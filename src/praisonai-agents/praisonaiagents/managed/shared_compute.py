"""Share one remote sandbox across every agent in a team or workflow.

``LocalAgent(compute=...)`` gives a *single* agent remote tools, and each agent
provisions its own isolated instance. A workflow therefore ends up with N
sandboxes and no shared filesystem, so agents cannot hand files to each other.

``SharedCompute`` provisions **one** instance for a whole run and binds every
participating agent's shell/file tools to it, so step 2 can read what step 1
wrote. Orchestration (routing, parallel, repeat) still runs locally.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import shlex
import threading
import uuid
import weakref
from typing import Any, Dict, List, Optional

from ._compute_bridge import resolve_compute

logger = logging.getLogger(__name__)

# Tool names that mean "touch the machine" and so must follow the sandbox.
BRIDGED_TOOL_NAMES = ("execute_command", "read_file", "write_file", "list_files")

# Models routinely refuse to call bridged tools because nothing in the prompt
# says remote execution is available -- the sandbox spins up and is never used.
CAPABILITY_PROMPT = (
    "You have tools that run on a REMOTE Linux sandbox, not on the user's machine: "
    "execute_command(command), read_file(path), write_file(path, content), list_files(path). "
    "Use them for any shell, file, or code-execution request. Never claim you are unable "
    "to run commands. All agents in this run share the same sandbox and working directory, "
    "so files written by an earlier step are visible to later steps."
)


def _run_sync(coro):
    """Run ``coro`` to completion from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop (e.g. called from async workflow code): hand the
    # coroutine to a private loop on another thread so we never re-enter.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class SharedCompute:
    """One provisioned sandbox instance shared by many agents.

    Provisioning is lazy: nothing is created until a tool is actually called, so
    a workflow that never touches the sandbox costs nothing.
    """

    def __init__(
        self,
        compute: Any,
        *,
        config: Optional[Any] = None,
        working_dir: str = "/workspace",
        auto_shutdown: bool = True,
        idle_timeout_s: int = 300,
    ):
        self.provider = resolve_compute(compute)
        self.working_dir = working_dir
        self.instance_id: Optional[str] = None
        self._config = config
        self._auto_shutdown = auto_shutdown
        self._idle_timeout_s = idle_timeout_s
        self._patched: List[Any] = []
        # Serialises lazy provisioning: parallel steps can make their first tool
        # call concurrently, and without this two threads would each provision
        # their own sandbox -- splitting the run and leaking one instance.
        self._provision_lock = threading.Lock()

    # ── lifecycle ────────────────────────────────────────────────────────────
    @property
    def provider_name(self) -> str:
        return getattr(self.provider, "provider_name", type(self.provider).__name__)

    def ensure_provisioned(self) -> str:
        """Provision on first use and return the instance id.

        Guarded by a lock so concurrent first-use calls (e.g. from a parallel
        step) share one sandbox instead of racing and provisioning several.
        """
        if self.instance_id is not None:
            return self.instance_id

        with self._provision_lock:
            # Re-check inside the lock: another thread may have provisioned
            # while we were waiting.
            if self.instance_id is not None:
                return self.instance_id

            config = self._config
            if config is None:
                from .protocols import ComputeConfig

                config = ComputeConfig(
                    working_dir=self.working_dir,
                    auto_shutdown=self._auto_shutdown,
                    idle_timeout_s=self._idle_timeout_s,
                )

            info = _run_sync(self.provider.provision(config))
            self.instance_id = getattr(info, "instance_id", info)
            logger.info(
                "[shared_compute] provisioned %s instance %s",
                self.provider_name,
                self.instance_id,
            )
            return self.instance_id

    def shutdown(self) -> None:
        """Tear down the instance and restore any agents we patched."""
        for ref, original_tools, original_backstory in self._patched:
            agent = ref()
            if agent is None:
                continue          # already collected; nothing left to restore
            try:
                if getattr(agent, "_tools_sandbox", None) is self:
                    agent._tools_sandbox = None
                agent.tools = original_tools
                agent.backstory = original_backstory
                cache = getattr(agent, "_system_prompt_cache", None)
                if cache is not None and hasattr(cache, "clear"):
                    cache.clear()
            except Exception:  # pragma: no cover - restoration is best-effort
                logger.debug("[shared_compute] could not restore agent %r", agent)
        self._patched.clear()

        if self.instance_id is None:
            return
        try:
            _run_sync(self.provider.shutdown(self.instance_id))
            logger.info("[shared_compute] shut down instance %s", self.instance_id)
        except Exception as exc:  # pragma: no cover - teardown must not mask errors
            logger.warning("[shared_compute] shutdown failed for %s: %s", self.instance_id, exc)
            self.instance_id = None
            raise            # the caller logs whether the sandbox was released
        finally:
            self.instance_id = None

    def __enter__(self) -> "SharedCompute":
        return self

    def __exit__(self, *exc_info) -> None:
        self.shutdown()

    # ── remote primitives ────────────────────────────────────────────────────
    def run_command(self, command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute ``command`` inside the shared sandbox."""
        instance_id = self.ensure_provisioned()
        result = _run_sync(self.provider.execute(instance_id, command, timeout))
        if isinstance(result, dict):
            return result
        return {"stdout": str(result), "stderr": "", "exit_code": 0}

    @staticmethod
    def _format(result: Dict[str, Any]) -> str:
        stdout = (result.get("stdout") or "").rstrip("\n")
        stderr = (result.get("stderr") or "").rstrip("\n")
        if result.get("exit_code"):
            return f"Error (exit {result['exit_code']}): {stderr or stdout or 'command failed'}"
        if stdout:
            return stdout
        if stderr:
            return stderr
        # Never return "" -- an empty tool result reads as "no progress" to the
        # loop guard and the model retries until it trips the stuck detector.
        return "(command succeeded with no output)"

    # ── tools handed to agents ───────────────────────────────────────────────
    def build_tools(self) -> List[Any]:
        """Return shell/file tools bound to this shared instance."""

        def execute_command(command: str) -> str:
            """Run a shell command on the shared remote sandbox."""
            return self._format(self.run_command(command))

        def read_file(path: str) -> str:
            """Read a file from the shared remote sandbox."""
            return self._format(self.run_command(f"cat {shlex.quote(path)}"))

        def write_file(path: str, content: str) -> str:
            """Write a file to the shared remote sandbox."""
            quoted = shlex.quote(path)
            # Random per-write delimiter so file content can never terminate the
            # heredoc early (which would truncate the file and run the remainder
            # as shell commands). Guard against the astronomically-unlikely case
            # where the token still appears in the body.
            # Uppercase hex on purpose. uuid4().hex is lowercase, and the
            # security policy substring-matches blocked_commands against the
            # whole command -- "dd" is one of them, and appears in 9.6% of
            # random lowercase hex strings. One write in ten failed with
            # "Blocked command pattern: dd" for no reason the caller could see.
            delimiter = f"__PRAISON_EOF_{uuid.uuid4().hex.upper()}__"
            while delimiter in content:
                delimiter = f"__PRAISON_EOF_{uuid.uuid4().hex.upper()}__"
            heredoc = (
                f"mkdir -p $(dirname {quoted}) && "
                f"cat > {quoted} <<'{delimiter}'\n{content}\n{delimiter}"
            )
            result = self.run_command(heredoc)
            if result.get("exit_code"):
                return self._format(result)
            return f"Wrote {path}"

        def list_files(path: str = ".") -> str:
            """List files in a directory on the shared remote sandbox."""
            return self._format(self.run_command(f"ls -la {shlex.quote(path)}"))

        bridged = [execute_command, read_file, write_file, list_files]
        # Tag them so Agent.clone_for_channel() drops them: each closes over
        # THIS sandbox, so a clone inheriting them would talk to the original
        # agent's instance and then attach a second sandbox of its own --
        # duplicating the capability prompt and splitting its work across two
        # machines. The clone regenerates its own on first use.
        for tool in bridged:
            tool._praison_sandbox_tool = True
        return bridged

    def attach(self, agents: List[Any], *, override_declared: bool = False) -> None:
        """Give each agent the shared tools and tell it they exist.

        Agents that already carry their own managed ``backend`` are skipped --
        they have deliberately been pointed at their own runtime.

        ``override_declared`` is set only by the agent's *own* placement, which
        is this sandbox's whole reason for existing. A run-level sandbox leaves
        it False so an agent that named its own place keeps it.
        """
        tools = self.build_tools()
        by_name = {t.__name__: t for t in tools}

        for agent in agents:
            if agent is None or getattr(agent, "backend", None) is not None:
                continue
            # An agent that named its own place, or already has a sandbox, must
            # not be attached again. A second attach appends CAPABILITY_PROMPT
            # twice and, if the two teardowns do not happen in LIFO order,
            # permanently restores the wrong tools: the agent is left holding
            # four tools bound to a shut-down instance.
            #
            # `tools_run_on` is checked as well as `_tools_sandbox` because of
            # ordering: a flow attaches at the start of the run, before the
            # agent's first chat() has created its own sandbox. Checking only
            # the live sandbox would attach here and let the agent attach again
            # on its first turn. An explicit per-agent choice outranks the run's
            # default, so the flow leaves it alone.
            declared_own = (
                not override_declared
                and getattr(agent, "tools_run_on", None) is not None
            )
            if getattr(agent, "_tools_sandbox", None) is not None or declared_own:
                logger.debug(
                    "[shared_compute] %r already runs its tools on %s; leaving it alone",
                    getattr(agent, "name", agent),
                    getattr(agent, "tools_run_on", "its own sandbox"),
                )
                continue
            if any(agent is ref() for ref, _, _ in self._patched):
                continue

            original_tools = list(getattr(agent, "tools", None) or [])
            # Agent.__init__ copies `instructions` into role/goal/backstory and
            # builds the system prompt from THOSE, so mutating `.instructions`
            # here would be silently ignored. Patch `backstory`, which leads the
            # system prompt.
            original_backstory = getattr(agent, "backstory", None)

            # Replace same-named local tools; keep everything else untouched.
            merged = [
                t for t in original_tools
                if getattr(t, "__name__", getattr(t, "name", None)) not in by_name
            ]
            merged.extend(tools)

            try:
                agent.tools = merged
                agent.backstory = (
                    f"{original_backstory}\n\n{CAPABILITY_PROMPT}"
                    if original_backstory
                    else CAPABILITY_PROMPT
                )
                # The system prompt is memoised per (role, goal, tools); drop the
                # cache so the capability text is actually rendered.
                cache = getattr(agent, "_system_prompt_cache", None)
                if cache is not None and hasattr(cache, "clear"):
                    cache.clear()
            except Exception as exc:  # pragma: no cover - never break a run over this
                logger.warning("[shared_compute] could not attach tools to %r: %s", agent, exc)
                continue

            # Mark where this agent's tools now run, so a nested attach (or a
            # later ensure_tools_placed) can see it is already bound.
            try:
                agent._tools_sandbox = self
            except Exception:  # pragma: no cover - exotic agent objects
                pass
            # Weakly: an agent points at its SharedCompute and the SharedCompute
            # pointed back, so a dropped agent was reclaimed as a cycle and its
            # sandbox was never shut down. Holding the agent weakly lets
            # weakref.finalize see the agent die and release the sandbox.
            try:
                ref = weakref.ref(agent)
            except TypeError:  # pragma: no cover - non-weakrefable agent
                ref = lambda _agent=agent: _agent
            self._patched.append((ref, original_tools, original_backstory))
