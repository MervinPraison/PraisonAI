"""
Compute Provider Protocol for Managed Agents.

Defines the interface contract for remote compute backends that host
managed agent sandboxes. Implementations (Docker, Fly.io, AWS, GCP)
live in the ``praisonai`` wrapper package.

Usage::

    from praisonaiagents.managed.protocols import ComputeProviderProtocol

    class FlyioCompute:
        async def provision(self, config): ...
        async def execute(self, instance_id, prompt): ...
        async def shutdown(self, instance_id): ...

    compute: ComputeProviderProtocol = FlyioCompute()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)


class InstanceStatus(str, Enum):
    """Status of a compute instance."""
    PROVISIONING = "provisioning"
    RUNNING = "running"
    IDLE = "idle"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ComputeConfig:
    """Configuration for provisioning a compute instance.

    Provider-agnostic — maps to Docker containers, Fly.io Machines,
    AWS Lambda, GCP Cloud Run, etc.

    Example::

        cfg = ComputeConfig(
            image="python:3.12-slim",
            cpu=2,
            memory_mb=2048,
            packages={"pip": ["pandas", "numpy"]},
            env={"OPENAI_API_KEY": "sk-..."},
            auto_shutdown=True,
            idle_timeout_s=300,
        )
    """
    image: str = "python:3.12-slim"
    cpu: int = 1
    memory_mb: int = 1024
    gpu: Optional[str] = None
    packages: Dict[str, List[str]] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    working_dir: str = "/workspace"
    mount_paths: List[str] = field(default_factory=list)
    networking: Dict[str, Any] = field(default_factory=lambda: {"type": "unrestricted"})
    auto_shutdown: bool = True
    idle_timeout_s: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InstanceInfo:
    """Runtime information about a provisioned compute instance."""
    instance_id: str = ""
    status: InstanceStatus = InstanceStatus.PROVISIONING
    endpoint: str = ""
    provider: str = ""
    region: str = ""
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionInfo:
    """Unified session information schema for all managed backends.
    
    Provides a consistent interface for session metadata across
    Anthropic Managed Agents and Local Managed Agents.
    """
    id: str
    status: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionInfo":
        """Create SessionInfo from backend-specific dict."""
        return cls(
            id=data["id"],
            status=data.get("status"),
            usage=data.get("usage")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict format expected by ManagedBackendProtocol."""
        result = {"id": self.id}
        if self.status is not None:
            result["status"] = self.status
        if self.usage is not None:
            result["usage"] = self.usage
        return result


@runtime_checkable
class ComputeProviderProtocol(Protocol):
    """Protocol for compute backends that host managed agent sandboxes.

    Lifecycle::

        instance = await provider.provision(config)
        result = await provider.execute(instance.instance_id, "print('hello')")
        await provider.shutdown(instance.instance_id)

    Implementations should handle:
    - Instance provisioning (container/VM/function creation)
    - Auto-shutdown after idle timeout or task completion
    - Session persistence (or delegation to SessionStore)
    - Package installation within the sandbox
    """

    @property
    def provider_name(self) -> str:
        """Name of this compute provider (docker, flyio, aws, gcp, local)."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this compute backend is available and configured."""
        ...

    async def provision(
        self,
        config: ComputeConfig,
    ) -> InstanceInfo:
        """Provision a new compute instance.

        Args:
            config: Compute configuration.

        Returns:
            InstanceInfo with instance_id and endpoint.
        """
        ...

    async def shutdown(
        self,
        instance_id: str,
    ) -> None:
        """Shutdown and clean up a compute instance.

        Called automatically when auto_shutdown is True and the agent
        is idle, or explicitly by the user.

        Args:
            instance_id: ID returned by provision().
        """
        ...

    async def get_status(
        self,
        instance_id: str,
    ) -> InstanceInfo:
        """Get current status of a compute instance.

        Args:
            instance_id: ID returned by provision().

        Returns:
            Updated InstanceInfo.
        """
        ...

    async def execute(
        self,
        instance_id: str,
        command: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Execute a command on the compute instance.

        Args:
            instance_id: ID returned by provision().
            command: Shell command to execute.
            timeout: Execution timeout in seconds.

        Returns:
            Dict with stdout, stderr, exit_code.
        """
        ...

    async def upload_file(
        self,
        instance_id: str,
        local_path: str,
        remote_path: str,
    ) -> bool:
        """Upload a file to the compute instance.

        Args:
            instance_id: ID returned by provision().
            local_path: Local file path.
            remote_path: Path inside the instance.

        Returns:
            True if successful.
        """
        ...

    async def download_file(
        self,
        instance_id: str,
        remote_path: str,
        local_path: str,
    ) -> bool:
        """Download a file from the compute instance.

        Args:
            instance_id: ID returned by provision().
            remote_path: Path inside the instance.
            local_path: Local destination path.

        Returns:
            True if successful.
        """
        ...

    async def list_instances(self) -> List[InstanceInfo]:
        """List all active compute instances managed by this provider.

        Returns:
            List of InstanceInfo for running instances.
        """
        ...
