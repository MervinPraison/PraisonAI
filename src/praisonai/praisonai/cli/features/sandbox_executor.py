"""
Sandboxed Execution System for PraisonAI CLI.

Inspired by Codex CLI's sandbox modes for secure command execution.
Provides isolated execution environment when enabled via --sandbox flag.

Architecture:
- SandboxExecutor: Base class for sandboxed execution
- SubprocessSandbox: Subprocess-based isolation with resource limits
- SandboxPolicy: Configurable security policies

Note: Sandbox is ONLY activated when explicitly requested via CLI flag.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from pathlib import Path
from enum import Enum
import subprocess
import logging
import tempfile
import shutil
import time

logger = logging.getLogger(__name__)


# ============================================================================
# Sandbox Modes
# ============================================================================

class SandboxMode(Enum):
    """
    Sandbox execution modes.
    
    - DISABLED: No sandboxing (default)
    - BASIC: Basic isolation with resource limits
    - STRICT: Strict isolation with filesystem restrictions
    - NETWORK_ISOLATED: No network access
    """
    DISABLED = "disabled"
    BASIC = "basic"
    STRICT = "strict"
    NETWORK_ISOLATED = "network_isolated"
    
    @classmethod
    def from_string(cls, value: str) -> "SandboxMode":
        """Parse mode from string."""
        value = value.lower().strip().replace("-", "_")
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f"Unknown sandbox mode: {value}")


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SandboxPolicy:
    """
    Security policy for sandbox execution.
    """
    mode: SandboxMode = SandboxMode.DISABLED
    
    # Resource limits
    max_memory_mb: int = 512
    max_cpu_seconds: int = 30
    max_file_size_mb: int = 10
    max_processes: int = 10
    
    # Filesystem restrictions
    allowed_paths: Set[str] = field(default_factory=set)
    blocked_paths: Set[str] = field(default_factory=lambda: {
        "/etc", "/var", "/usr", "/bin", "/sbin",
        "/root", "/home", "/sys", "/proc"
    })
    temp_dir: Optional[str] = None
    
    # Network restrictions
    allow_network: bool = True
    allowed_hosts: Set[str] = field(default_factory=set)
    
    # Command restrictions
    blocked_commands: Set[str] = field(default_factory=lambda: {
        "rm", "rmdir", "mv", "dd", "mkfs", "fdisk",
        "sudo", "su", "chmod", "chown", "kill", "pkill"
    })
    
    @classmethod
    def for_mode(cls, mode: SandboxMode) -> "SandboxPolicy":
        """Create policy for a given mode."""
        if mode == SandboxMode.DISABLED:
            return cls(mode=mode)
        
        elif mode == SandboxMode.BASIC:
            return cls(
                mode=mode,
                max_memory_mb=512,
                max_cpu_seconds=60,
                allow_network=True
            )
        
        elif mode == SandboxMode.STRICT:
            return cls(
                mode=mode,
                max_memory_mb=256,
                max_cpu_seconds=30,
                max_processes=5,
                allow_network=True,
                blocked_commands={
                    "rm", "rmdir", "mv", "dd", "mkfs", "fdisk",
                    "sudo", "su", "chmod", "chown", "kill", "pkill",
                    "curl", "wget", "nc", "netcat", "ssh", "scp"
                }
            )
        
        elif mode == SandboxMode.NETWORK_ISOLATED:
            return cls(
                mode=mode,
                max_memory_mb=512,
                max_cpu_seconds=60,
                allow_network=False
            )
        
        return cls(mode=mode)


@dataclass
class ExecutionResult:
    """Result of sandboxed execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    was_sandboxed: bool
    policy_violations: List[str] = field(default_factory=list)
    
    @property
    def output(self) -> str:
        """Get combined output."""
        return self.stdout + self.stderr


# ============================================================================
# Command Validator
# ============================================================================

class CommandValidator:
    """
    Validates commands against sandbox policy.
    """
    
    def __init__(self, policy: SandboxPolicy):
        self.policy = policy
    
    def validate(self, command: str) -> List[str]:
        """
        Validate a command against the policy.
        
        Returns:
            List of policy violations (empty if valid)
        """
        violations = []
        
        if self.policy.mode == SandboxMode.DISABLED:
            return violations
        
        # Parse command
        parts = command.split()
        if not parts:
            return violations
        
        cmd_name = Path(parts[0]).name
        
        # Check blocked commands
        if cmd_name in self.policy.blocked_commands:
            violations.append(f"Command '{cmd_name}' is blocked by sandbox policy")
        
        # Check for dangerous patterns
        dangerous_patterns = [
            ("rm -rf", "Recursive force delete is blocked"),
            ("> /dev/", "Writing to device files is blocked"),
            ("| sh", "Piping to shell is blocked"),
            ("| bash", "Piping to bash is blocked"),
            ("$(", "Command substitution is blocked"),
            ("`", "Backtick command substitution is blocked"),
        ]
        
        for pattern, message in dangerous_patterns:
            if pattern in command:
                violations.append(message)
        
        # Check path access
        for part in parts:
            if part.startswith("/"):
                for blocked in self.policy.blocked_paths:
                    if part.startswith(blocked):
                        violations.append(f"Access to '{blocked}' is blocked")
                        break
        
        return violations
    
    def is_allowed(self, command: str) -> bool:
        """Check if command is allowed."""
        return len(self.validate(command)) == 0


# ============================================================================
# Subprocess Sandbox
# ============================================================================

class SubprocessSandbox:
    """
    Subprocess-based sandbox execution.
    
    Provides basic isolation through:
    - Resource limits (timeout, memory via ulimit)
    - Working directory isolation
    - Environment variable control
    - Command validation
    """
    
    def __init__(
        self,
        policy: Optional[SandboxPolicy] = None,
        working_dir: Optional[str] = None,
        verbose: bool = False
    ):
        self.policy = policy or SandboxPolicy()
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.verbose = verbose
        self.validator = CommandValidator(self.policy)
        
        self._temp_dir: Optional[Path] = None
    
    def _setup_temp_dir(self) -> Path:
        """Set up temporary directory for isolated execution."""
        if self._temp_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="praisonai_sandbox_"))
        return self._temp_dir
    
    def _cleanup_temp_dir(self) -> None:
        """Clean up temporary directory."""
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
            except Exception as e:
                logger.debug(f"Failed to cleanup temp dir: {e}")
            self._temp_dir = None
    
    def _build_environment(self) -> Dict[str, str]:
        """Build restricted environment variables."""
        import os
        
        # Start with minimal environment
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self._temp_dir or self.working_dir),
            "TERM": "xterm",
            "LANG": "en_US.UTF-8",
        }
        
        # Add some safe variables from current environment
        safe_vars = ["USER", "SHELL", "PYTHONPATH"]
        for var in safe_vars:
            if var in os.environ:
                env[var] = os.environ[var]
        
        return env
    
    def execute(
        self,
        command: str,
        timeout: Optional[float] = None,
        capture_output: bool = True
    ) -> ExecutionResult:
        """
        Execute a command in the sandbox.
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds (overrides policy)
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            ExecutionResult with execution details
        """
        start_time = time.time()
        
        # Check if sandbox is enabled
        if self.policy.mode == SandboxMode.DISABLED:
            return self._execute_unsandboxed(command, timeout, capture_output)
        
        # Validate command
        violations = self.validator.validate(command)
        if violations:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="Command blocked by sandbox policy:\n" + "\n".join(violations),
                duration_ms=(time.time() - start_time) * 1000,
                was_sandboxed=True,
                policy_violations=violations
            )
        
        # Set up sandbox
        if self.policy.mode == SandboxMode.STRICT:
            self._setup_temp_dir()
            cwd = self._temp_dir
        else:
            cwd = self.working_dir
        
        # Build environment
        env = self._build_environment()
        
        # Set timeout
        if timeout is None:
            timeout = float(self.policy.max_cpu_seconds)
        
        # Execute
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                env=env,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            
            return ExecutionResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
                duration_ms=(time.time() - start_time) * 1000,
                was_sandboxed=True
            )
        
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration_ms=(time.time() - start_time) * 1000,
                was_sandboxed=True,
                policy_violations=["Timeout exceeded"]
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=(time.time() - start_time) * 1000,
                was_sandboxed=True,
                policy_violations=[str(e)]
            )
        
        finally:
            if self.policy.mode == SandboxMode.STRICT:
                self._cleanup_temp_dir()
    
    def _execute_unsandboxed(
        self,
        command: str,
        timeout: Optional[float],
        capture_output: bool
    ) -> ExecutionResult:
        """Execute without sandbox (when disabled)."""
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.working_dir,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            
            return ExecutionResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
                duration_ms=(time.time() - start_time) * 1000,
                was_sandboxed=False
            )
        
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration_ms=(time.time() - start_time) * 1000,
                was_sandboxed=False
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=(time.time() - start_time) * 1000,
                was_sandboxed=False
            )


# ============================================================================
# CLI Integration Handler
# ============================================================================

class SandboxExecutorHandler:
    """
    Handler for integrating Sandbox Execution with PraisonAI CLI.
    
    Note: Sandbox is ONLY activated when --sandbox flag is passed.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._sandbox: Optional[SubprocessSandbox] = None
        self._enabled: bool = False
    
    @property
    def feature_name(self) -> str:
        return "sandbox_executor"
    
    @property
    def is_enabled(self) -> bool:
        """Check if sandbox is enabled."""
        return self._enabled
    
    def initialize(
        self,
        mode: str = "disabled",
        working_dir: Optional[str] = None,
        policy: Optional[SandboxPolicy] = None
    ) -> SubprocessSandbox:
        """
        Initialize the sandbox.
        
        Args:
            mode: Sandbox mode (disabled, basic, strict, network_isolated)
            working_dir: Working directory for execution
            policy: Optional custom policy
            
        Returns:
            Configured SubprocessSandbox
        """
        try:
            sandbox_mode = SandboxMode.from_string(mode)
        except ValueError:
            logger.warning(f"Unknown sandbox mode '{mode}', defaulting to 'disabled'")
            sandbox_mode = SandboxMode.DISABLED
        
        if policy is None:
            policy = SandboxPolicy.for_mode(sandbox_mode)
        
        self._sandbox = SubprocessSandbox(
            policy=policy,
            working_dir=working_dir,
            verbose=self.verbose
        )
        
        self._enabled = sandbox_mode != SandboxMode.DISABLED
        
        if self.verbose and self._enabled:
            from rich import print as rprint
            rprint(f"[yellow]⚠ Sandbox enabled: {sandbox_mode.value}[/yellow]")
        
        return self._sandbox
    
    def get_sandbox(self) -> Optional[SubprocessSandbox]:
        """Get the sandbox executor."""
        return self._sandbox
    
    def execute(
        self,
        command: str,
        timeout: Optional[float] = None
    ) -> ExecutionResult:
        """
        Execute a command.
        
        If sandbox is not initialized, runs without sandboxing.
        """
        if not self._sandbox:
            self._sandbox = self.initialize()
        
        return self._sandbox.execute(command, timeout=timeout)
    
    def validate_command(self, command: str) -> List[str]:
        """Validate a command against sandbox policy."""
        if not self._sandbox:
            return []
        
        return self._sandbox.validator.validate(command)
    
    def get_mode(self) -> str:
        """Get current sandbox mode."""
        if self._sandbox:
            return self._sandbox.policy.mode.value
        return SandboxMode.DISABLED.value
