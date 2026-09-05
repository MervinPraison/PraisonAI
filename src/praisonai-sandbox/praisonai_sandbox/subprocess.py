"""
Subprocess Sandbox implementation for PraisonAI.

Provides isolated code execution using subprocess with resource limits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
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
        from praisonai_sandbox import SubprocessSandbox
        
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

        # Always pass a minimal PATH (so python resolves) — never the host's.
        env.setdefault(
            "PATH",
            os.pathsep.join(
                p for p in (
                    os.path.dirname(sys.executable) if sys.executable else "",
                    "/usr/local/bin", "/usr/bin", "/bin",
                )
                if p
            ),
        )
        # HOME uses temp_dir which is set during start() - /tmp is defensive fallback  # noqa: S108
        env.setdefault("HOME", self._temp_dir or "/tmp")
        return env
    
    def _validate_command_against_policy(
        self,
        cmd: List[str],
        policy: SecurityPolicy,
    ) -> Optional[str]:
        """Return an error message when *cmd* violates *policy*."""
        if not cmd:
            return "Empty command"

        from ._shell import strip_heredoc_bodies

        # A quoted heredoc body is file content, not a command. Leaving it in
        # made write_file() reject any file whose text happened to contain a
        # blocked pattern.
        cmd_str = strip_heredoc_bodies(" ".join(cmd))
        for blocked in policy.blocked_commands:
            if blocked and blocked in cmd_str:
                return f"Blocked command pattern: {blocked}"

        if policy.allowed_commands:
            base_cmd = os.path.basename(cmd[0])
            allowed = {c.split()[0] for c in policy.allowed_commands}
            if base_cmd not in allowed and cmd[0] not in policy.allowed_commands:
                return f"Command not in allowlist: {base_cmd}"

        if not policy.allow_subprocess:
            shell_bins = {"sh", "bash", "dash", "zsh", "csh", "ksh", "cmd", "powershell"}
            if os.path.basename(cmd[0]) in shell_bins:
                return "Subprocess execution is disabled by security policy"

        # Scan the shell payload too: with shell=True the real path lives
        # inside `sh -c "..."`, where a plain argv walk cannot see it.
        from ._shell import policy_scan_parts

        for part in policy_scan_parts([strip_heredoc_bodies(c) for c in cmd]):
            if not part.startswith(("/", "~", ".")):
                continue
            expanded = os.path.realpath(os.path.expanduser(part))
            for blocked_path in policy.blocked_paths:
                blocked_abs = os.path.realpath(os.path.expanduser(blocked_path))
                if expanded == blocked_abs or expanded.startswith(blocked_abs + os.sep):
                    return f"Access to blocked path: {blocked_path}"
            if policy.allowed_paths:
                allowed = any(
                    expanded == os.path.realpath(os.path.expanduser(p))
                    or expanded.startswith(os.path.realpath(os.path.expanduser(p)) + os.sep)
                    for p in policy.allowed_paths
                )
                if not allowed:
                    return f"Path not in allowlist: {part}"
        return None
    
    def _apply_rlimits(self, limits: ResourceLimits):
        """Apply resource limits via POSIX setrlimit (Linux/macOS only)."""
        if os.name != "posix":
            logger.warning("Resource limits not supported on Windows - sandbox isolation is weaker")
            return
            
        try:
            import resource
        except ImportError:
            logger.warning("Resource module not available - resource limits not enforced")
            return

        import sys

        # Each limit gets its own try/except. One shared block meant the first
        # failure skipped the rest -- and RLIMIT_AS always fails on macOS, so a
        # single unsupported limit silently voided NPROC and NOFILE too.
        wanted = []
        if limits.memory_mb and limits.memory_mb > 0:
            # RLIMIT_AS is unlimited-by-default on Darwin and raises
            # "current limit exceeds maximum limit"; skip rather than warn.
            if sys.platform != "darwin":
                bytes_ = limits.memory_mb * 1024 * 1024
                wanted.append(("RLIMIT_AS", resource.RLIMIT_AS, (bytes_, bytes_)))
        # RLIMIT_NPROC is deliberately NOT set. POSIX defines it per *real user
        # ID*, not per process tree, so a value like max_processes=10 counts
        # every process the user already has running -- the sandbox then cannot
        # fork at all and even `echo a | tr a-z A-Z` dies with
        # "sh: fork: Resource temporarily unavailable".
        # This was latent before: RLIMIT_AS raised first and skipped the rest,
        # so NPROC never applied. Capping a sandbox's process count needs a
        # cgroup or a container, not setrlimit.
        if limits.max_open_files and limits.max_open_files > 0:
            wanted.append(("RLIMIT_NOFILE", resource.RLIMIT_NOFILE,
                           (limits.max_open_files, limits.max_open_files)))
        # Note: RLIMIT_CPU is process CPU time, not wall clock - timeout is separate.

        for label, which, value in wanted:
            try:
                resource.setrlimit(which, value)
            except (OSError, ValueError) as e:
                # This runs inside the forked child, so a warning here lands in
                # the sandbox's stderr and is returned to the model as tool
                # output. Stay silent; the limit simply does not apply.
                logger.debug("Could not set %s: %s", label, e)
    
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
    
    def _validate_code_against_policy(
        self,
        code: str,
        language: str,
        policy: SecurityPolicy,
    ) -> Optional[str]:
        """Return an error message when *code* violates *policy*.

        blocked_imports was declared in SecurityPolicy, documented, and
        serialised by to_dict() -- and read by nothing. Only run_command()
        validated anything, and SandboxManager.run_code() goes through
        execute(), so the default backend enforced no policy at all: strict()
        still let code `import subprocess`, open a socket and read
        /etc/passwd, reporting COMPLETED / exit 0.

        Python is checked by parsing rather than substring matching, so a
        blocked name inside a string or comment is not a false positive. Code
        that will not parse is left to the interpreter to reject.

        Import bindings are resolved so aliases cannot slip a blocked call past
        the check: `import os as x; x.system(...)` and `from os import system;
        system(...)` both resolve back to `os.system`. Bare names are only
        flagged when they are read (a Load) -- `subprocess = 3` or
        `def f(eval): ...` bind a local of the same spelling and are harmless.
        """
        blocked = [b for b in (getattr(policy, "blocked_imports", None) or []) if b]
        if not blocked or language != "python":
            return None

        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return None

        # "os.system" in the list means the attribute call, not the os module.
        modules = {b for b in blocked if "." not in b}
        dotted = {b for b in blocked if "." in b}

        # Names used in call position -- `eval(...)` -- so a bare blocked builtin
        # is caught while a mere mention (`print(subprocess_count)`) is not.
        called_names = {
            n.func
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }

        # Resolve local bindings introduced by imports back to their real dotted
        # names, so an alias cannot spell a blocked call differently:
        #   import os as x        -> x     resolves to os
        #   from os import system -> system resolves to os.system
        # aliases: local name -> real module path (for attribute-call resolution)
        # from_binds: local name -> real dotted name (for bare-name calls)
        aliases: Dict[str, str] = {}
        from_binds: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    aliases[bound] = alias.name
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                for alias in node.names:
                    bound = alias.asname or alias.name
                    from_binds[bound] = f"{base}.{alias.name}" if base else alias.name

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if alias.name in modules or root in modules:
                        return f"Blocked import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if name in modules or name.split(".")[0] in modules:
                    return f"Blocked import: {name}"
                for alias in node.names:
                    if from_binds.get(alias.asname or alias.name) in dotted:
                        return f"Blocked import: {from_binds[alias.asname or alias.name]}"
            elif isinstance(node, ast.Attribute):
                target = node
                parts = []
                while isinstance(target, ast.Attribute):
                    parts.append(target.attr)
                    target = target.value
                if isinstance(target, ast.Name):
                    # Translate the root through any import alias so
                    # `import os as x; x.system()` resolves to os.system.
                    root_real = aliases.get(target.id, target.id)
                    parts.append(root_real)
                    full = ".".join(reversed(parts))
                    if full in dotted:
                        return f"Blocked call: {full}"
            elif isinstance(node, ast.Name):
                # Only a *read* of the name is a use; an assignment target or
                # parameter merely rebinds the spelling and is harmless.
                if not isinstance(node.ctx, ast.Load):
                    continue
                # A bare blocked name is only a threat when it is called:
                # `eval('1+1')` matters, `print(subprocess)` (where subprocess
                # is a local int or an unused mention) does not. Modules stay
                # dangerous solely via `import`, already handled above.
                if node in called_names and (node.id in modules or node.id in dotted):
                    return f"Blocked call: {node.id}"
                # from os import system; system() -> resolves to os.system
                if from_binds.get(node.id) in dotted:
                    return f"Blocked call: {from_binds[node.id]}"

        return None

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

        # Enforce the policy before the code is written or spawned. run_command()
        # has always validated; execute() -- the default backend, and the path
        # SandboxManager.run_code() takes -- validated nothing.
        policy = self.config.security_policy
        policy_error = self._validate_code_against_policy(code, language, policy)
        if policy_error:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                stdout="",
                stderr=f"Security policy violation: {policy_error}",
                exit_code=1,
                error=f"Security policy violation: {policy_error}",
            )

        code_file = os.path.join(self._temp_dir, f"code_{execution_id}.py")
        with open(code_file, "w") as f:
            f.write(code)
        
        python_exe = sys.executable or "python"
        if language == "python":
            cmd = [python_exe, code_file]
        elif language == "bash":
            cmd = ["bash", code_file]
        else:
            cmd = [python_exe, code_file]
        
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

        policy = self.config.security_policy
        policy_error = self._validate_command_against_policy(cmd, policy)
        if policy_error:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=policy_error,
            )
        
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
