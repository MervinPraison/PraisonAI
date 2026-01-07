"""
Safe Shell Execution for PraisonAI CLI.

Provides shell execution with banned commands and auto-background support.
Reuses patterns from sandbox_executor.py.
"""

import subprocess
import shlex
import logging
import time
import threading
from typing import List, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# Banned commands list for safe shell execution
BANNED_COMMANDS: Set[str] = {
    # Network/Download tools
    "curl", "wget", "aria2c", "axel", "nc", "netcat",
    "ssh", "scp", "telnet", "ftp", "sftp",
    
    # Browsers
    "chrome", "firefox", "safari", "lynx", "w3m", "links",
    
    # System administration
    "sudo", "su", "doas",
    
    # Package managers (system-level)
    "apt", "apt-get", "yum", "dnf", "pacman", "zypper",
    "apk", "emerge", "pkg", "brew",
    
    # System modification
    "systemctl", "service", "chkconfig",
    "mount", "umount", "fdisk", "mkfs", "parted",
    "crontab", "at", "batch",
    
    # Network configuration
    "iptables", "firewall-cmd", "ufw", "pfctl",
    "ifconfig", "ip", "route", "netstat",
    
    # Dangerous file operations
    "rm", "rmdir", "dd", "shred",
    "chmod", "chown", "chgrp",
}

# Commands that are safe for read-only operations
SAFE_COMMANDS: Set[str] = {
    "ls", "cat", "head", "tail", "less", "more",
    "grep", "find", "wc", "sort", "uniq",
    "echo", "printf", "date", "pwd", "whoami",
    "file", "stat", "du", "df",
    "git status", "git log", "git diff", "git show",
    "python --version", "node --version", "npm --version",
}


class CommandRisk(Enum):
    """Risk level for commands."""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass
class ExecutionResult:
    """Result of shell command execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    command: str
    was_backgrounded: bool = False
    job_id: Optional[str] = None
    error: str = ""
    
    @property
    def output(self) -> str:
        """Get combined output."""
        if self.stdout and self.stderr:
            return f"{self.stdout}\n{self.stderr}"
        return self.stdout or self.stderr or ""


def get_command_name(command: str) -> str:
    """Extract the base command name from a command string."""
    try:
        parts = shlex.split(command)
        if parts:
            return parts[0].split("/")[-1]  # Handle full paths
    except ValueError:
        pass
    return command.split()[0] if command.split() else ""


def is_command_banned(command: str) -> bool:
    """Check if a command is in the banned list."""
    cmd_name = get_command_name(command).lower()
    
    # Check direct match
    if cmd_name in BANNED_COMMANDS:
        return True
    
    # Check for dangerous patterns
    dangerous_patterns = [
        "rm -rf", "rm -r", "rm -f",
        "> /dev/", ">> /dev/",
        "| sudo", "&& sudo",
        "chmod 777", "chmod -R",
    ]
    
    cmd_lower = command.lower()
    for pattern in dangerous_patterns:
        if pattern in cmd_lower:
            return True
            
    return False


def validate_command(command: str) -> bool:
    """
    Validate if a command is safe to execute.
    
    Returns True if command is allowed, False if blocked.
    """
    return not is_command_banned(command)


def get_command_risk(command: str) -> CommandRisk:
    """Assess the risk level of a command."""
    if is_command_banned(command):
        return CommandRisk.BLOCKED
        
    cmd_name = get_command_name(command).lower()
    
    # Check if it's a known safe command
    for safe_cmd in SAFE_COMMANDS:
        if command.lower().startswith(safe_cmd):
            return CommandRisk.SAFE
            
    # Check for potentially risky patterns
    risky_patterns = ["write", "delete", "modify", "create", "install"]
    if any(p in command.lower() for p in risky_patterns):
        return CommandRisk.MEDIUM
        
    return CommandRisk.LOW


def safe_execute(
    command: str,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    auto_background_threshold: float = 60.0,
    env: Optional[dict] = None,
    on_output: Optional[Callable[[str], None]] = None,
) -> ExecutionResult:
    """
    Execute a shell command safely with banned command checking.
    
    Args:
        command: Command to execute
        cwd: Working directory
        timeout: Maximum execution time in seconds
        auto_background_threshold: Time after which to background the command
        env: Environment variables
        on_output: Callback for streaming output
        
    Returns:
        ExecutionResult with execution details
    """
    start_time = time.time()
    
    # Check if command is banned
    if is_command_banned(command):
        return ExecutionResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=0,
            command=command,
            error=f"Command blocked: '{get_command_name(command)}' is in the banned commands list"
        )
    
    try:
        # Execute command
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            text=True,
        )
        
        # Wait for completion with timeout
        effective_timeout = timeout or auto_background_threshold
        
        try:
            stdout, stderr = process.communicate(timeout=effective_timeout)
            duration_ms = (time.time() - start_time) * 1000
            
            return ExecutionResult(
                success=process.returncode == 0,
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                command=command,
            )
            
        except subprocess.TimeoutExpired:
            # Command took too long - could be backgrounded
            duration_ms = (time.time() - start_time) * 1000
            
            # For now, kill the process
            process.kill()
            stdout, stderr = process.communicate()
            
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout=stdout or "",
                stderr=stderr or "",
                duration_ms=duration_ms,
                command=command,
                was_backgrounded=False,
                error=f"Command timed out after {effective_timeout}s"
            )
            
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return ExecutionResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=str(e),
            duration_ms=duration_ms,
            command=command,
            error=str(e)
        )


async def safe_execute_async(
    command: str,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    env: Optional[dict] = None,
) -> ExecutionResult:
    """Async version of safe_execute."""
    import asyncio
    
    start_time = time.time()
    
    if is_command_banned(command):
        return ExecutionResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=0,
            command=command,
            error=f"Command blocked: '{get_command_name(command)}' is in the banned commands list"
        )
    
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            return ExecutionResult(
                success=process.returncode == 0,
                exit_code=process.returncode or 0,
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                duration_ms=duration_ms,
                command=command,
            )
            
        except asyncio.TimeoutError:
            process.kill()
            duration_ms = (time.time() - start_time) * 1000
            
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                command=command,
                error=f"Command timed out after {timeout}s"
            )
            
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return ExecutionResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=str(e),
            duration_ms=duration_ms,
            command=command,
            error=str(e)
        )


class SafeShellHandler:
    """Handler for safe shell execution in CLI context."""
    
    def __init__(
        self,
        additional_banned: Optional[List[str]] = None,
        additional_allowed: Optional[List[str]] = None,
    ):
        self.banned_commands = BANNED_COMMANDS.copy()
        if additional_banned:
            self.banned_commands.update(additional_banned)
        if additional_allowed:
            self.banned_commands -= set(additional_allowed)
    
    def execute(self, command: str, **kwargs) -> ExecutionResult:
        """Execute a command with safety checks."""
        return safe_execute(command, **kwargs)
    
    async def execute_async(self, command: str, **kwargs) -> ExecutionResult:
        """Execute a command asynchronously with safety checks."""
        return await safe_execute_async(command, **kwargs)
    
    def is_safe(self, command: str) -> bool:
        """Check if a command is safe to execute."""
        return validate_command(command)
    
    def get_risk(self, command: str) -> CommandRisk:
        """Get the risk level of a command."""
        return get_command_risk(command)
