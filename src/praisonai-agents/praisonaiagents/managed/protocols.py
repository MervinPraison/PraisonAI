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
class ManagedBackendProtocol(Protocol):
    """Protocol for external managed agent backends.
    
    Defines the contract between PraisonAI Agent's delegation layer
    and any managed agent infrastructure provider (Anthropic Managed Agents, etc.).
    
    The Core SDK defines *what* — this protocol.
    The Wrapper implements *how* — the provider-specific adapter.
    
    Lifecycle::
    
        backend = SomeManagedBackend(config={...})
        agent = Agent(name="coder", backend=backend)
        result = agent.start("Write a script")  # delegates to backend.execute()
    
    Implementations must handle:
    - Agent/environment/session creation and caching
    - Event streaming (agent.message, agent.tool_use, session.status_idle)
    - Custom tool calls (agent.custom_tool_use → user.custom_tool_result)
    - Tool confirmation (always_ask policy → user.tool_confirmation)
    - Usage tracking (input_tokens, output_tokens)
    - Session reset for multi-turn isolation
    """
    
    async def execute(self, prompt: str, **kwargs) -> str:
        """Execute a prompt on managed infrastructure and return the full response.
        
        This is the primary entry point called by Agent._delegate_to_backend().
        
        Args:
            prompt: The user message to send to the managed agent.
            **kwargs: Provider-specific options (e.g., timeout, metadata).
            
        Returns:
            The agent's complete text response.
        """
        ...
    
    async def stream(self, prompt: str, **kwargs):
        """Stream a prompt response as text chunks.
        
        Yields text fragments as the managed agent produces them.
        Used when Agent is invoked with stream=True.
        
        Args:
            prompt: The user message.
            **kwargs: Provider-specific options.
            
        Yields:
            Text chunks from the agent's response.
        """
        ...
        yield ""  # type: ignore[misc]
    
    def reset_session(self) -> None:
        """Discard the cached session so the next execute() creates a fresh one.
        
        The agent and environment remain cached for reuse.
        """
        ...
    
    def reset_all(self) -> None:
        """Discard all cached state (agent, environment, session, client).
        
        Next execute() call will re-create everything from scratch.
        """
        ...

    # ── Optional methods (default no-ops for backward compat) ──

    def update_agent(self, **kwargs) -> None:
        """Update an existing managed agent's configuration.
        
        Allows changing system prompt, tools, model, etc. on a previously
        created agent without recreating it.
        
        Args:
            **kwargs: Fields to update (system, tools, model, name, etc.).
        """
        ...

    def interrupt(self) -> None:
        """Send a user interrupt to the active session.
        
        Signals the managed agent to stop its current work (equivalent to
        ``user.interrupt`` event in the Anthropic API).
        """
        ...

    def retrieve_session(self) -> Dict[str, Any]:
        """Retrieve the current managed session's metadata and usage.
        
        Standardized return schema::
        
            {
                "session_id": "sesn_01234",
                "agent_id": "agent_01234", 
                "environment_id": "env_01234",
                "status": "idle" | "running" | "error",
                "created_at": 1234567890.0,
                "last_activity_at": 1234567890.0,
                "usage": {
                    "input_tokens": 150,
                    "output_tokens": 75,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                },
                "metadata": {}
            }
        
        Returns:
            Dict with standardized session info.
        """
        ...

    def list_sessions(self, **kwargs) -> List[Dict[str, Any]]:
        """List sessions for the current agent.
        
        Args:
            **kwargs: Provider-specific filters (limit, status, etc.).
            
        Returns:
            List of session summary dicts with same schema as retrieve_session().
        """
        ...
