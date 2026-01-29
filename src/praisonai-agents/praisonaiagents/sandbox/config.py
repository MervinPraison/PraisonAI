"""
Sandbox Configuration for PraisonAI Agents.

Provides configuration dataclasses for sandbox settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .protocols import ResourceLimits


@dataclass
class SecurityPolicy:
    """Security policy for sandbox execution.
    
    Attributes:
        allow_network: Whether to allow network access
        allow_file_write: Whether to allow file writes
        allow_subprocess: Whether to allow subprocess creation
        allowed_paths: List of paths that can be accessed
        blocked_paths: List of paths that are blocked
        allowed_commands: List of allowed shell commands (empty = all)
        blocked_commands: List of blocked shell commands
        allowed_imports: List of allowed Python imports (empty = all)
        blocked_imports: List of blocked Python imports
        max_output_size: Maximum output size in bytes
    """
    
    allow_network: bool = False
    allow_file_write: bool = True
    allow_subprocess: bool = False
    allowed_paths: List[str] = field(default_factory=list)
    blocked_paths: List[str] = field(default_factory=lambda: [
        "/etc/passwd", "/etc/shadow", "~/.ssh", "~/.aws", "~/.config"
    ])
    allowed_commands: List[str] = field(default_factory=list)
    blocked_commands: List[str] = field(default_factory=lambda: [
        "rm -rf", "dd", "mkfs", "fdisk", "shutdown", "reboot"
    ])
    allowed_imports: List[str] = field(default_factory=list)
    blocked_imports: List[str] = field(default_factory=lambda: [
        "subprocess", "os.system", "eval", "exec", "compile"
    ])
    max_output_size: int = 1024 * 1024  # 1MB
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allow_network": self.allow_network,
            "allow_file_write": self.allow_file_write,
            "allow_subprocess": self.allow_subprocess,
            "allowed_paths": self.allowed_paths,
            "blocked_paths": self.blocked_paths,
            "allowed_commands": self.allowed_commands,
            "blocked_commands": self.blocked_commands,
            "allowed_imports": self.allowed_imports,
            "blocked_imports": self.blocked_imports,
            "max_output_size": self.max_output_size,
        }
    
    @classmethod
    def strict(cls) -> "SecurityPolicy":
        """Create a strict security policy for untrusted code."""
        return cls(
            allow_network=False,
            allow_file_write=False,
            allow_subprocess=False,
            max_output_size=100 * 1024,  # 100KB
        )
    
    @classmethod
    def standard(cls) -> "SecurityPolicy":
        """Create a standard security policy."""
        return cls()
    
    @classmethod
    def permissive(cls) -> "SecurityPolicy":
        """Create a permissive security policy for trusted code."""
        return cls(
            allow_network=True,
            allow_file_write=True,
            allow_subprocess=True,
            blocked_paths=[],
            blocked_commands=[],
            blocked_imports=[],
            max_output_size=10 * 1024 * 1024,  # 10MB
        )


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution.
    
    Attributes:
        sandbox_type: Type of sandbox (docker, subprocess, e2b)
        image: Docker image to use (for docker sandbox)
        working_dir: Working directory within sandbox
        env: Environment variables
        resource_limits: Resource limits
        security_policy: Security policy
        auto_cleanup: Whether to auto-cleanup after execution
        persist_files: Whether to persist files between executions
        mount_paths: Paths to mount into sandbox (host:container)
        metadata: Additional configuration
    """
    
    sandbox_type: str = "subprocess"
    image: str = "python:3.11-slim"
    working_dir: str = "/workspace"
    env: Dict[str, str] = field(default_factory=dict)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    security_policy: SecurityPolicy = field(default_factory=SecurityPolicy)
    auto_cleanup: bool = True
    persist_files: bool = False
    mount_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sandbox_type": self.sandbox_type,
            "image": self.image,
            "working_dir": self.working_dir,
            "env": {k: "***" if "key" in k.lower() or "secret" in k.lower() else v 
                   for k, v in self.env.items()},
            "resource_limits": self.resource_limits.to_dict(),
            "security_policy": self.security_policy.to_dict(),
            "auto_cleanup": self.auto_cleanup,
            "persist_files": self.persist_files,
            "mount_paths": self.mount_paths,
            "metadata": self.metadata,
        }
    
    @classmethod
    def docker(cls, image: str = "python:3.11-slim") -> "SandboxConfig":
        """Create a Docker sandbox configuration."""
        return cls(
            sandbox_type="docker",
            image=image,
        )
    
    @classmethod
    def subprocess(cls) -> "SandboxConfig":
        """Create a subprocess sandbox configuration."""
        return cls(
            sandbox_type="subprocess",
        )
    
    @classmethod
    def e2b(cls) -> "SandboxConfig":
        """Create an E2B sandbox configuration."""
        return cls(
            sandbox_type="e2b",
        )
