"""
Sandbox Protocols for PraisonAI Agents.

Defines the interfaces for sandbox implementations that enable
safe code execution in isolated environments.

All implementations should live in the praisonai wrapper package.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Protocol,
    Union,
    runtime_checkable,
)


class SandboxStatus(str, Enum):
    """Status of a sandbox execution."""
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"


@dataclass
class ResourceLimits:
    """Resource limits for sandbox execution.
    
    Attributes:
        memory_mb: Maximum memory in megabytes (0 = unlimited)
        cpu_percent: Maximum CPU percentage (0 = unlimited)
        timeout_seconds: Maximum execution time in seconds
        max_processes: Maximum number of processes
        max_open_files: Maximum number of open files
        network_enabled: Whether network access is allowed
        disk_write_mb: Maximum disk write in megabytes (0 = unlimited)
    """
    
    memory_mb: int = 512
    cpu_percent: int = 100
    timeout_seconds: int = 60
    max_processes: int = 10
    max_open_files: int = 100
    network_enabled: bool = False
    disk_write_mb: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "timeout_seconds": self.timeout_seconds,
            "max_processes": self.max_processes,
            "max_open_files": self.max_open_files,
            "network_enabled": self.network_enabled,
            "disk_write_mb": self.disk_write_mb,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceLimits":
        """Create from dictionary."""
        return cls(
            memory_mb=data.get("memory_mb", 512),
            cpu_percent=data.get("cpu_percent", 100),
            timeout_seconds=data.get("timeout_seconds", 60),
            max_processes=data.get("max_processes", 10),
            max_open_files=data.get("max_open_files", 100),
            network_enabled=data.get("network_enabled", False),
            disk_write_mb=data.get("disk_write_mb", 100),
        )
    
    @classmethod
    def minimal(cls) -> "ResourceLimits":
        """Create minimal resource limits for untrusted code."""
        return cls(
            memory_mb=128,
            cpu_percent=50,
            timeout_seconds=30,
            max_processes=5,
            max_open_files=50,
            network_enabled=False,
            disk_write_mb=10,
        )
    
    @classmethod
    def standard(cls) -> "ResourceLimits":
        """Create standard resource limits."""
        return cls()
    
    @classmethod
    def generous(cls) -> "ResourceLimits":
        """Create generous resource limits for trusted code."""
        return cls(
            memory_mb=2048,
            cpu_percent=100,
            timeout_seconds=300,
            max_processes=50,
            max_open_files=500,
            network_enabled=True,
            disk_write_mb=1000,
        )


@dataclass
class SandboxResult:
    """Result of a sandbox execution.
    
    Attributes:
        execution_id: Unique execution identifier
        status: Execution status
        exit_code: Process exit code (None if not completed)
        stdout: Standard output
        stderr: Standard error
        duration_seconds: Execution duration
        started_at: Start timestamp
        completed_at: Completion timestamp
        error: Error message if failed
        metadata: Additional execution metadata
    """
    
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: SandboxStatus = SandboxStatus.PENDING
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "status": self.status.value if isinstance(self.status, SandboxStatus) else self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SandboxResult":
        """Create from dictionary."""
        status = data.get("status", "pending")
        try:
            status = SandboxStatus(status)
        except ValueError:
            status = SandboxStatus.PENDING
        
        return cls(
            execution_id=data.get("execution_id", str(uuid.uuid4())),
            status=status,
            exit_code=data.get("exit_code"),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )
    
    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == SandboxStatus.COMPLETED and self.exit_code == 0
    
    @property
    def output(self) -> str:
        """Get combined output (stdout + stderr)."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[stderr]\n{self.stderr}")
        return "\n".join(parts)


@runtime_checkable
class SandboxProtocol(Protocol):
    """Protocol for sandbox implementations.
    
    Sandboxes provide isolated environments for safe code execution.
    Implementations can use Docker, subprocess isolation, or other
    containerization technologies.
    
    Example usage (implementation in praisonai wrapper):
        from praisonai.sandbox import DockerSandbox
        
        sandbox = DockerSandbox(image="python:3.11-slim")
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)
    """
    
    @property
    def is_available(self) -> bool:
        """Whether the sandbox backend is available."""
        ...
    
    @property
    def sandbox_type(self) -> str:
        """Type of sandbox (docker, subprocess, etc.)."""
        ...
    
    # Lifecycle methods
    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        ...
    
    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        ...
    
    # Execution methods
    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Execute code in the sandbox.
        
        Args:
            code: Code to execute
            language: Programming language (python, bash, etc.)
            limits: Resource limits for execution
            env: Environment variables
            working_dir: Working directory for execution
            
        Returns:
            Execution result
        """
        ...
    
    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a file in the sandbox.
        
        Args:
            file_path: Path to file to execute
            args: Command line arguments
            limits: Resource limits for execution
            env: Environment variables
            
        Returns:
            Execution result
        """
        ...
    
    async def run_command(
        self,
        command: Union[str, List[str]],
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Run a shell command in the sandbox.
        
        Args:
            command: Command to run (string or list of args)
            limits: Resource limits for execution
            env: Environment variables
            working_dir: Working directory
            
        Returns:
            Execution result
        """
        ...
    
    # File operations
    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file to the sandbox.
        
        Args:
            path: Path within sandbox
            content: File content
            
        Returns:
            True if successful
        """
        ...
    
    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file from the sandbox.
        
        Args:
            path: Path within sandbox
            
        Returns:
            File content or None if not found
        """
        ...
    
    async def list_files(
        self,
        path: str = "/",
    ) -> List[str]:
        """List files in a sandbox directory.
        
        Args:
            path: Directory path within sandbox
            
        Returns:
            List of file paths
        """
        ...
    
    # Status and cleanup
    def get_status(self) -> Dict[str, Any]:
        """Get sandbox status information.
        
        Returns:
            Status information including:
            - available: Whether sandbox is available
            - type: Sandbox type
            - running: Whether sandbox is running
            - resource_usage: Current resource usage
        """
        ...
    
    async def cleanup(self) -> None:
        """Clean up sandbox resources (files, processes, etc.)."""
        ...
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        ...
