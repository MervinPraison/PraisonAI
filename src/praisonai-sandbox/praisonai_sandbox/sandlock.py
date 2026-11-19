"""
Sandlock Sandbox implementation for PraisonAI.

Provides kernel-level isolated code execution using Landlock + seccomp-bpf.
Requires the 'sandlock' package for Linux systems.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from praisonaiagents.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxStatus,
    ResourceLimits,
)

logger = logging.getLogger(__name__)

# System directories every sandboxed interpreter may read.
_READ_ROOTS = ["/usr/lib/python3", "/usr/local/lib/python3", "/lib", "/usr/lib", "/bin", "/usr/bin"]


class SandlockSandbox:
    """Sandlock-based sandbox for kernel-level isolated code execution.
    
    Uses Landlock and seccomp-bpf for filesystem and syscall isolation.
    Provides the strongest security guarantees available on Linux systems.
    
    Security features:
    - Kernel-enforced filesystem allowlisting (Landlock)
    - Network domain/port control
    - Memory, process, CPU, and fd limits
    - Syscall filtering (seccomp-bpf)
    - ~5ms overhead, no Docker, no root required
    
    Example:
        from praisonai_sandbox import SandlockSandbox
        from praisonaiagents.sandbox import ResourceLimits
        
        sandbox = SandlockSandbox()
        limits = ResourceLimits.minimal()  # Strict limits for untrusted code
        result = await sandbox.execute("print('Hello, World!')", limits=limits)
        print(result.stdout)  # Hello, World!
    """
    
    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the sandlock sandbox.
        
        Args:
            config: Optional sandbox configuration
            
        Raises:
            ImportError: If sandlock package is not available
            RuntimeError: If Landlock is not supported on this system
        """
        self.config = config or SandboxConfig.native()
        self._is_running = False
        self._temp_dir: Optional[str] = None
        self._used_subprocess_fallback = False
        
        # Lazy import sandlock to avoid import-time dependency
        try:
            import sandlock
            self._sandlock = sandlock
        except ImportError:
            raise ImportError(
                "sandlock package required for SandlockSandbox. "
                "Install with: pip install 'praisonai[sandbox]' or pip install sandlock"
            )

        # Fail loud if Landlock isn't supported on this kernel.  sandlock
        # requires a minimum Landlock ABI (currently v6, which shipped in
        # Linux 6.12); query it rather than hard-coding so we track the SDK's
        # own requirement.
        try:
            abi = self._sandlock.landlock_abi_version()
            min_abi = self._sandlock.min_landlock_abi()
        except Exception as e:
            raise RuntimeError(
                f"failed to query Landlock ABI version: {e}"
            ) from e
        if abi < min_abi:
            raise RuntimeError(
                "SandlockSandbox requires Landlock ABI >= "
                f"{min_abi} (Linux kernel >= 6.12 with "
                "CONFIG_SECURITY_LANDLOCK=y).  This kernel reports Landlock "
                f"ABI version {abi}.  Use SubprocessSandbox explicitly if "
                "weaker isolation is acceptable."
            )
        self._require_enforceable()

    def _require_enforceable(self) -> None:
        """Landlock grants whole trees: a blocked path inside a granted one is unkeepable."""
        from ._enforce import require_enforceable
        from ._policy import _resolve, _within

        policy = self.config.security_policy
        granted = [_resolve(p) for p in (*_READ_ROOTS, *policy.allowed_paths) if os.path.exists(p)]
        problems = [f"blocked_paths=[{b!r}] (overlaps {g})" for b in policy.blocked_paths
                    for g in granted if _within(_resolve(b), g) or _within(g, _resolve(b))]
        require_enforceable("SandlockSandbox", problems,
                            "Landlock can only allow whole directories; narrow allowed_paths.")

    def _validate_command_against_policy(self, cmd, policy, cwd=None) -> Optional[str]:
        from ._policy import screen_command

        return screen_command(cmd, policy, cwd or self._temp_dir, roots=[self._temp_dir])

    def _policy_error(self, cmd: List[str], working_dir: Optional[str]) -> Optional[str]:
        """Screen *cmd* and confine a caller-chosen working_dir; None when allowed."""
        from ._policy import _resolve, _within
        from .subprocess import SubprocessSandbox

        policy = self.config.security_policy
        roots = [self._temp_dir, *policy.allowed_paths]
        if working_dir and not any(r and _within(_resolve(working_dir), _resolve(r)) for r in roots):
            return f"working_dir {working_dir!r} is outside the sandbox and SecurityPolicy.allowed_paths"
        if cmd[:2] == ["python3", "-c"]:
            return SubprocessSandbox._validate_code_against_policy(self, cmd[2], "python", policy)
        return self._validate_command_against_policy(cmd, policy, working_dir)

    @property
    def is_available(self) -> bool:
        """Whether sandlock backend is available."""
        try:
            return self._sandlock.landlock_abi_version() >= self._sandlock.min_landlock_abi()
        except (AttributeError, ImportError):
            return False
    
    @property
    def sandbox_type(self) -> str:
        return "sandlock"
    
    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        if self._is_running:
            return
        
        self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandlock_")
        self._is_running = True
        logger.info("Sandlock sandbox initialized with Landlock isolation")
    
    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        if not self._is_running:
            return
        
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        
        self._is_running = False
        logger.info("Sandlock sandbox stopped")
    
    def _build_sandbox_kwargs(
        self,
        limits: ResourceLimits,
        working_dir: Optional[str] = None,
        extra_readable: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build sandlock ``Sandbox`` keyword arguments from resource limits.

        sandlock dropped the separate ``Policy`` object; configuration is now
        passed directly to ``Sandbox(**kwargs)``.  This returns that kwargs
        dict.

        Args:
            limits: Resource limits configuration
            working_dir: Working directory for execution (added to the
                writable allowlist).
            extra_readable: Additional directories to add to the Landlock
                read allowlist (e.g. the parent of a script passed to
                ``execute_file``).
        """
        # Landlock requires every path in the allowlist to exist at rule-
        # attach time; passing a missing directory makes sandlock_spawn
        # fail outright.  Filter to paths that actually exist on this host.
        allowed_read_paths = [p for p in _READ_ROOTS if os.path.isdir(p)]
        if extra_readable:
            # extra_readable may name individual files (e.g. the single script
            # passed to execute_file), so accept any path that exists — not
            # just directories.  Landlock grants read on a named file without
            # exposing its siblings.
            allowed_read_paths.extend(
                p for p in extra_readable if os.path.exists(p)
            )

        policy = self.config.security_policy
        allowed_write_paths = []
        allowed_read_paths += [p for p in policy.allowed_paths if os.path.isdir(p)]
        if working_dir:
            allowed_write_paths.append(working_dir)
        if self._temp_dir:
            allowed_write_paths.append(self._temp_dir)

        # Landlock does not imply read access from write access: a path that
        # is only in fs_writable can be written but not read back.  The
        # sandboxed process needs to read its own working directory (e.g. to
        # import a file it just wrote, or to stat the cwd), so mirror the
        # writable dirs into the read allowlist.  De-duplicate to keep the
        # rule set minimal.
        for p in (working_dir, self._temp_dir):
            if p and os.path.isdir(p) and p not in allowed_read_paths:
                allowed_read_paths.append(p)

        allowed_write_paths.extend(policy.allowed_paths)
        if not policy.allow_file_write:
            allowed_write_paths = []  # Landlock: read-only everywhere
        
        # Network policy.
        #
        # sandlock collapsed network config into a single ``net_allow``
        # endpoint allowlist:
        #   []                    -> deny all outbound (the default)
        #   ["*:*", ...]          -> allow rules; "*:*" = any TCP host:port
        #
        # Protocol gating falls out of rule presence: with no UDP rule, UDP
        # sockets are denied at the seccomp layer.  To make an enabled network
        # actually usable we open all outbound TCP plus UDP DNS (port 53) so
        # the sandboxed process can resolve hostnames.  To block the network
        # we leave the allowlist empty (deny all).
        if limits.network_enabled and policy.allow_network:
            net_allow = ["*:*", "udp://*:53"]
        else:
            net_allow = []

        return {
            # Filesystem restrictions (Landlock)
            "fs_readable": allowed_read_paths,
            "fs_writable": allowed_write_paths,

            # Resource limits
            "max_memory": f"{limits.memory_mb}M",
            "max_processes": limits.max_processes,
            "max_open_files": limits.max_open_files,
            # max_cpu is a throttle percentage of one core, not a time budget.
            # Execution timeout is handled via Sandbox.run(timeout=...).
            "max_cpu": limits.cpu_percent,

            # Network (deny-all by default)
            "net_allow": net_allow,

            # Environment isolation.  sandlock inherits the parent's FULL
            # environment when clean_env is False (its default), which would
            # leak host secrets (SECRET_KEY, DATABASE_URL, ...) into untrusted
            # sandboxed code.  Force a minimal baseline (PATH/HOME/USER/TERM/
            # LANG) instead — mirroring SubprocessSandbox, which likewise
            # refuses to copy the host environment.  Per-call ``env`` is
            # layered on top of this baseline by _run_sandlocked.
            "clean_env": True,
        }

    @staticmethod
    def _decode(buf: Any) -> str:
        """Decode a sandlock Result stdout/stderr buffer to str.

        sandlock returns ``bytes`` from ``Sandbox.run()``; PraisonAI's
        ``SandboxResult`` uses ``str`` throughout.  Invalid UTF-8 is
        replaced rather than raised so downstream consumers never see
        binary artefacts.
        """
        if isinstance(buf, bytes):
            return buf.decode("utf-8", errors="replace")
        return buf or ""

    def _safe_sandbox_path(self, path: str) -> Optional[str]:
        """Resolve a caller-supplied path to an absolute path inside _temp_dir.

        Returns None if the resolved path would escape the sandbox root,
        preventing path-traversal attacks via sequences like ``../../etc/passwd``.
        """
        if not self._temp_dir:
            return None
        # Join, then resolve symlinks / ".." components
        candidate = os.path.realpath(
            os.path.join(self._temp_dir, path.lstrip("/"))
        )
        sandbox_root = os.path.realpath(self._temp_dir)
        # Allow the sandbox root itself (e.g. list_files("/")) or any path inside it.
        if candidate != sandbox_root and not candidate.startswith(sandbox_root + os.sep):
            logger.warning("Path traversal attempt blocked: %s", path)
            return None
        return candidate

    async def _run_sandlocked(
        self,
        cmd: List[str],
        execution_id: str,
        limits: ResourceLimits,
        env: Optional[Dict[str, str]],
        working_dir: Optional[str],
        extra_readable: Optional[List[str]] = None,
    ) -> SandboxResult:
        """Execute *cmd* inside a sandlock Sandbox and return a SandboxResult.

        Centralises all sandlock Sandbox construction and error handling so
        that ``execute`` and ``run_command`` share a single code path.

        ``env`` variables are layered on top of the clean baseline
        environment established in _build_sandbox_kwargs (clean_env=True),
        so the child never inherits the host's full environment.  An
        explicit empty dict is honoured as "no overrides" — distinct from
        ``None`` only in intent, since the baseline is minimal either way.
        ``working_dir`` is applied to the sandbox config (added to the
        writable-path allow-list).
        """
        self._require_enforceable()
        policy_error = self._policy_error(cmd, working_dir)
        if policy_error:
            return SandboxResult(execution_id=execution_id, status=SandboxStatus.FAILED,
                                 error=f"Security policy violation: {policy_error}")
        sandbox_kwargs = self._build_sandbox_kwargs(
            limits, working_dir, extra_readable
        )
        if env is not None:
            sandbox_kwargs["env"] = dict(env)

        started_at = time.time()

        def _run() -> Any:
            # Context manager ensures the sandbox handle is released even
            # if .run() raises partway through.
            with self._sandlock.Sandbox(**sandbox_kwargs) as sb:
                return sb.run(cmd, timeout=limits.timeout_seconds)

        try:
            result = await asyncio.get_running_loop().run_in_executor(None, _run)
        except Exception as e:  # noqa: BLE001 — broad catch keeps the sandbox
            # resilient: any sandlock/spawn failure is surfaced as a FAILED
            # result rather than propagating.  Log the full traceback so the
            # underlying cause isn't lost.
            logger.exception("sandlock execution failed for %s", execution_id)
            completed_at = time.time()
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=f"Execution failed: {e}",
                duration_seconds=completed_at - started_at,
                started_at=started_at,
                completed_at=completed_at,
            )

        completed_at = time.time()
        duration = completed_at - started_at
        cap = self.config.security_policy.max_output_size
        stdout, stderr = (self._decode(b[:cap] + b"\n[OUTPUT TRUNCATED]" if cap and isinstance(
            b, bytes) and len(b) > cap else b) for b in (result.stdout, result.stderr))

        # sandlock uses exit_code == -1 as the ExitStatus::Timeout sentinel
        # (see sandlock's python/src/sandlock/_sdk.py).  This is a
        # structural signal — Sandbox.run() doesn't populate result.error
        # for timeouts, so string-matching on it is unreliable.
        if result.success:
            status = SandboxStatus.COMPLETED
            error = None
        elif result.exit_code == -1:
            status = SandboxStatus.TIMEOUT
            error = f"Execution timed out after {limits.timeout_seconds}s"
        else:
            status = SandboxStatus.FAILED
            error = f"Execution failed with exit code {result.exit_code}: {stderr}"

        return SandboxResult(
            execution_id=execution_id,
            status=status,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            started_at=started_at,
            completed_at=completed_at,
            error=error,
            metadata={
                "sandbox_type": "sandlock",
                "landlock_enabled": True,
                "seccomp_enabled": True,
            },
        )

    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Execute code in the sandlock-isolated sandbox."""
        if not self._is_running:
            await self.start()

        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())

        if language == "bash":
            cmd = ["bash", "-c", code]
        else:
            cmd = ["python3", "-c", code]
        
        return await self._run_sandlocked(
            cmd,
            execution_id=execution_id,
            limits=limits,
            env=env,
            working_dir=working_dir or self._temp_dir,
        )
    
    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a file in the sandbox.

        The script is passed to the interpreter by path rather than slurped
        through ``-c``, so large scripts don't hit ARG_MAX.  Only the script
        file itself — not its parent directory — is added to the Landlock
        read allowlist, so sibling files on the host are never exposed.
        """
        if not self._is_running:
            await self.start()

        if not os.path.exists(file_path):
            return SandboxResult(
                status=SandboxStatus.FAILED,
                error=f"File not found: {file_path}",
            )

        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())

        abs_path = os.path.realpath(file_path)
        interp = "bash" if file_path.endswith((".sh", ".bash")) else "python3"
        cmd: List[str] = [interp, abs_path]
        if args:
            cmd.extend(args)

        return await self._run_sandlocked(
            cmd,
            execution_id=execution_id,
            limits=limits,
            env=env,
            working_dir=self._temp_dir,
            extra_readable=[abs_path],
        )
    
    async def run_command(
        self,
        command: Union[str, List[str]],
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Run a shell command in the sandbox."""
        if not self._is_running:
            await self.start()

        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())

        if isinstance(command, str):
            cmd = ["sh", "-c", command]
        else:
            cmd = list(command)
        
        return await self._run_sandlocked(
            cmd,
            execution_id=execution_id,
            limits=limits,
            env=env,
            working_dir=working_dir or self._temp_dir,
        )
    
    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file to the sandbox, never following a symlink the sandboxed code made."""
        from ._compat import write_in_sandbox

        return write_in_sandbox(self._temp_dir, path, content)

    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file from the sandbox, never following a symlink the sandboxed code made."""
        from ._compat import read_in_sandbox

        return read_in_sandbox(self._temp_dir, path)

    async def list_files(
        self,
        path: str = "/",
    ) -> List[str]:
        """List files in a sandbox directory."""
        full_path = self._safe_sandbox_path(path)
        if full_path is None or not os.path.exists(full_path):
            return []
        
        try:
            files = []
            for root, dirs, filenames in os.walk(full_path):
                for filename in filenames:
                    rel_path = os.path.relpath(
                        os.path.join(root, filename),
                        self._temp_dir,
                    )
                    files.append("/" + rel_path)
            return files
        except Exception:
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get sandbox status information."""
        kernel_isolated = self.is_available and not self._used_subprocess_fallback
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "temp_dir": self._temp_dir,
            "landlock_supported": self.is_available,
            "subprocess_fallback": self._used_subprocess_fallback,
            "features": {
                "filesystem_isolation": kernel_isolated,
                "network_isolation": kernel_isolated,
                "syscall_filtering": kernel_isolated,
                "resource_limits": True,
            }
        }
    
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandlock_")
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        await self.stop()
        await self.start()
