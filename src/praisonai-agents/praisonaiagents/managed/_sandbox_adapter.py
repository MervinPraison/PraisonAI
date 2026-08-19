"""Expose a single sandbox environment as a one-instance compute provider.

There are two execution stacks in this project and they are *not* duplicates:

* ``SandboxProtocol`` (praisonai-sandbox) -- one object **is** one environment:
  ``start / stop / execute / run_command / reset``.
* ``ComputeProviderProtocol`` -- one object **hands out** many environments:
  ``provision / execute(instance_id, ...) / shutdown / list_instances``.

``tools_run_on=`` speaks the second protocol, so four backends that only exist
as sandboxes -- ``subprocess``, ``sandlock``, ``ssh``, ``novita`` -- were
unreachable through it. This adapter is the missing half: it holds exactly one
environment and presents the manager-shaped API over it.

Deliberate limitation: ``list_instances()`` can only report what *this process*
provisioned, so adapter-backed places never appear in ``praisonai managed ps``.
A single environment has no cross-process registry to consult, and pretending
otherwise would be worse than saying so.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Backends that exist only as SandboxProtocol implementations. The literal is
# the floor, not the ceiling: the sandbox registry accepts plugins by entry
# point, so a hardcoded tuple silently withheld contributed backends from
# tools_run_on=. `capsule` was the live example -- it ships from
# praisonai-plugins, worked with run_in=, and was invisible to tools_run_on=.
_SANDBOX_ONLY_FLOOR = ("subprocess", "sandlock", "ssh", "novita")


def sandbox_only_names() -> tuple:
    """Sandbox backends with no compute-registry equivalent.

    Anything the compute registry already provides is excluded, so a name that
    exists in both (docker, e2b, modal, daytona) keeps its richer compute
    implementation rather than being downgraded to the one-instance adapter.
    """
    names = set(_SANDBOX_ONLY_FLOOR)
    try:
        from ..sandbox._sandbox_bridge import get_sandbox_registry

        registry = get_sandbox_registry()
        registry = registry.default() if isinstance(registry, type) else registry
        names |= {str(n).lower() for n in registry.list_all_names()}
    except Exception:  # pragma: no cover - discovery must never break resolution
        pass

    try:
        from ._compute_bridge import _PROVIDERS

        names -= set(_PROVIDERS)
    except Exception:
        pass
    return tuple(sorted(names))


class _SandboxOnly(tuple):
    """A tuple that re-reads the registry, so `in` sees plugins installed later.

    Kept as a tuple subclass because SANDBOX_ONLY is imported and iterated in
    several places that predate this.
    """

    def __contains__(self, item):
        return item in sandbox_only_names()

    def __iter__(self):
        return iter(sandbox_only_names())

    def __len__(self):
        return len(sandbox_only_names())


SANDBOX_ONLY = _SandboxOnly(_SANDBOX_ONLY_FLOOR)

# Names that need connection details no bare string can carry.
NEEDS_INSTANCE = {
    "ssh": (
        "run on a remote machine over SSH by passing the object, so it can "
        "carry the host: SSHSandbox(host='...', user='...')"
    ),
}


class SandboxComputeAdapter:
    """One ``SandboxProtocol`` environment, wearing the compute-provider shape."""

    def __init__(self, sandbox_type: str, config: Optional[Any] = None,
                 sandbox: Optional[Any] = None):
        self._type = sandbox_type
        self._config = config
        self._sandbox = sandbox          # pre-built instance, if supplied
        self._owns_sandbox = sandbox is None
        self._instance_id: Optional[str] = None

    # ── identity ─────────────────────────────────────────────────────────────
    @property
    def provider_name(self) -> str:
        return self._type

    @property
    def is_available(self) -> bool:
        if self._sandbox is not None:
            return bool(getattr(self._sandbox, "is_available", True))
        try:
            from ..sandbox._sandbox_bridge import resolve_sandbox_class

            cls = resolve_sandbox_class(self._type)
            probe = cls() if self._type not in NEEDS_INSTANCE else None
            return bool(getattr(probe, "is_available", False)) if probe else False
        except Exception:
            return False

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def provision(self, config: Any) -> Any:
        from .protocols import InstanceInfo, InstanceStatus

        if self._sandbox is None:
            from ..sandbox import SandboxConfig
            from ..sandbox.manager import SandboxManager

            cfg = self._config
            if cfg is None:
                # "/workspace" is the convention for *container* sandboxes and
                # does not exist on a Mac or a bare Linux box -- creating it
                # fails with "Read-only file system". Local backends pick their
                # own private temp dir, so only pass a working_dir through when
                # the caller actually chose one.
                wanted_dir = getattr(config, "working_dir", None)
                local_place = self._type in ("subprocess", "sandlock")
                if local_place and wanted_dir in (None, "", "/workspace"):
                    wanted_dir = None
                cfg = SandboxConfig(
                    sandbox_type=self._type,
                    env=dict(getattr(config, "env", None) or {}),
                    **({"working_dir": wanted_dir} if wanted_dir else {}),
                )
                # This sandbox exists to back the model's execute_command tool,
                # which IS a shell. The default policy sets allow_subprocess=
                # False, which makes `sh -c` -- and therefore every pipe,
                # redirect and && the model writes -- fail as "disabled by
                # security policy". Blocking the shell inside a shell tool is a
                # contradiction, not a protection; blocked_commands and
                # blocked_paths still apply.
                if getattr(cfg, "security_policy", None) is not None:
                    cfg.security_policy.allow_subprocess = True
            if getattr(config, "image", None):
                cfg.image = config.image
            self._manager = SandboxManager(cfg)
            self._sandbox = await self._manager.__aenter__()
        else:
            self._manager = None
            starter = getattr(self._sandbox, "start", None)
            if starter is not None:
                await starter()

        self._instance_id = f"{self._type}_{uuid.uuid4().hex[:12]}"
        logger.info("[sandbox_adapter] provisioned %s as %s", self._type, self._instance_id)
        return InstanceInfo(
            instance_id=self._instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"{self._type}://local",
            provider=self._type,
            metadata={"adapter": True, "discoverable": False},
        )

    async def execute(self, instance_id: str, command: str,
                      timeout: Optional[int] = 300) -> Dict[str, Any]:
        if self._sandbox is None:
            raise RuntimeError(
                f"{self._type} sandbox is not running; provision() was not called"
            )
        # The bridged execute_command tool hands us a shell command string, and
        # models write pipes, redirects and && constantly. Without shell=True
        # `echo x > f` is argv-split and "> f" arrives as a literal argument.
        try:
            result = await self._sandbox.run_command(command, shell=True)
        except TypeError:
            # Backends predating the shell= parameter.
            result = await self._sandbox.run_command(command)
        # A policy denial arrives as result.error with exit_code=None. Dropping
        # it would turn "blocked by security policy" into a silent success --
        # the caller would see exit 0 and empty output.
        error = getattr(result, "error", None)
        exit_code = getattr(result, "exit_code", None)
        stderr = getattr(result, "stderr", "") or ""
        if error:
            stderr = f"{stderr}\n{error}".strip() if stderr else str(error)
            if exit_code in (None, 0):
                exit_code = 1
        return {
            "stdout": getattr(result, "stdout", "") or "",
            "stderr": stderr,
            "exit_code": exit_code or 0,
        }

    async def shutdown(self, instance_id: str) -> None:
        try:
            if getattr(self, "_manager", None) is not None:
                await self._manager.__aexit__(None, None, None)
            elif self._sandbox is not None:
                stopper = getattr(self._sandbox, "stop", None)
                if stopper is not None:
                    await stopper()
        finally:
            if self._owns_sandbox:
                self._sandbox = None
            self._manager = None
            self._instance_id = None

    async def get_status(self, instance_id: str) -> Any:
        from .protocols import InstanceInfo, InstanceStatus

        running = self._sandbox is not None and instance_id == self._instance_id
        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING if running else InstanceStatus.STOPPED,
            provider=self._type,
        )

    async def list_instances(self) -> List[Any]:
        """Only what this process provisioned -- see the module docstring."""
        from .protocols import InstanceInfo, InstanceStatus

        if self._instance_id is None:
            return []
        return [InstanceInfo(
            instance_id=self._instance_id,
            status=InstanceStatus.RUNNING,
            provider=self._type,
            metadata={"adapter": True, "discoverable": False},
        )]

    # ── file transfer ────────────────────────────────────────────────────────
    async def upload_file(self, instance_id: str, local_path: str, remote_path: str) -> None:
        with open(local_path, "r") as handle:
            await self._sandbox.write_file(remote_path, handle.read())

    async def download_file(self, instance_id: str, remote_path: str, local_path: str) -> None:
        content = await self._sandbox.read_file(remote_path)
        with open(local_path, "w") as handle:
            handle.write(content if isinstance(content, str) else str(content))


def wrap_sandbox_instance(sandbox: Any) -> SandboxComputeAdapter:
    """Adapt an already-constructed sandbox (e.g. ``SSHSandbox(host=...)``)."""
    name = getattr(sandbox, "sandbox_type", None) or type(sandbox).__name__.lower()
    return SandboxComputeAdapter(str(name), sandbox=sandbox)
