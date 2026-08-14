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
        for agent, original_tools, original_backstory in self._patched:
            try:
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
            delimiter = f"__PRAISON_EOF_{uuid.uuid4().hex}__"
            while delimiter in content:
                delimiter = f"__PRAISON_EOF_{uuid.uuid4().hex}__"
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

        return [execute_command, read_file, write_file, list_files]

    def attach(self, agents: List[Any]) -> None:
        """Give each agent the shared tools and tell it they exist.

        Agents that already carry their own managed ``backend`` are skipped --
        they have deliberately been pointed at their own runtime.
        """
        tools = self.build_tools()
        by_name = {t.__name__: t for t in tools}

        for agent in agents:
            if agent is None or getattr(agent, "backend", None) is not None:
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

            self._patched.append((agent, original_tools, original_backstory))
