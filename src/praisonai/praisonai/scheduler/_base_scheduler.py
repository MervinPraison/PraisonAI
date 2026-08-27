"""
Shared, lock-agnostic scheduler logic for both sync and async variants.
"""

import os
import json
import logging
from enum import Enum
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Type

logger = logging.getLogger(__name__)


class DeliveryOutcome(str, Enum):
    """Typed outcome of routing a scheduled run's result to its chat target.

    Makes the fire-time delivery result *observable* instead of a discarded
    ``bool``: the caller folds it into the run's recorded outcome so a
    scheduled run never reports plain success when the user received nothing.

    - ``NOT_CONFIGURED``: no ``deliver`` target — nothing to send.
    - ``SUPPRESSED``: intentional silence (NO_REPLY / [SILENT]) — a *recorded*
      non-outcome, not a failure.
    - ``DELIVERED``: the router accepted the send.
    - ``UNDELIVERED``: the send failed (dead target, package missing,
      unresolvable token, transient error) — surfaced, never silent.
    """

    NOT_CONFIGURED = "not_configured"
    SUPPRESSED = "suppressed"
    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"

    @property
    def undelivered(self) -> bool:
        """True only for an *unintended* delivery failure that must surface."""
        return self is DeliveryOutcome.UNDELIVERED


def _to_non_negative_int(value: Any) -> int:
    """Coerce a token count to a non-negative int, defaulting to 0 on bad input.

    Guards against negative or malformed usage values that could otherwise
    produce a negative run cost (a budget-brake bypass) or raise during cost
    calculation.
    """
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _extract_usage(result: Any) -> Tuple[int, int, str]:
    """Pull (input_tokens, output_tokens, model) off whatever the agent returned.

    Looks for the common LiteLLM / SDK response shapes. Falls back to
    (0, 0, '') so a response with no usage metadata contributes $0 — not a
    fake constant. The budget brake should err on the side of running forever
    rather than tripping prematurely on missing metadata.
    """
    usage = getattr(result, "usage", None)
    if usage is None and isinstance(result, dict):
        usage = result.get("usage")

    model = getattr(result, "model", None)
    if model is None and isinstance(result, dict):
        model = result.get("model")
    model = model or ""

    if usage is None:
        return 0, 0, model

    if isinstance(usage, dict):
        in_tok = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        out_tok = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        return _to_non_negative_int(in_tok), _to_non_negative_int(out_tok), model

    in_tok = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0
    out_tok = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0
    return _to_non_negative_int(in_tok), _to_non_negative_int(out_tok), model


def _compute_run_cost(result: Any) -> Tuple[float, int, int, str]:
    """Compute the real cost of a single run from its usage metadata.

    Returns (cost, input_tokens, output_tokens, model). Returns a cost of 0.0
    when no token usage is available rather than a misleading constant.
    """
    in_tok, out_tok, model = _extract_usage(result)
    if not (in_tok or out_tok):
        return 0.0, in_tok, out_tok, model
    from praisonai.cli.features.cost_tracker import get_pricing
    try:
        cost = get_pricing(model or "default").calculate_cost(in_tok, out_tok)
    except Exception:
        logger.debug(
            "Cost computation failed for model=%r; treating run cost as 0.0", model
        )
        return 0.0, in_tok, out_tok, model
    return cost, in_tok, out_tok, model


def build_from_yaml(
    scheduler_cls: Type,
    yaml_path: str = "agents.yaml",
    interval_override: Optional[str] = None,
    max_retries_override: Optional[int] = None,
    timeout_override: Optional[int] = None,
    max_cost_override: Optional[float] = None,
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
) -> "_BaseAgentScheduler":
    """Construct a scheduler from an agents.yaml file.

    Shared by both the sync ``AgentScheduler`` and async ``AsyncAgentScheduler``;
    the only difference between the two is ``scheduler_cls``. The agent created
    here is framework-agnostic, so no executor-agent wrapper parameter is needed.
    """
    from .yaml_loader import load_agent_yaml_with_schedule, create_agent_from_config

    # Load configuration from YAML
    agent_config, schedule_config = load_agent_yaml_with_schedule(yaml_path)

    # Validate task before any (potentially expensive) agent construction
    task = agent_config.get('task', '')
    if not task:
        raise ValueError("No task specified in YAML file")

    # Create agent from config
    agent = create_agent_from_config(agent_config)

    # Apply overrides to schedule config
    if interval_override:
        schedule_config['interval'] = interval_override
    if max_retries_override is not None:
        schedule_config['max_retries'] = max_retries_override
    if timeout_override is not None:
        schedule_config['timeout'] = timeout_override
    if max_cost_override is not None:
        schedule_config['max_cost'] = max_cost_override

    # Create scheduler instance with timeout and cost limits
    scheduler = scheduler_cls(
        agent=agent,
        task=task,
        config=agent_config,
        timeout=schedule_config.get('timeout'),
        max_cost=schedule_config.get('max_cost'),
        on_success=on_success,
        on_failure=on_failure,
        deliver=schedule_config.get('deliver', ''),
    )

    # Store schedule config for later use
    scheduler._yaml_schedule_config = schedule_config

    return scheduler


def build_from_recipe(
    scheduler_cls: Type,
    agent_cls: Type,
    recipe_name: str,
    *,
    input_data: Any = None,
    config: Optional[Dict[str, Any]] = None,
    interval_override: Optional[str] = None,
    max_retries_override: Optional[int] = None,
    timeout_override: Optional[int] = None,
    max_cost_override: Optional[float] = None,
    deliver: str = "",
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
) -> "_BaseAgentScheduler":
    """Construct a scheduler from a recipe name.

    Shared by both sync and async schedulers. ``scheduler_cls`` selects the
    scheduler type and ``agent_cls`` selects the executor-agent wrapper
    (``RecipeExecutorAgent`` vs ``AsyncRecipeExecutorAgent``) — the only two
    pieces that differed between the previously-duplicated copies.
    """
    from praisonai.recipe.bridge import resolve, get_recipe_task_description

    # Only pass timeout_sec through to recipe execution when the caller
    # explicitly overrides it. Otherwise leave options empty so the recipe's
    # own runtime_config timeout (via resolved.get_timeout_sec()) is honoured
    # instead of being clobbered by the scheduler default.
    resolve_options: Dict[str, Any] = {}
    if timeout_override is not None:
        resolve_options['timeout_sec'] = timeout_override

    # Resolve the recipe
    resolved = resolve(
        recipe_name,
        input_data=input_data,
        config=config or {},
        options=resolve_options,
    )

    # Get runtime config defaults from recipe
    interval = interval_override or "hourly"
    max_retries = max_retries_override if max_retries_override is not None else 3
    timeout = timeout_override if timeout_override is not None else 300
    max_cost = max_cost_override if max_cost_override is not None else 1.00

    runtime = resolved.runtime_config
    if runtime and hasattr(runtime, 'schedule'):
        sched_config = runtime.schedule
        interval = interval_override or sched_config.interval
        max_retries = max_retries_override if max_retries_override is not None else sched_config.max_retries
        timeout = timeout_override or sched_config.timeout_sec
        max_cost = max_cost_override if max_cost_override is not None else sched_config.max_cost_usd
        # An explicit ``deliver=`` argument wins; otherwise fall back to a
        # target declared on the recipe's schedule config, if any.
        deliver = deliver or getattr(sched_config, 'deliver', '') or ''

    # Create the executor-agent wrapper (sync or async variant)
    agent = agent_cls(resolved)
    task = get_recipe_task_description(resolved)

    # Create scheduler instance
    scheduler = scheduler_cls(
        agent=agent,
        task=task,
        timeout=timeout,
        max_cost=max_cost,
        on_success=on_success,
        on_failure=on_failure,
        deliver=deliver,
    )

    # Store recipe metadata and schedule config
    scheduler._recipe_name = recipe_name
    scheduler._recipe_resolved = resolved
    scheduler._yaml_schedule_config = {
        'interval': interval,
        'max_retries': max_retries,
        'run_immediately': False,
        'timeout': timeout,
        'max_cost': max_cost,
        'deliver': deliver,
    }

    return scheduler


def build_from_blueprint(
    scheduler_cls: Type,
    agent_cls: Type,
    blueprint_name: str,
    *,
    slots: Optional[Dict[str, Any]] = None,
    deliver: str = "",
    agent_id: str = "",
    interval_override: Optional[str] = None,
    max_retries_override: Optional[int] = None,
    timeout_override: Optional[int] = None,
    max_cost_override: Optional[float] = None,
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
) -> "_BaseAgentScheduler":
    """Construct a scheduler from a blueprint template.

    Shared by both the sync ``AgentScheduler`` and async
    ``AsyncAgentScheduler`` so blueprint resolution lives in one place.
    ``scheduler_cls`` selects the scheduler type and ``agent_cls`` selects the
    blueprint-agent wrapper (``BlueprintAgent`` vs ``AsyncBlueprintAgent``) —
    the only pieces that differ between the two surfaces.
    """
    from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue

    catalogue = BlueprintCatalogue()
    bp = catalogue.get_blueprint(blueprint_name)
    if bp is None:
        available = [b.name for b in catalogue.list_blueprints()]
        raise ValueError(
            f"Blueprint '{blueprint_name}' not found. "
            f"Available: {available}"
        )

    resolved_slots = catalogue.resolve_slots(bp, slots or {})
    prompt = catalogue.materialize_prompt(bp, resolved_slots)
    schedule_expr = catalogue.materialize_schedule(bp, resolved_slots)

    config: Dict[str, Any] = {
        "blueprint": blueprint_name,
        "resolved_slots": resolved_slots,
        "deliver": deliver or bp.default_deliver,
        "agent_id": agent_id or bp.default_agent,
    }

    agent = agent_cls(prompt, blueprint_name)

    timeout = timeout_override or 300
    max_cost = max_cost_override if max_cost_override is not None else 1.00

    scheduler = scheduler_cls(
        agent=agent,
        task=prompt,
        config=config,
        timeout=timeout,
        max_cost=max_cost,
        on_success=on_success,
        on_failure=on_failure,
        deliver=config.get("deliver", ""),
    )

    scheduler._blueprint_name = blueprint_name
    scheduler._blueprint_slots = resolved_slots
    scheduler._yaml_schedule_config = {
        'interval': interval_override or schedule_expr,
        'max_retries': max_retries_override if max_retries_override is not None else 3,
        'run_immediately': False,
        'timeout': timeout,
        'max_cost': max_cost,
    }

    return scheduler


class _BaseAgentScheduler:
    """Shared, lock-agnostic scheduler logic — used by both sync and async variants."""

    is_running: bool
    max_cost: Optional[float]
    _execution_count: int
    _success_count: int
    _failure_count: int
    _total_cost: float
    _start_time: Optional[datetime]
    # Delivery-outcome accounting (Issue #4454): tracked with explicit counters
    # rather than inferred from success counts, so a run with no target
    # (NOT_CONFIGURED) or intentional silence (SUPPRESSED) is never mislabelled
    # as delivered, and a run whose delivery fails is counted ``undelivered`` —
    # never a plain success.
    _delivered_count: int = 0
    _undelivered_count: int = 0

    @property
    def _delivery_lock(self):
        """Lazily-created lock guarding the delivery-outcome counters.

        Created on first use so both the sync and async schedulers (whose own
        counters use their own locks) can safely bump delivery counts from a
        worker thread without either subclass having to declare it.
        """
        lock = getattr(self, "_delivery_lock_obj", None)
        if lock is None:
            import threading as _threading
            lock = _threading.Lock()
            self._delivery_lock_obj = lock
        return lock

    def _should_suppress_delivery(self, text: str) -> bool:
        """Return True when a run's whole output is an exact silence marker.

        Honours the core intentional-silence contract (NO_REPLY / [SILENT] /
        SILENT) on the unattended path so both sync and async schedulers stay
        quiet instead of delivering the literal marker. Prose that merely
        mentions the token is unaffected (exact-match).
        """
        try:
            from praisonaiagents.bots.silence import is_intentional_silence_response
            return is_intentional_silence_response(text)
        except Exception:  # pragma: no cover - core primitive always present
            return False

    def _deliver_result(self, result: Any) -> "DeliveryOutcome":
        """Route a successful result to the configured chat target.

        Returns a typed :class:`DeliveryOutcome` so the caller can fold the
        fire-time delivery result into the run's recorded outcome instead of
        discarding it — a scheduled run whose delivery fails must never report
        plain success (Issue #4454). The delivery target is resolved and sent
        through the shared ``DeliveryRouter`` (rate limiting, idempotency dedup,
        dead-target self-heal), reusing the same machinery the gateway uses —
        without requiring the full gateway. Never raises: a delivery problem
        must not tear down the scheduler. Shared by both the sync and async
        schedulers.
        """
        if not self.deliver:
            return DeliveryOutcome.NOT_CONFIGURED
        text = str(result)
        # Honour the core intentional-silence contract on the unattended path:
        # a run whose whole output is an exact silence marker (NO_REPLY /
        # [SILENT] / SILENT) means "nothing worth sending — stay quiet". The
        # run still completes and is recorded in history; only delivery is
        # suppressed. Prose that merely mentions the token is unaffected
        # (is_intentional_silence_response is exact-match). This is a *recorded*
        # non-outcome, not an unintended failure.
        if self._should_suppress_delivery(text):
            logger.info(
                "Scheduled run chose intentional silence; delivery suppressed"
            )
            return DeliveryOutcome.SUPPRESSED
        try:
            if self._delivery is None:
                # Normally built eagerly at __init__ for a creation-time
                # pre-flight; rebuild here as a fallback if that was skipped.
                self._build_delivery()
            if self._delivery is None:
                # The wrapper could not be built (e.g. praisonai-bot missing):
                # the result was configured for delivery but went nowhere.
                logger.error(
                    "Scheduler delivery target configured but unavailable; "
                    "result not delivered"
                )
                return DeliveryOutcome.UNDELIVERED
            delivered = self._delivery.deliver(text)
            return (
                DeliveryOutcome.DELIVERED if delivered
                else DeliveryOutcome.UNDELIVERED
            )
        except Exception as e:
            logger.error(f"Scheduler delivery error: {e}")
            return DeliveryOutcome.UNDELIVERED

    def _finalize_delivery(self, result: Any) -> bool:
        """Deliver ``result`` and fold the outcome into truthful accounting.

        Runs the configured delivery, then records the outcome so a scheduled
        run whose delivery fails is never reported as a plain success
        (Issue #4454). Returns ``True`` when the run should fire ``on_success``
        (delivered, suppressed, or no target) and ``False`` when it must fire
        the delivery-failure path instead. Shared by both schedulers.
        """
        outcome = self._deliver_result(result)
        if outcome is DeliveryOutcome.DELIVERED:
            with self._delivery_lock:
                self._delivered_count += 1
            return True
        if outcome.undelivered:
            self._record_undelivered(result)
            return False
        # NOT_CONFIGURED / SUPPRESSED: nothing was supposed to be sent, so the
        # run's success is unaffected.
        return True

    def _record_undelivered(self, result: Any) -> None:
        """Record + surface a scheduled result that could not be delivered.

        A run whose ``deliver=`` target ultimately fails is *not* a plain
        success: it bumps the ``undelivered`` counter, best-effort fires the
        core ``MESSAGE_UNDELIVERED`` hook (reusing the existing protocol seam —
        no new protocol) if a hook runner is attached to the agent, and lets
        the caller invoke ``on_failure``. Never raises. Shared by both the
        sync and async schedulers.
        """
        with self._delivery_lock:
            self._undelivered_count += 1
        runner = getattr(self.agent, "hook_runner", None) or getattr(
            self.agent, "_hook_runner", None
        )
        if runner is None:
            return
        try:
            from praisonaiagents.hooks.types import HookEvent
            from praisonaiagents.hooks.events import MessageUndeliveredInput
            import time as _time

            target = getattr(self._delivery, "_target", None)
            platform = getattr(target, "channel", "") or str(self.deliver)
            channel_id = getattr(target, "channel_id", "") or ""
            event_input = MessageUndeliveredInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.MESSAGE_UNDELIVERED,
                timestamp=str(_time.time()),
                agent_name=getattr(self.agent, "name", "scheduler"),
                platform=platform,
                content=str(result),
                channel_id=channel_id,
                error="scheduled result could not be delivered",
                notice_delivered=False,
            )
            runner.execute_sync(HookEvent.MESSAGE_UNDELIVERED, event_input)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("MESSAGE_UNDELIVERED hook failed: %s", e)

    def _build_delivery(self) -> None:
        """Construct the delivery wrapper, running its creation-time pre-flight.

        Building :class:`SchedulerDelivery` here resolves the ``deliver`` token
        (rewriting a symbolic ``"origin"`` to the persisted concrete origin) and
        logs a preview / actionable warning for the configured destination —
        without touching the network. Called eagerly at ``__init__`` so that
        pre-flight happens at *creation*, with a lazy fallback in
        ``_deliver_result``. Never raises: a delivery-setup problem must not
        prevent the scheduler from being created or a run from completing.
        Shared by both the sync and async schedulers.
        """
        try:
            from praisonai.scheduler._delivery import SchedulerDelivery
            job_id = self.config.get("agent_id", "") if self.config else ""
            # Pass the persisted origin (if any) so a ``deliver="origin"``
            # target resolves to the concrete channel the job was created
            # in — without the full gateway.
            origin = SchedulerDelivery.origin_from_config(self.config)
            self._delivery = SchedulerDelivery(
                self.deliver, job_id=job_id, origin=origin
            )
        except Exception as e:
            logger.error(f"Scheduler delivery setup error: {e}")

    def _budget_exceeded(self) -> bool:
        """Return True when the accumulated cost has reached ``max_cost``.

        A ``max_cost`` of 0 is a real (zero) budget and must trip immediately;
        only ``None`` means "no budget limit".
        """
        return self.max_cost is not None and self._total_cost >= self.max_cost

    def _build_stats(
        self,
        *,
        execs: int,
        success: int,
        failed: int,
        total_cost: float,
    ) -> Dict[str, Any]:
        """Build stats dictionary for both sync and async schedulers."""
        runtime = (
            (datetime.now() - self._start_time).total_seconds()
            if self._start_time else 0
        )
        return {
            "is_running": self.is_running,
            "total_executions": execs,
            "successful_executions": success,
            "failed_executions": failed,
            "success_rate": (success / execs * 100) if execs > 0 else 0,
            "total_cost_usd": round(total_cost, 4),
            "remaining_budget": (
                round(self.max_cost - total_cost, 4) if self.max_cost is not None else None
            ),
            "runtime_seconds": runtime,
            "cost_per_execution": (
                round(total_cost / execs, 4) if execs > 0 else 0
            ),
            # Delivery-outcome accounting (Issue #4454): distinguish a run that
            # actually reached the user from one whose delivery failed. A run
            # can be a successful *execution* yet an undelivered *result*. Both
            # use explicit counters (not success-minus-undelivered inference) so
            # NOT_CONFIGURED / SUPPRESSED runs never over-report a delivery.
            "delivered_deliveries": getattr(self, "_delivered_count", 0),
            "undelivered_deliveries": getattr(self, "_undelivered_count", 0),
        }

    def _update_state_if_daemon(self) -> None:
        """Update ~/.praisonai/schedulers/*.json for the current PID, if present.

        Safe for both sync and async callers — it's plain blocking file I/O that
        runs once per execution and is wrapped in try/except.
        """
        try:
            state_dir = os.path.expanduser("~/.praisonai/schedulers")
            if not os.path.exists(state_dir):
                return
            current_pid = os.getpid()
            for fname in os.listdir(state_dir):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(state_dir, fname)
                try:
                    with open(path, "r") as f:
                        state = json.load(f)
                    if state.get("pid") == current_pid:
                        state["executions"] = self._execution_count
                        state["cost"] = round(self._total_cost, 4)
                        # Persist the wall-clock anchor so a restart resumes the
                        # schedule at the next real occurrence instead of
                        # re-phasing from process start (see issue #3526).
                        last_run = getattr(self, "_last_run_at", None)
                        if last_run is not None:
                            state["last_run_at"] = last_run
                        with open(path, "w") as f:
                            json.dump(state, f, indent=2)
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Failed to update state: %s", e)

    def _load_persisted_last_run(self) -> None:
        """Restore ``_last_run_at`` from this PID's daemon state file, if any.

        Lets a restarted daemon resume a wall-clock (cron) schedule from where
        it left off — a slot missed during downtime runs once, then re-anchors
        — instead of re-phasing from process start (see issue #3526). No-op for
        plain interval schedules and when no daemon state file exists.
        """
        try:
            state_dir = os.path.expanduser("~/.praisonai/schedulers")
            if not os.path.exists(state_dir):
                return
            current_pid = os.getpid()
            for fname in os.listdir(state_dir):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(state_dir, fname)
                try:
                    with open(path, "r") as f:
                        state = json.load(f)
                    if state.get("pid") == current_pid:
                        last_run = state.get("last_run_at")
                        if last_run is not None:
                            self._last_run_at = float(last_run)
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Failed to load persisted last_run_at: %s", e)