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
        from praisonai.sandbox import SandlockSandbox
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
        
        # Lazy import sandlock to avoid import-time dependency
        try:
            import sandlock
            self._sandlock = sandlock
        except ImportError:
            raise ImportError(
                "sandlock package required for SandlockSandbox. "
                "Install with: pip install 'praisonai[sandbox]' or pip install sandlock"
            )

        # Fail loud if Landlock isn't supported on this kernel.
        try:
            abi = self._sandlock.landlock_abi_version()
        except Exception as e:
            raise RuntimeError(
                f"failed to query Landlock ABI version: {e}"
            ) from e
        if abi < 1:
            raise RuntimeError(
                "SandlockSandbox requires Landlock support (Linux kernel "
                ">= 6.12 with CONFIG_SECURITY_LANDLOCK=y).  This kernel "
                f"reports Landlock ABI version {abi}.  Use SubprocessSandbox "
                "explicitly if weaker isolation is acceptable."
            )
    
    @property
    def is_available(self) -> bool:
        """Whether sandlock backend is available."""
        try:
            return self._sandlock.landlock_abi_version() >= 1
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
    
    def _create_policy(
        self,
        limits: ResourceLimits,
        working_dir: Optional[str] = None,
        extra_readable: Optional[List[str]] = None,
    ) -> Any:
        """Create sandlock policy from resource limits.

        Args:
            limits: Resource limits configuration
            working_dir: Working directory for execution (added to the
                writable allowlist).
            extra_readable: Additional directories to add to the Landlock
                read allowlist (e.g. the parent of a script passed to
                ``execute_file``).
        """
        Policy = self._sandlock.Policy

        # Landlock requires every path in the allowlist to exist at rule-
        # attach time; passing a missing directory makes sandlock_spawn
        # fail outright.  Filter to paths that actually exist on this host.
        _candidate_read_paths = [
            "/usr/lib/python3",
            "/usr/local/lib/python3",
            "/lib",
            "/usr/lib",
            "/bin",
            "/usr/bin",
        ]
        allowed_read_paths = [p for p in _candidate_read_paths if os.path.isdir(p)]
        if extra_readable:
            allowed_read_paths.extend(
                p for p in extra_readable if os.path.isdir(p)
            )

        allowed_write_paths = []
        if working_dir:
            allowed_write_paths.append(working_dir)
        if self._temp_dir:
            allowed_write_paths.append(self._temp_dir)

        # Add any configured allowed paths from security policy
        if hasattr(self.config, 'security_policy') and self.config.security_policy:
            allowed_write_paths.extend(self.config.security_policy.allowed_paths)
        
        # Network policy.
        #
        # sandlock uses tri-state semantics for net_allow_hosts:
        #   None           -> unrestricted (real /etc/hosts visible)
        #   []             -> deny all hosts (empty virtual /etc/hosts)
        #   ["host", ...]  -> allowlist
        #
        # TCP connectivity is governed separately by net_connect/net_bind,
        # both of which default to [] = deny all.  To enable network we must
        # explicitly open TCP ports; to block network we can rely on the
        # defaults AND additionally block DNS via net_allow_hosts=[].
        if limits.network_enabled:
            net_kwargs: Dict[str, Any] = {
                # Allow outbound TCP to any port; leave net_allow_hosts at
                # its default (None = /etc/hosts unrestricted).
                "net_connect": ["0-65535"],
            }
        else:
            net_kwargs = {
                # Empty allowlist -> no host resolvable via virtual /etc/hosts.
                # net_bind/net_connect default to [] = deny all TCP.
                "net_allow_hosts": [],
            }

        policy = Policy(
            # Filesystem restrictions (Landlock)
            fs_readable=allowed_read_paths,
            fs_writable=allowed_write_paths,

            # Resource limits
            max_memory=f"{limits.memory_mb}M",
            max_processes=limits.max_processes,
            max_open_files=limits.max_open_files,
            # max_cpu is a throttle percentage of one core, not a time budget.
            # Execution timeout is handled via Sandbox.run(timeout=...).
            max_cpu=limits.cpu_percent,

            **net_kwargs,
        )

        return policy

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
        # Ensure the resolved path is strictly inside the sandbox root (not equal to it)
        if not candidate.startswith(sandbox_root + os.sep):
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

        Centralises all sandlock Sandbox/Policy construction and error handling
        so that ``execute`` and ``run_command`` share a single code path.

        Note: ``env`` is accepted for API compatibility but sandlock's
        ``Sandbox.run()`` does not support per-run environment injection;
        callers requiring custom env vars should set them in the policy or
        prior to sandbox creation.  ``working_dir`` is applied via the policy
        (added to the writable-path allow-list).
        """
        policy = self._create_policy(limits, working_dir, extra_readable)

        started_at = time.time()

        def _run() -> Any:
            # Context manager ensures the sandbox handle is released even
            # if .run() raises partway through.
            with self._sandlock.Sandbox(policy) as sb:
                return sb.run(cmd, timeout=limits.timeout_seconds)

        try:
            result = await asyncio.get_running_loop().run_in_executor(None, _run)
        except Exception as e:
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
        stdout = self._decode(result.stdout)
        stderr = self._decode(result.stderr)

        # sandlock surfaces timeouts via result.error containing "timed out".
        # This is authoritative — wall-clock guesses are unreliable because a
        # process can legitimately finish just under the limit.
        err_text = (result.error or "") if not result.success else ""
        is_timeout = "timed out" in err_text.lower() or "timeout" in err_text.lower()

        if result.success:
            status = SandboxStatus.COMPLETED
            error = None
        elif is_timeout:
            status = SandboxStatus.TIMEOUT
            error = f"Execution timed out after {limits.timeout_seconds}s"
        else:
            status = SandboxStatus.FAILED
            error = f"Execution failed with exit code {result.exit_code}: {stderr or err_text}"

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
        through ``-c``, so large scripts don't hit ARG_MAX.  The file's
        parent directory is added to the Landlock read allowlist for this
        run so the sandboxed process can actually open it.
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
            extra_readable=[os.path.dirname(abs_path)],
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
        """Write a file to the sandbox."""
        full_path = self._safe_sandbox_path(path)
        if full_path is None:
            return False
        
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        try:
            mode = "wb" if isinstance(content, bytes) else "w"
            with open(full_path, mode) as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            return False
    
    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file from the sandbox."""
        full_path = self._safe_sandbox_path(path)
        if full_path is None or not os.path.exists(full_path):
            return None
        
        try:
            with open(full_path, "r") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(full_path, "rb") as f:
                return f.read()
        except Exception:
            return None
    
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
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "temp_dir": self._temp_dir,
            "landlock_supported": self.is_available,
            "features": {
                "filesystem_isolation": True,
                "network_isolation": True,
                "syscall_filtering": True,
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
