"""
ScheduledAgentExecutor — bridges ScheduleRunner + agent resolution.

This is a thin reusable bridge that any consumer (UI, CLI, custom app)
can use to poll the scheduler and dispatch due jobs to agents, without
reimplementing the same polling + agent-lookup logic each time.

Lives in the **bot** layer because the gateway polls due jobs and dispatches
to registered agents. Optional :class:`RunPolicy` (wrapper safety gate) is
supported when co-installed via ``praisonai.scheduler.run_policy``.

Usage::

    from praisonaiagents.scheduler import ScheduleRunner, FileScheduleStore
    from praisonai_bot.scheduler.executor import ScheduledAgentExecutor

    store = FileScheduleStore()
    runner = ScheduleRunner(store)

    executor = ScheduledAgentExecutor(
        runner=runner,
        agent_resolver=lambda agent_id: my_gateway.get_agent(agent_id),
    )

    # In your async event loop:
    async for job_result in executor.tick():
        print(f"Job {job_result.job.name}: {job_result.result}")
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import os
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from praisonaiagents.scheduler import ScheduleRunner, ScheduleJob
    from praisonaiagents.scheduler.models import DeliveryTarget
    from praisonaiagents.scheduler.protocols import JobConditionProtocol

    RunPolicy = Any  # optional wrapper ``praisonai.scheduler.run_policy.RunPolicy``

logger = logging.getLogger(__name__)

# On POSIX, start the command in its own session so a timeout can kill the whole
# process group (shell + children) rather than orphaning them. Mirrors the
# pattern used by the pre-run ``ShellConditionGate``.
_POSIX = os.name == "posix"

# Bound the delivered output so a chatty command cannot flood the channel or
# disk. stdout is truncated to this many characters (with a marker) verbatim.
_MAX_COMMAND_OUTPUT_CHARS = 8000


@dataclass
class JobResult:
    """Result of a single scheduled job execution.

    Attributes:
        job: The ScheduleJob that was executed.
        result: Agent response (str) or None on failure.
        status: ``"succeeded"``, ``"failed"``, or ``"skipped"``.
        error: Error message if status is ``"failed"``.
        duration: Wall-clock seconds for agent execution.
        delivered: Whether the result was delivered to a channel bot.
        delivery_error: Delivery failure message, separate from execution
            ``error`` so a job that ran but failed to deliver is auditable.
        audit_path: Local path where full output was persisted (if any).
    """

    job: Any  # ScheduleJob
    result: Optional[str] = None
    status: str = "succeeded"
    error: Optional[str] = None
    duration: float = 0.0
    delivered: bool = False
    delivery_error: Optional[str] = None
    audit_path: Optional[str] = None


class ScheduledAgentExecutor:
    """Bridges ScheduleRunner + agent resolution for any consumer.

    This is a **stateless** helper — it does not own a loop or thread.
    Callers decide how and when to call :meth:`tick` or :meth:`run_loop`.

    Parameters:
        runner: An SDK ``ScheduleRunner`` instance.
        agent_resolver: A callable ``(agent_id: str | None) -> Agent``
            that returns an agent for the given ID.  May return ``None``
            if no agent is available.
        delivery_handler: Optional async callable
            ``(delivery: DeliveryTarget, text: str) -> None``.
            Called after successful execution when the job has a
            delivery target.  Typically routes to a channel bot's
            ``send_message()``.  When it is ``None`` (``praisonai schedule
            tick`` run out of process with no live gateway) delivery falls back
            to a stateless, token-authenticated standalone sender for the target
            platform (Telegram/Slack/Discord) using the same ``{PLATFORM}_BOT_TOKEN``
            env the gateway uses, so scheduled delivery works unattended.
        on_success: Optional callback ``(job, result) -> None``.
        on_failure: Optional callback ``(job, error) -> None``.
        run_policy: Optional :class:`~praisonai.scheduler.run_policy.RunPolicy`
            applied to every unattended run — scopes the agent's toolset,
            scans the assembled prompt, persists a durable output audit, and
            (when configured) delivers a failure summary on failure.
        condition_resolver: Optional callable ``(job) -> JobConditionProtocol``
            returning a *pre-run gate* for the job, or ``None`` for no gate.
            The gate is evaluated **before** the model turn: when it returns
            ``run=False`` the tick is recorded as ``skipped`` (no tokens spent,
            no delivery); when it returns ``run=True`` with ``context`` the
            context is appended to the job message. Defaults to a resolver that
            returns a :class:`~praisonai.scheduler.condition_gate.ShellConditionGate`
            for jobs with a ``pre_run`` command. Pass ``condition_resolver=False``
            (or a resolver returning ``None``) to disable gating entirely.
            This is a *cost/efficiency* gate, complementary to the *safety*
            ``run_policy``.
    """

    def __init__(
        self,
        runner: "ScheduleRunner",
        agent_resolver: Callable[[Optional[str]], Any],
        *,
        delivery_handler: Optional[Callable[..., Any]] = None,
        on_success: Optional[Callable[..., None]] = None,
        on_failure: Optional[Callable[..., None]] = None,
        run_policy: Optional["RunPolicy"] = None,
        condition_resolver: Any = None,
        owner_id: Optional[str] = None,
        lease_seconds: float = 300.0,
    ) -> None:
        self._runner = runner
        self._resolve = agent_resolver
        self._deliver = delivery_handler
        self._on_success = on_success
        self._on_failure = on_failure
        self._run_policy = run_policy
        # ``None`` → use the default shell gate resolver; ``False`` → disable
        # gating; otherwise a user-supplied ``(job) -> gate | None`` callable.
        self._condition_resolver = condition_resolver
        # Stable-per-process identity for atomic job claims so a due job fires
        # at most once across tickers/processes/hosts when the store supports
        # ``claim_due``. Defaults to host+pid+uuid.
        self._owner_id = owner_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._lease_seconds = lease_seconds

    # ── public API ───────────────────────────────────────────────────

    async def tick(self) -> AsyncIterator[JobResult]:
        """Check for due jobs and execute them, yielding results.

        Each due job is dispatched to the resolved agent via
        ``agent.chat(job.message)`` in a background thread (so sync
        agents work correctly in an async context).

        Yields:
            :class:`JobResult` for each due job.

        When the backing store supports an atomic claim (``claim_due``), each
        due job is reserved under a cross-process lock before running so it
        fires **at most once** across all tickers/processes/hosts. Stores
        without that support fall back to the non-atomic ``get_due_jobs`` path.
        """
        claim = getattr(self._runner, "claim_due_jobs", None)
        if callable(claim):
            due_jobs: List["ScheduleJob"] = claim(self._owner_id, self._lease_seconds)
            atomic = getattr(self._runner, "supports_atomic_claim", None)
            atomic_claim = bool(atomic()) if callable(atomic) else False
        else:  # pragma: no cover - older runner without claim support
            due_jobs = self._runner.get_due_jobs()
            atomic_claim = False

        for job in due_jobs:
            try:
                result = await self._execute_one(job)
            finally:
                if atomic_claim:
                    # Release the lease so it does not linger until expiry.
                    try:
                        self._runner.complete_run(job.id, self._owner_id)
                    except Exception as e:  # pragma: no cover - defensive
                        logger.warning(
                            "Failed to release lease for job '%s': %s", job.id, e,
                        )
            yield result

    async def tick_all(self) -> List[JobResult]:
        """Like :meth:`tick` but collects all results into a list."""
        results: List[JobResult] = []
        async for r in self.tick():
            results.append(r)
        return results

    async def run_loop(
        self,
        interval: float = 15.0,
        *,
        max_ticks: Optional[int] = None,
    ) -> None:
        """Convenience loop that calls :meth:`tick` at a fixed interval.

        Args:
            interval: Seconds between ticks (default 15).
            max_ticks: Stop after this many ticks (``None`` = forever).
        """
        tick_count = 0
        logger.info(
            "ScheduledAgentExecutor loop started (interval=%.1fs)", interval,
        )
        try:
            while max_ticks is None or tick_count < max_ticks:
                async for result in self.tick():
                    logger.info(
                        "Job '%s' %s (%.1fs)",
                        getattr(result.job, "name", result.job),
                        result.status,
                        result.duration,
                    )
                tick_count += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("ScheduledAgentExecutor loop stopped after %d ticks", tick_count)

    # ── internals ────────────────────────────────────────────────────

    async def _execute_one(self, job: "ScheduleJob") -> JobResult:
        """Execute a single job and return the result."""
        started = time.time()

        # Model-free command action: when the job carries a ``command`` it runs
        # that command on its schedule and delivers stdout verbatim — no agent
        # is resolved and no model turn is taken. Checked before the agent path
        # so a deterministic watchdog (``df -h``, ``uptime``, a health-check
        # ``curl``) costs no tokens and cannot be reformatted by a model.
        command = str(getattr(job, "command", "") or "").strip()
        if command:
            return await self._execute_command(job, command, started)

        message = str(getattr(job, "message", "") or "")
        agent_id = getattr(job, "agent_id", None)

        # Skip jobs with no message
        if not message:
            duration = time.time() - started
            self._runner.mark_run(
                job,
                status="skipped",
                error="No message configured",
                duration=duration,
            )
            return JobResult(
                job=job,
                status="skipped",
                error="No message configured",
                duration=duration,
            )

        # Resolve the agent
        try:
            agent = self._resolve(agent_id)
        except Exception as e:
            logger.warning("Agent resolution failed for job '%s': %s", job.id, e)
            err = f"Agent resolution failed: {e}"
            duration = time.time() - started
            self._runner.mark_run(job, status="failed", error=err, duration=duration)
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(
                job=job, status="failed", error=err, duration=duration,
            )

        if agent is None:
            err = f"No agent found for agent_id={agent_id!r}"
            logger.warning("Skipping job '%s': %s", job.id, err)
            duration = time.time() - started
            self._runner.mark_run(job, status="failed", error=err, duration=duration)
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(
                job=job, status="failed", error=err, duration=duration,
            )

        # Model pin / drift guard: an unattended job created against one model
        # must not silently start running on whatever the default later becomes
        # (a switch to a pricier frontier model would inflate cost and change
        # behaviour with nobody watching). When the job carries a ``model``
        # snapshot and ``pin_model`` is set, compare it with the resolved
        # agent's current model; on drift, fail closed (recorded as an error
        # and, where configured, delivered) rather than running on the new one.
        # Jobs with no snapshot skip this entirely, preserving prior behaviour.
        drift, _restore_pin = self._check_model_drift(job, agent)
        if drift is not None:
            logger.warning("Job '%s' blocked by model drift: %s", job.id, drift)
            duration = time.time() - started
            self._runner.mark_run(
                job, status="failed", error=drift, duration=duration,
            )
            if self._on_failure:
                self._on_failure(job, drift)
            failed = JobResult(
                job=job, status="failed", error=drift, duration=duration,
            )
            await asyncio.to_thread(self._audit_output, job, failed)
            await self._maybe_deliver_failure(job, failed)
            return failed

        # The pin above mutates the shared agent's ``llm`` for the duration of
        # this run only. From here every exit path — the pre-run gate skip, a
        # run-policy block, the model turn, or a raised exception — must restore
        # it, so the pin never leaks into another (attended) turn on the same
        # agent. ``_run_pinned`` wraps the remainder in a single try/finally.
        try:
            return await self._run_pinned(job, agent, message, started)
        finally:
            if _restore_pin is not None:
                _restore_pin()

    async def _run_pinned(
        self, job: "ScheduleJob", agent: Any, message: str, started: float,
    ) -> "JobResult":
        """Gate, policy-scan, and run the model turn for a resolved agent.

        Split out from :meth:`_dispatch` so the run-scoped model pin can be
        restored in a single ``finally`` around every exit path below.
        """
        # Cross-run memory: load the job's persisted scratchpad (cursor /
        # watermark / last-seen hash) so both the pre-run gate and the model
        # turn can do *incremental* work — "only what's new since last run".
        # ``prior`` is ``{}`` when the store has no per-job state support or the
        # job has none, preserving today's stateless behaviour exactly.
        prior_state = self._get_job_state(job)
        # The unmodified baseline used when persisting after the run so a
        # merge that only re-adds an already-present gate watermark is still
        # detected as a change and written (``prior_state`` below gets the gate
        # watermark folded in for the notepad, so it can't serve as the base).
        original_state = dict(prior_state)
        # Accumulates state to persist after the run — a monitor gate's
        # watermark and/or state the agent emits. Kept separate from
        # ``prior_state`` so we only ever *write* when something actually
        # changed (an empty accumulator → no write, today's behaviour).
        pending_updates: Dict[str, Any] = {}

        # Pre-run condition gate (cost/efficiency): a cheap, deterministic
        # check that decides whether the (expensive) model turn is warranted.
        # When it reports "nothing to do" the tick is recorded as ``skipped`` —
        # no tokens spent, no empty message delivered.  When it reports "go"
        # any context it produced is appended to the message before the turn.
        gate = self._resolve_condition(job)
        if gate is not None:
            # Only pass ``state=`` to a gate that opts into it — a legacy
            # stateless gate (``should_run(self, job)``) would raise TypeError.
            pass_state = self._gate_accepts_state(gate)
            try:
                # Run off the event loop: the default gate shells out via
                # subprocess.run(), which would otherwise block every other
                # tick / delivery / health-check coroutine for the gate's
                # timeout. Mirrors the agent.chat() offload below.
                if pass_state:
                    decision = await asyncio.to_thread(
                        gate.should_run, job, state=prior_state,
                    )
                else:
                    decision = await asyncio.to_thread(gate.should_run, job)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "Pre-run gate raised for job '%s': %s; running anyway",
                    job.id, e,
                )
                decision = None
            if decision is not None and not getattr(decision, "run", True):
                reason = getattr(decision, "reason", None) or "pre-run gate: nothing to do"
                logger.info("Job '%s' skipped by pre-run gate: %s", job.id, reason)
                # A monitor gate may carry a watermark forward even on a
                # suppressed tick (e.g. ``no_change`` recording the last-seen
                # hash). Persist it so the *next* tick sees the advance.
                self._persist_job_state(
                    job, prior_state, getattr(decision, "state_updates", None),
                )
                duration = time.time() - started
                self._runner.mark_run(
                    job, status="skipped", error=reason, duration=duration,
                )
                return JobResult(
                    job=job, status="skipped", error=reason, duration=duration,
                )
            if decision is not None:
                context = getattr(decision, "context", None)
                if context:
                    message = f"{message}\n\n{context}"
                # Fold any gate watermark into the state visible to this run
                # (so the notepad reflects the latest cursor) AND queue it for
                # persistence after the run — a go-path gate watermark must land
                # too, not only a skip-path one.
                updates = getattr(decision, "state_updates", None)
                if isinstance(updates, dict) and updates:
                    prior_state = {**prior_state, **updates}
                    pending_updates.update(updates)

        # Give the model turn memory of the last run by injecting a compact,
        # clearly-delimited notepad. No-op when there is no prior state.
        message = self._with_notepad(message, prior_state)

        # Run-scoped policy: scan the *untrusted* portion of the run before it
        # reaches the model — the user message plus any runtime-loaded skill or
        # recipe content, which is where injected text actually arrives.  The
        # agent's own admin-authored system prompt / instructions / backstory
        # are trusted configuration and are deliberately NOT fed to the built-in
        # heuristic scanner (it would false-positive on common defensive phrases
        # like "do not reveal your system prompt").  A deployment that wants to
        # scan the full context can supply its own ``scanner``.
        if self._run_policy is not None:
            scan_target = self._assemble_scan_target(agent, message)
            scan = self._run_policy.scan_prompt(scan_target)
            if not scan.ok:
                err = f"Blocked by run policy: {scan.reason}"
                logger.warning(
                    "Job '%s' blocked by run policy: %s", job.id, scan.reason,
                )
                duration = time.time() - started
                self._runner.mark_run(
                    job, status="failed", error=err, duration=duration,
                )
                if self._on_failure:
                    self._on_failure(job, err)
                result = JobResult(
                    job=job, status="failed", error=err, duration=duration,
                )
                await asyncio.to_thread(self._audit_output, job, result)
                await self._maybe_deliver_failure(job, result)
                return result

        # Execute via agent.chat() in a thread (sync-safe)
        # Wire session_target: "main" preserves context, "isolated" is fresh
        # Toolset scoping: restrict the agent's tools for the duration of this
        # unattended run, restoring them afterwards so the policy never leaks
        # into other (attended) uses of the same agent instance.
        _restore_tools = self._apply_toolset_scope(agent)
        try:
            session_target = getattr(job, "session_target", "isolated")
            delivery = getattr(job, "delivery", None)
            session_id = (
                getattr(delivery, "session_id", None)
                if delivery else None
            )

            # Build chat kwargs — only pass session_id if the agent
            # actually accepts it (Core SDK's Agent.chat signature does
            # not currently expose session_id; older assumption caused a
            # TypeError on every scheduled job).
            chat_kwargs: Dict[str, Any] = {}
            try:
                chat_params = inspect.signature(agent.chat).parameters
            except (TypeError, ValueError):  # C-callable or builtin
                chat_params = {}
            supports_session_id = (
                "session_id" in chat_params
                or any(p.kind == inspect.Parameter.VAR_KEYWORD
                       for p in chat_params.values())
            )
            if supports_session_id:
                if session_target == "main" and session_id:
                    chat_kwargs["session_id"] = session_id
                else:
                    chat_kwargs["session_id"] = f"cron_{job.id}"

            result = await asyncio.to_thread(
                agent.chat, message, **chat_kwargs,
            )
            result_str = str(result)
        except Exception as e:
            logger.warning("Job '%s' execution failed: %s", job.id, e)
            err = str(e)
            duration = time.time() - started
            self._runner.mark_run(job, status="failed", error=err, duration=duration)
            if self._on_failure:
                self._on_failure(job, err)
            failed = JobResult(
                job=job, status="failed", error=err, duration=duration,
            )
            await asyncio.to_thread(self._audit_output, job, failed)
            await self._maybe_deliver_failure(job, failed)
            return failed
        finally:
            if _restore_tools is not None:
                _restore_tools()

        # Success - calculate duration before delivery
        duration = time.time() - started

        # Build the success result up-front so the durable output audit is
        # written regardless of whether delivery later succeeds or fails.
        job_result = JobResult(
            job=job,
            result=result_str,
            status="succeeded",
            duration=duration,
        )
        await asyncio.to_thread(self._audit_output, job, job_result)

        # Persist cross-run memory: any gate watermark queued above plus any
        # state the agent emitted (a ``state`` / ``state_updates`` mapping on a
        # rich chat result) are merged onto the original baseline and written,
        # keyed by job id and size-bounded by the store. No-op for stores
        # without ``set_state`` or when nothing changed — today's behaviour.
        agent_updates = self._agent_state_updates(result)
        if isinstance(agent_updates, dict):
            pending_updates.update(agent_updates)
        self._persist_job_state(job, original_state, pending_updates)

        # Honour the core intentional-silence contract: a run whose whole
        # output is an exact silence marker (NO_REPLY / [SILENT] / SILENT) means
        # "nothing worth sending — stay quiet". The run is still recorded as
        # succeeded (audited above, history below); only delivery is suppressed
        # so an unattended monitor does not post the raw control token. Prose
        # that merely mentions the token is unaffected (exact-match check).
        silent = False
        try:
            from praisonaiagents.bots.silence import is_intentional_silence_response
            silent = is_intentional_silence_response(result_str)
        except Exception:  # pragma: no cover - core primitive always present
            silent = False

        # Deliver to channel bot if delivery target exists
        delivered = False
        delivery_error: Optional[str] = None
        delivery = getattr(job, "delivery", None)
        if silent:
            logger.info(
                "Job '%s' chose intentional silence; delivery suppressed", job.id,
            )
        elif delivery and self._can_deliver(delivery):
            try:
                await self._dispatch_delivery(delivery, result_str)
                delivered = True
                logger.info(
                    "Delivered job '%s' result to %s:%s",
                    job.id, delivery.channel, delivery.channel_id,
                )
            except Exception as e:
                delivery_error = str(e)
                logger.warning(
                    "Delivery failed for job '%s' to %s:%s: %s",
                    job.id, delivery.channel, delivery.channel_id, e,
                )

        # Log history with execution results.  last_status is the *execution*
        # status (succeeded) recorded separately from any delivery error, so a
        # job that ran but failed to deliver is auditable.
        self._runner.mark_run(
            job,
            status="succeeded",
            result=result_str,
            duration=duration,
            delivered=delivered,
        )

        if self._on_success:
            self._on_success(job, result_str)

        job_result.delivered = delivered
        job_result.delivery_error = delivery_error
        return job_result

    # ── command-action helpers ───────────────────────────────────────

    async def _execute_command(
        self, job: "ScheduleJob", command: str, started: float,
    ) -> JobResult:
        """Run a job's ``command`` and deliver its stdout verbatim.

        No agent is resolved and no model turn is taken. The command runs off
        the event loop (via :func:`asyncio.to_thread`) so a slow command does
        not block other ticks / deliveries; it is bounded by
        ``job.command_timeout`` and killed with its process group on POSIX. A
        non-zero exit surfaces the exit code and output rather than being
        silently dropped, and output is bounded before delivery.
        """
        # Defensively normalise the timeout: a corrupt persisted value (e.g.
        # ``"five"`` from a hand-edited store) must fail only *this* job, never
        # escape ``float(...)`` and break the ticker loop for every other job.
        # Non-numeric, non-positive, or non-finite values fall back to 60s.
        raw_timeout = getattr(job, "command_timeout", 60.0)
        try:
            timeout = float(raw_timeout)
            if not math.isfinite(timeout) or timeout <= 0:
                timeout = 60.0
        except (TypeError, ValueError):
            timeout = 60.0
        try:
            output, code = await asyncio.to_thread(
                self._run_command, command, timeout,
            )
        except Exception as e:  # pragma: no cover - defensive
            err = f"command failed to launch: {e}"
            logger.warning("Job '%s' %s", job.id, err)
            duration = time.time() - started
            self._runner.mark_run(job, status="failed", error=err, duration=duration)
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(job=job, status="failed", error=err, duration=duration)

        duration = time.time() - started
        succeeded = code == 0
        text = output if succeeded else f"[exit {code}] {output}".rstrip()

        # Deliver verbatim through the existing DeliveryTarget path, unchanged.
        delivered = False
        delivery_error: Optional[str] = None
        delivery = getattr(job, "delivery", None)
        if text and delivery and self._can_deliver(delivery):
            try:
                await self._dispatch_delivery(delivery, text)
                delivered = True
                logger.info(
                    "Delivered command job '%s' output to %s:%s",
                    job.id, delivery.channel, delivery.channel_id,
                )
            except Exception as e:
                delivery_error = str(e)
                logger.warning(
                    "Delivery failed for command job '%s': %s", job.id, e,
                )

        status = "succeeded" if succeeded else "failed"
        self._runner.mark_run(
            job,
            status=status,
            result=text if succeeded else None,
            error=None if succeeded else text,
            duration=duration,
            delivered=delivered,
        )
        if succeeded and self._on_success:
            self._on_success(job, text)
        elif not succeeded and self._on_failure:
            self._on_failure(job, text)

        return JobResult(
            job=job,
            result=text if succeeded else None,
            status=status,
            error=None if succeeded else text,
            duration=duration,
            delivered=delivered,
            delivery_error=delivery_error,
        )

    @staticmethod
    def _run_command(command: str, timeout: float) -> Tuple[str, int]:
        """Run ``command`` in a shell, returning ``(bounded_output, exit_code)``.

        On POSIX the shell runs in its own session so a timeout kills the whole
        process group (shell + children) instead of orphaning them. On timeout
        the process is killed and a ``124`` exit code (the conventional
        ``timeout(1)`` code) is returned with whatever output was captured.

        Output is bounded *as it is read* rather than buffered in full: a chatty
        or runaway command in the long-running gateway cannot grow the capture
        past ``_MAX_COMMAND_OUTPUT_CHARS`` (+ marker), so it cannot exhaust
        gateway memory. The wall-clock ``timeout`` still bounds total runtime and
        kills the process group on breach.
        """
        popen_kwargs: dict = {}
        if _POSIX:
            popen_kwargs["start_new_session"] = True

        # Hard cap the number of chars we retain in memory regardless of how much
        # the command emits; once past the cap we keep reading (to let the pipe
        # drain / the process finish) but discard the excess.
        cap = _MAX_COMMAND_OUTPUT_CHARS
        chunks: List[str] = []
        retained = 0
        truncated = False
        deadline = time.monotonic() + max(timeout, 0.0)

        def _drain(stream) -> None:
            nonlocal retained, truncated
            for line in iter(stream.readline, ""):
                if retained < cap:
                    room = cap - retained
                    chunks.append(line[:room])
                    retained += min(len(line), room)
                    if retained >= cap:
                        truncated = True
                else:
                    truncated = True

        proc = None
        timed_out = False
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **popen_kwargs,
            )
            reader = threading.Thread(
                target=_drain, args=(proc.stdout,), daemon=True,
            )
            reader.start()
            remaining = deadline - time.monotonic()
            reader.join(timeout=max(remaining, 0.0))
            # A process that has already exited (stdout at EOF) may not have its
            # status reaped yet, so ``proc.poll()`` can transiently return None
            # right after a fast exit. Never infer a timeout from process state
            # alone — only the wall-clock deadline decides. Otherwise a command
            # that exits quickly (e.g. ``sys.exit(3)``) races into a false
            # ``124`` kill on a loaded runner.
            if proc.poll() is None:
                # Give the process a brief chance to be reaped before deciding.
                grace = deadline - time.monotonic()
                if grace > 0:
                    try:
                        proc.wait(timeout=grace)
                    except subprocess.TimeoutExpired:
                        pass
                if proc.poll() is None and time.monotonic() >= deadline:
                    # Genuinely past the deadline and still running → timed out.
                    timed_out = True
                    try:
                        if _POSIX:
                            os.killpg(os.getpgid(proc.pid), 9)
                        else:  # pragma: no cover - non-POSIX
                            proc.kill()
                    except (ProcessLookupError, PermissionError, OSError):  # pragma: no cover
                        proc.kill()
            proc.wait(timeout=5)
            reader.join(timeout=5)
            code = 124 if timed_out else (proc.returncode if proc.returncode is not None else 0)
        except Exception:  # pragma: no cover - defensive: reap and surface
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            raise
        finally:
            if proc is not None and proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:  # pragma: no cover
                    pass

        output = "".join(chunks)
        if timed_out:
            output = f"{output}\n[timed out after {timeout:.0f}s]"
        output = output.rstrip("\n")
        if truncated:
            output += "\n…[output truncated]"
        return output, code

    # ── condition-gate helpers ───────────────────────────────────────

    def _resolve_condition(self, job: "ScheduleJob") -> Optional["JobConditionProtocol"]:
        """Resolve the pre-run gate for ``job`` (or ``None`` for no gate).

        Resolution order:
        - ``condition_resolver is False`` → gating disabled, return ``None``.
        - a user-supplied callable → call it with the job and return its result.
        - default (``None``) → return a :class:`ShellConditionGate` when the
          job declares a ``pre_run`` command, else ``None``.
        """
        resolver = self._condition_resolver
        if resolver is False:
            return None
        if resolver is not None:
            try:
                return resolver(job)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "condition_resolver raised for job '%s': %s; no gate applied",
                    getattr(job, "id", "?"), e,
                )
                return None
        # Default resolver: only build a gate when there is something to gate on.
        if not (getattr(job, "pre_run", None) or "").strip():
            return None
        from .condition_gate import ShellConditionGate
        return ShellConditionGate()

    @staticmethod
    def _gate_accepts_state(gate: Any) -> bool:
        """Whether ``gate.should_run`` opts into a keyword-only ``state=``.

        A legacy stateless gate (``should_run(self, job)``) must never be
        passed ``state=`` — it would raise ``TypeError`` and break every tick.
        We detect the capability by signature (an explicit ``state`` parameter
        or ``**kwargs``) so stateless gates keep working unchanged.
        """
        should_run = getattr(gate, "should_run", None)
        if should_run is None:
            return False
        try:
            params = inspect.signature(should_run).parameters
        except (TypeError, ValueError):  # pragma: no cover - C-callable
            return False
        if "state" in params:
            return True
        return any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )

    # ── cross-run state helpers (JobStateStoreProtocol) ───────────────

    def _state_store(self) -> Optional[Any]:
        """Return the backing store if it supports per-job state, else ``None``.

        Reuses the runner's existing schedule store when it implements the core
        :class:`JobStateStoreProtocol` (``get_state`` / ``set_state``). Detected
        with ``hasattr`` so a store without state support (or an older runner)
        transparently yields ``None`` — the stateless behaviour of today.
        """
        store = getattr(self._runner, "_store", None)
        if store is None:
            return None
        if hasattr(store, "get_state") and hasattr(store, "set_state"):
            return store
        return None

    def _get_job_state(self, job: "ScheduleJob") -> Dict[str, Any]:
        """Load the job's persisted scratchpad (``{}`` when unsupported/empty)."""
        store = self._state_store()
        if store is None:
            return {}
        try:
            state = store.get_state(job.id)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Could not read state for job '%s': %s", job.id, e)
            return {}
        return dict(state) if isinstance(state, dict) else {}

    def _persist_job_state(
        self,
        job: "ScheduleJob",
        prior: Dict[str, Any],
        updates: Optional[Dict[str, Any]],
    ) -> None:
        """Merge ``updates`` onto ``prior`` and persist, if anything changed.

        ``updates is None`` means "write nothing" (an error/no-op probe leaves
        prior state untouched); an empty dict likewise changes nothing. No-op
        when the store has no state support.

        One-shot jobs (``delete_after_run``) are already removed from the store
        by ``claim_due`` before the run reaches here, and their state is popped
        with them. Persisting now would recreate an orphan ``job_state`` entry
        that nothing ever cleans up (the schedule is gone, so ``remove`` is a
        no-op) — and which would be injected if the same explicit id is reused.
        A single-run job has no "next run" to read a watermark, so skip it.
        """
        if getattr(job, "delete_after_run", False):
            return
        if not isinstance(updates, dict) or not updates:
            return
        store = self._state_store()
        if store is None:
            return
        merged = {**prior, **updates}
        if merged == prior:
            return
        try:
            store.set_state(job.id, merged)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Could not persist state for job '%s': %s", job.id, e)

    @staticmethod
    def _agent_state_updates(result: Any) -> Optional[Dict[str, Any]]:
        """Extract a state mapping the agent emitted on a rich chat result.

        Most agents return a plain string (no state) — this returns ``None``
        then, so nothing is written. A richer result object MAY expose a
        ``state_updates`` or ``state`` mapping to carry a watermark forward.
        """
        for attr in ("state_updates", "state"):
            value = getattr(result, attr, None)
            if isinstance(value, dict) and value:
                return value
        return None

    @staticmethod
    def _with_notepad(message: str, state: Dict[str, Any]) -> str:
        """Prepend a compact, delimited "state since last run" notepad.

        Returns ``message`` unchanged when there is no prior state so a
        stateless job's prompt is byte-for-byte what it was before. The block
        is rendered as sorted ``key=value`` lines so the agent can pick up a
        cursor / watermark and do incremental work.
        """
        if not state:
            return message
        try:
            lines = "\n".join(
                f"{k}={state[k]}" for k in sorted(state, key=str)
            )
        except Exception:  # pragma: no cover - defensive
            lines = str(state)
        notepad = f"Notepad (state since last run):\n{lines}"
        return f"{notepad}\n\n{message}"

    # ── model pin / drift helpers ────────────────────────────────────

    @staticmethod
    def _split_provider_model(
        provider: Optional[str], model: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Normalise a ``(provider, model)`` pair to separate parts.

        A model string may embed its provider (e.g. ``"openai/gpt-4o"``). When
        an explicit ``provider`` is absent and the model carries a ``/`` prefix,
        the prefix is lifted out so a provider-qualified pin and a bare-model
        resolution (or vice versa) compare as the same provider/model — avoiding
        a false drift purely from representation. Only the *first* ``/`` splits
        (model paths like ``"openai/ft:gpt-4o:org::id"`` keep their tail).
        """
        if not isinstance(model, str) or not model:
            model = None
        if not isinstance(provider, str) or not provider:
            provider = None
        if provider is None and model is not None and "/" in model:
            head, _, tail = model.partition("/")
            if head and tail:
                provider, model = head, tail
        return provider, model

    @classmethod
    def _agent_model(cls, agent: Any) -> Tuple[Optional[str], Optional[str]]:
        """Best-effort normalised ``(provider, model)`` for a resolved agent.

        The core ``Agent`` carries its model as ``agent.llm`` (a string that may
        embed the provider, e.g. ``"openai/gpt-4o"``); an explicit ``provider``
        attribute is honoured when present. Returns ``(None, None)`` when the
        agent exposes nothing recognisable so an unreadable agent never *causes*
        a false drift — the snapshot comparison simply cannot fire.
        """
        provider = getattr(agent, "provider", None)
        model = getattr(agent, "model", None)
        if not isinstance(model, str) or not model:
            llm = getattr(agent, "llm", None)
            model = llm if isinstance(llm, str) and llm else None
        return cls._split_provider_model(provider, model)

    def _check_model_drift(
        self, job: "ScheduleJob", agent: Any
    ) -> Tuple[Optional[str], Optional[Callable[[], None]]]:
        """Enforce a pinned job's model snapshot.

        Returns ``(drift_reason, restore)``:
        - ``drift_reason`` is a string when a pinned job has drifted (the run
          must fail closed), else ``None``.
        - ``restore`` is a zero-arg callable that undoes the run-scoped pin, or
          ``None`` when nothing was pinned. It **must** be invoked in a
          ``finally`` after the turn so the pin never leaks into other
          (attended) uses of the same shared agent instance.

        No-op (``(None, None)``) unless the job carries a ``model`` snapshot and
        ``pin_model`` is truthy — an unpinned or unsnapshotted job follows the
        default exactly as before. Both sides are normalised (provider prefix
        lifted out of the model) before comparison so equivalent representations
        (``openai/gpt-4o`` vs ``gpt-4o``+``openai``) do not false-drift.
        """
        pinned_model = getattr(job, "model", None)
        if not pinned_model or not getattr(job, "pin_model", True):
            return None, None
        pinned_provider, pinned_model = self._split_provider_model(
            getattr(job, "provider", None), pinned_model
        )
        provider, model = self._agent_model(agent)
        # Compare provider only when both sides carry one — a snapshot without a
        # provider (model-only pin) must not fail closed just because the agent
        # happens to expose a provider attribute, and vice versa.
        provider_drift = (
            pinned_provider is not None
            and provider is not None
            and provider != pinned_provider
        )
        model_drift = model is not None and model != pinned_model
        if provider_drift or model_drift:
            reason = (
                f"model drift: pinned {pinned_provider or '?'}/{pinned_model}, "
                f"resolver now {provider or '?'}/{model or '?'}"
            )
            return reason, None
        # No drift → pin the run to the snapshot so the turn is stable even if
        # the resolver's default later changes between this check and the call.
        # The pin is **run-scoped**: the resolved agent is typically a shared
        # registry instance, so we snapshot the prior ``llm`` and return a
        # restore callable the caller invokes in ``finally`` — the pin never
        # bleeds into another (attended) turn on the same agent.
        pin_value = (
            f"{pinned_provider}/{pinned_model}" if pinned_provider else pinned_model
        )
        try:
            had_llm = hasattr(agent, "llm")
            prev_llm = getattr(agent, "llm", None)
            agent.llm = pin_value
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "Could not pin job '%s' to model %r: %s",
                job.id, pin_value, e,
            )
            return None, None

        def _restore() -> None:
            try:
                if had_llm:
                    agent.llm = prev_llm
                else:  # pragma: no cover - defensive
                    delattr(agent, "llm")
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "Could not restore model after pinned job '%s': %s",
                    job.id, e,
                )

        return None, _restore

    # ── run-policy helpers ───────────────────────────────────────────

    def _assemble_scan_target(self, agent: Any, message: str) -> str:
        """Build the *untrusted* content to scan for injection.

        Combines the user message with any runtime-loaded skill or recipe
        content — the surfaces through which attacker-controlled text actually
        reaches an unattended run.  The agent's admin-authored ``system_prompt``
        / ``instructions`` / ``backstory`` are trusted configuration set at
        agent-construction time and are intentionally excluded: feeding them to
        the heuristic scanner caused false positives on common defensive
        instructions (e.g. "do not reveal your system prompt"), which would
        silently block every scheduled run for affected agents.
        """
        parts: List[str] = []
        # Loaded skill/recipe content, if the agent exposes it — this is loaded
        # at run construction and can carry injected text.
        for attr in ("loaded_skills", "skills", "recipes"):
            value = getattr(agent, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    parts.append(str(item))
            elif isinstance(value, str) and value.strip():
                parts.append(value)
        parts.append(message)
        return "\n".join(parts)

    def _apply_toolset_scope(self, agent: Any) -> Optional[Callable[[], None]]:
        """Scope the agent's tools per the run policy for one run.

        Returns a callable that restores the agent's original tools, or
        ``None`` when no scoping was applied.  Restoration ensures the policy
        does not leak into other (attended) uses of the same agent instance.
        """
        if self._run_policy is None:
            return None
        original = getattr(agent, "tools", None)
        if not original:
            return None
        filtered = self._run_policy.filter_tools(list(original))
        if len(filtered) == len(original):
            return None
        try:
            agent.tools = filtered
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("RunPolicy could not scope agent tools: %s", e)
            return None

        def _restore() -> None:
            try:
                agent.tools = original
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "RunPolicy could not restore agent tools: %s", e,
                )

        return _restore

    def _audit_output(self, job: "ScheduleJob", result: JobResult) -> None:
        """Persist the full run output to a durable audit path.

        Writes regardless of delivery outcome so a run that succeeded but
        failed to deliver is recoverable.  No-op unless the policy configures
        an ``audit_dir``.
        """
        if self._run_policy is None or not self._run_policy.audit_dir:
            return
        audit_dir = self._run_policy.audit_dir
        try:
            os.makedirs(audit_dir, exist_ok=True)
            ts = time.time_ns()
            # Sanitise job.id into a safe basename so path separators / ".."
            # cannot escape audit_dir, and use a nanosecond stamp so two runs
            # of the same job in the same second do not overwrite each other.
            safe_job_id = "".join(
                ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
                for ch in str(getattr(job, "id", "") or "job")
            ) or "job"
            path = os.path.join(audit_dir, f"{safe_job_id}_{ts}.txt")
            body = result.result if result.result is not None else (result.error or "")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    f"job_id={job.id}\n"
                    f"job_name={getattr(job, 'name', '')}\n"
                    f"status={result.status}\n"
                    f"duration={result.duration:.3f}\n"
                    f"timestamp={ts}\n"
                    f"---\n"
                )
                fh.write(body)
            result.audit_path = path
            logger.info("Persisted run audit for job '%s' to %s", job.id, path)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to write run audit for job '%s': %s", job.id, e)

    def _can_deliver(self, delivery: "DeliveryTarget") -> bool:
        """Whether a configured ``delivery`` target should be dispatched.

        A configured target is *always* dispatched so that a target with no
        delivery mechanism (no live handler and no standalone sender for its
        platform) surfaces an actionable ``delivery_error`` via
        :meth:`_dispatch_delivery` instead of being silently dropped. Only a
        missing target (``None``) short-circuits — there is nothing to deliver.
        The capability decision (live handler vs. standalone sender vs. neither)
        is made in :meth:`_dispatch_delivery`, which raises when neither exists.
        """
        return delivery is not None

    async def _dispatch_delivery(
        self, delivery: "DeliveryTarget", text: str,
    ) -> None:
        """Deliver ``text`` to ``delivery``, preferring the live adapter.

        When a live ``delivery_handler`` is wired (a running gateway) it is used
        unchanged. When it is absent — ``praisonai schedule tick`` run out of
        process as a plain OS-cron / CI / serverless job — this falls back to a
        stateless, token-authenticated standalone sender for the target platform
        so scheduled delivery works without a persistent gateway. If neither is
        available the send raises, so the caller records ``delivery_error``
        exactly as it does for any other delivery failure.
        """
        if self._deliver is not None:
            coro = self._deliver(delivery, text)
            if inspect.isawaitable(coro):
                await coro
            return
        from ._standalone_sender import resolve_standalone_sender

        sender = resolve_standalone_sender(getattr(delivery, "channel", ""))
        if sender is None:
            raise RuntimeError(
                "no live adapter and no standalone sender for channel "
                f"{getattr(delivery, 'channel', '')!r}"
            )
        await sender(delivery, text)

    async def _maybe_deliver_failure(
        self, job: "ScheduleJob", result: JobResult,
    ) -> None:
        """Fail-closed delivery: send a compact failure summary on failure.

        Active only when the run policy sets ``deliver_on_failure`` and the job
        has a delivery target.  Records any delivery error on the result
        separately from the execution ``error``.
        """
        if self._run_policy is None or not self._run_policy.deliver_on_failure:
            return
        delivery = getattr(job, "delivery", None)
        if not delivery or not self._can_deliver(delivery):
            return
        summary = (
            f"⚠️ Scheduled job '{getattr(job, 'name', job.id)}' failed: "
            f"{result.error or 'unknown error'}"
        )
        try:
            await self._dispatch_delivery(delivery, summary)
            logger.info("Delivered failure summary for job '%s'", job.id)
        except Exception as e:
            result.delivery_error = str(e)
            logger.warning(
                "Failure-summary delivery failed for job '%s': %s", job.id, e,
            )
