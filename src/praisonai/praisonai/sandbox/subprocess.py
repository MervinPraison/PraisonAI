"""
Subprocess Sandbox implementation for PraisonAI.

Provides isolated code execution using subprocess with resource limits.
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
from praisonaiagents.sandbox.config import SecurityPolicy

logger = logging.getLogger(__name__)


class SubprocessSandbox:
    """Subprocess-based sandbox for code execution.
    
    Executes code in isolated subprocesses with timeout limits.
    Less secure than Docker but works without Docker installation.
    
    Example:
        from praisonai.sandbox import SubprocessSandbox
        
        sandbox = SubprocessSandbox()
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    """
    
    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the subprocess sandbox.
        
        Args:
            config: Optional sandbox configuration
        """
        self.config = config or SandboxConfig.subprocess()
        self._is_running = False
        self._temp_dir: Optional[str] = None
    
    def _build_child_env(self, policy: SecurityPolicy, overrides: Dict[str, str] | None) -> Dict[str, str]:
        """Construct a minimal, policy-driven env for the child process."""
        # Start with the explicit env from SandboxConfig and the per-call overrides only.
        env = dict(self.config.env)
        if overrides:
            env.update(overrides)

        # If the policy allows network, pass through proxy-related vars so the child can
        # reach the outside world; otherwise withhold them.
        if policy.allow_network:
            for var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy",
                        "https_proxy", "no_proxy"):
                if var in os.environ:
                    env[var] = os.environ[var]

        # Always pass a minimal PATH (so /usr/bin/python resolves) — never the host's.
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        # HOME uses temp_dir which is set during start() - /tmp is defensive fallback  # noqa: S108
        env.setdefault("HOME", self._temp_dir or "/tmp")
        return env
    
    def _apply_rlimits(self, limits: ResourceLimits):
        """Apply resource limits via POSIX setrlimit (Linux/macOS only)."""
        if os.name != "posix":
            logger.warning("Resource limits not supported on Windows - sandbox isolation is weaker")
            return
            
        try:
            import resource
            if limits.memory_mb and limits.memory_mb > 0:
                bytes_ = limits.memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (bytes_, bytes_))
            if limits.max_processes and limits.max_processes > 0:
                resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))
            if limits.max_open_files and limits.max_open_files > 0:
                resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files))
            # Note: RLIMIT_CPU is process CPU time, not wall clock time - timeout is handled separately
        except ImportError:
            logger.warning("Resource module not available - resource limits not enforced")
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to set resource limits: {e}")
    
    @property
    def is_available(self) -> bool:
        """Subprocess sandbox is always available."""
        return True
    
    @property
    def sandbox_type(self) -> str:
        return "subprocess"
    
    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        if self._is_running:
            return
        
        self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandbox_")
        self._is_running = True
        logger.info("Subprocess sandbox initialized")
    
    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        if not self._is_running:
            return
        
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        
        self._is_running = False
        logger.info("Subprocess sandbox stopped")
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Execute code in the sandbox."""
        if not self._is_running:
            await self.start()
        
        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())
        
        code_file = os.path.join(self._temp_dir, f"code_{execution_id}.py")
        with open(code_file, "w") as f:
            f.write(code)
        
        if language == "python":
            cmd = ["python", code_file]
        elif language == "bash":
            cmd = ["bash", code_file]
        else:
            cmd = ["python", code_file]
        
        # Build environment based on security policy instead of copying host environment
        process_env = self._build_child_env(self.config.security_policy, env)
        
        started_at = time.time()
        
        # preexec_fn is POSIX-only; omit on Windows
        popen_kwargs = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": working_dir or self._temp_dir,
            "env": process_env,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
            popen_kwargs["preexec_fn"] = lambda: self._apply_rlimits(limits)
        else:
            logger.warning("Resource limits and session isolation not available on Windows")

        try:
            proc = await asyncio.create_subprocess_exec(*cmd, **popen_kwargs)
            
            try:
                # Truncate output to max_output_size after reading
                max_output_size = self.config.security_policy.max_output_size
                
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds,
                )
                
                # Truncate output if it exceeds max_output_size
                if max_output_size and max_output_size > 0:
                    if len(stdout) > max_output_size:
                        stdout = stdout[:max_output_size] + b"\n[OUTPUT TRUNCATED]"
                    if len(stderr) > max_output_size:
                        stderr = stderr[:max_output_size] + b"\n[OUTPUT TRUNCATED]"
                
                completed_at = time.time()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.COMPLETED,
                    exit_code=proc.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_seconds=completed_at - started_at,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            except asyncio.TimeoutError:
                # Kill the whole process group, not just the leader
                try:
                    if os.name == "posix":
                        import signal
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except (ProcessLookupError, PermissionError, OSError):
                    proc.kill()
                await proc.wait()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.TIMEOUT,
                    error=f"Execution timed out after {limits.timeout_seconds}s",
                    duration_seconds=limits.timeout_seconds,
                    started_at=started_at,
                    completed_at=time.time(),
                )
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
        finally:
            if os.path.exists(code_file):
                os.remove(code_file)
    
    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a file in the sandbox."""
        if not os.path.exists(file_path):
            return SandboxResult(
                status=SandboxStatus.FAILED,
                error=f"File not found: {file_path}",
            )
        
        with open(file_path, "r") as f:
            code = f.read()
        
        return await self.execute(code, limits=limits, env=env)
    
    async def run_command(
        self,
        command: Union[str, List[str]],
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
        shell: bool = False,
    ) -> SandboxResult:
        """Run a command in the sandbox.
        
        Args:
            command: String command or list of arguments
            limits: Resource limits to apply
            env: Environment variables
            working_dir: Working directory
            shell: If True, explicitly use shell. If False (default), execute safely without shell.
        """
        if not self._is_running:
            await self.start()
        
        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())
        
        # Import here to avoid circular import
        from ._shell import build_argv
        cmd = build_argv(command, shell=shell)
        
        # Build environment based on security policy instead of copying host environment
        process_env = self._build_child_env(self.config.security_policy, env)
        
        started_at = time.time()
        
        # preexec_fn is POSIX-only; omit on Windows
        popen_kwargs = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": working_dir or self._temp_dir,
            "env": process_env,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
            popen_kwargs["preexec_fn"] = lambda: self._apply_rlimits(limits)
        else:
            logger.warning("Resource limits and session isolation not available on Windows")

        try:
            proc = await asyncio.create_subprocess_exec(*cmd, **popen_kwargs)
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds,
                )
                
                # Truncate output if it exceeds max_output_size
                max_output_size = self.config.security_policy.max_output_size
                if max_output_size and max_output_size > 0:
                    if len(stdout) > max_output_size:
                        stdout = stdout[:max_output_size] + b"\n[OUTPUT TRUNCATED]"
                    if len(stderr) > max_output_size:
                        stderr = stderr[:max_output_size] + b"\n[OUTPUT TRUNCATED]"
                
                completed_at = time.time()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.COMPLETED,
                    exit_code=proc.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_seconds=completed_at - started_at,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            except asyncio.TimeoutError:
                # Kill the whole process group, not just the leader
                try:
                    if os.name == "posix":
                        import signal
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except (ProcessLookupError, PermissionError, OSError):
                    proc.kill()
                await proc.wait()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.TIMEOUT,
                    error=f"Command timed out after {limits.timeout_seconds}s",
                    duration_seconds=limits.timeout_seconds,
                    started_at=started_at,
                    completed_at=time.time(),
                )
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
    
    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file to the sandbox."""
        from ._compat import safe_sandbox_path
        
        full_path = safe_sandbox_path(self._temp_dir, path)
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
        from ._compat import safe_sandbox_path
        
        full_path = safe_sandbox_path(self._temp_dir, path)
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
        from ._compat import safe_sandbox_path
        
        full_path = safe_sandbox_path(self._temp_dir, path)
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
        }
    
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandbox_")
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        await self.stop()
        await self.start()
