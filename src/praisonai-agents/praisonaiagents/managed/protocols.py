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
    AsyncIterator,
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


@runtime_checkable
class ManagedRuntimeProtocol(Protocol):
    """Protocol for hosted agent runtime — the agent LOOP runs on remote infra.
    
    This is the NEW protocol that separates true managed runtimes 
    (entire agent loop hosted remotely) from sandboxed tool execution
    (loop local, only tools remote).
    
    Implementations:
    - AnthropicManagedAgent: Uses Anthropic's hosted agent runtime
    - E2BManagedAgent: Agent loop runs inside E2B sandbox  
    - ModalManagedAgent: Agent loop runs as Modal function
    - FlyioManagedAgent: Agent loop runs in Fly.io Machine
    
    Lifecycle::
    
        # Create agent config on remote provider
        agent_id = await runtime.create_agent(config)
        
        # Create environment template 
        env_id = await runtime.create_environment(env_config)
        
        # Start session (agent instance in environment)
        session_id = await runtime.create_session(agent_id, env_id)
        
        # Send user message and stream agent responses
        await runtime.send_event(session_id, {"type": "user.message", "content": "Hello"})
        async for event in runtime.stream_events(session_id):
            if event["type"] == "agent.message":
                print(event["content"])
        
        # Cleanup
        await runtime.archive_session(session_id)
    
    Key differences from ManagedBackendProtocol:
    - ManagedBackendProtocol: Agent.chat() runs locally, delegates to backend.execute()
    - ManagedRuntimeProtocol: Agent.chat() runs on remote infra, events streamed back
    """
    
    # Agent CRUD
    async def create_agent(self, config: Dict[str, Any]) -> str:
        """Create a new agent on the remote runtime.
        
        Args:
            config: Agent configuration (name, model, system, tools, etc.)
            
        Returns:
            agent_id: Unique identifier for the created agent
        """
        ...
    
    async def retrieve_agent(self, agent_id: str) -> Dict[str, Any]:
        """Retrieve agent configuration and metadata.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Agent configuration dict
        """
        ...
    
    async def update_agent(self, agent_id: str, config: Dict[str, Any]) -> str:
        """Update agent configuration (bumps version).
        
        Args:
            agent_id: Agent identifier
            config: New configuration
            
        Returns:
            New version identifier
        """
        ...
    
    async def archive_agent(self, agent_id: str) -> None:
        """Archive an agent (make inactive).
        
        Args:
            agent_id: Agent identifier
        """
        ...
    
    async def list_agents(self, **filters) -> List[Dict[str, Any]]:
        """List all agents with optional filtering.
        
        Args:
            **filters: Optional filters (status, created_after, etc.)
            
        Returns:
            List of agent configuration dicts
        """
        ...
    
    async def list_agent_versions(self, agent_id: str) -> List[Dict[str, Any]]:
        """List all versions of an agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            List of version metadata dicts
        """
        ...
    
    # Environment CRUD
    async def create_environment(self, config: Dict[str, Any]) -> str:
        """Create a new environment template.
        
        Args:
            config: Environment configuration (packages, networking, etc.)
            
        Returns:
            environment_id: Unique identifier for the created environment
        """
        ...
    
    async def retrieve_environment(self, environment_id: str) -> Dict[str, Any]:
        """Retrieve environment configuration.
        
        Args:
            environment_id: Environment identifier
            
        Returns:
            Environment configuration dict
        """
        ...
    
    async def list_environments(self, **filters) -> List[Dict[str, Any]]:
        """List environments with optional filtering.
        
        Args:
            **filters: Optional filters
            
        Returns:
            List of environment configuration dicts
        """
        ...
    
    async def archive_environment(self, environment_id: str) -> None:
        """Archive an environment template.
        
        Args:
            environment_id: Environment identifier
        """
        ...
    
    async def delete_environment(self, environment_id: str) -> None:
        """Permanently delete an environment template.
        
        Args:
            environment_id: Environment identifier
        """
        ...
    
    # Session CRUD  
    async def create_session(
        self, 
        agent_id: str, 
        environment_id: str, 
        **kwargs
    ) -> str:
        """Create a new session (agent instance in environment).
        
        Args:
            agent_id: Agent identifier (latest version) or version dict
            environment_id: Environment identifier
            **kwargs: Optional vault_ids, resources, etc.
            
        Returns:
            session_id: Unique identifier for the session
        """
        ...
    
    async def retrieve_session(self, session_id: str) -> Dict[str, Any]:
        """Retrieve session metadata and status.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session metadata dict
        """
        ...
    
    async def list_sessions(self, **filters) -> List[Dict[str, Any]]:
        """List sessions with optional filtering.
        
        Args:
            **filters: Optional filters (agent_id, status, etc.)
            
        Returns:
            List of session metadata dicts
        """
        ...
    
    async def archive_session(self, session_id: str) -> None:
        """Archive a session (preserve but make inactive).
        
        Args:
            session_id: Session identifier  
        """
        ...
    
    async def delete_session(self, session_id: str) -> None:
        """Permanently delete a session.
        
        Args:
            session_id: Session identifier
        """
        ...
    
    # Event streaming (core interaction)
    async def send_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """Send an event to the session.
        
        Args:
            session_id: Session identifier
            event: Event dict (type: "user.message", content: "...", etc.)
        """
        ...
    
    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream events from the session.
        
        Args:
            session_id: Session identifier
            
        Yields:
            Event dicts (agent.message, agent.tool_use, session.status_idle, etc.)
        """
        ...
    
    # Control
    async def interrupt(self, session_id: str) -> None:
        """Interrupt a running session.
        
        Args:
            session_id: Session identifier
        """
        ...
