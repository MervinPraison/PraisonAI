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
            setup=["pip install -e ."],
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
    setup: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    working_dir: str = "/workspace"
    mount_paths: List[str] = field(default_factory=list)
    networking: Dict[str, Any] = field(default_factory=lambda: {"type": "unrestricted"})
    auto_shutdown: bool = True
    idle_timeout_s: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)


_ENV_FILENAME = "environment.yaml"
_ENV_DIRNAME = ".praisonai"

_ENV_KNOWN_KEYS = {
    "image", "packages", "setup", "env", "resources",
    "network", "backend", "working_dir", "mount_paths",
}


def find_environment_definition(start: Optional[str] = None) -> Optional[str]:
    """Discover ``.praisonai/environment.yaml`` by walking up from ``start``.

    Args:
        start: Directory to start searching from (defaults to CWD).

    Returns:
        Absolute path to the definition file, or ``None`` if not found.
    """
    import os

    current = os.path.abspath(start or os.getcwd())
    while True:
        candidate = os.path.join(current, _ENV_DIRNAME, _ENV_FILENAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def load_environment_definition(
    path: Optional[str] = None,
) -> Optional[ComputeConfig]:
    """Load a repo-committed ``.praisonai/environment.yaml`` into a ComputeConfig.

    This is the single resolution path shared by every ``compute=`` consumer:
    the file declares image / packages / setup / env / resources / network /
    backend, and is mapped onto the existing :class:`ComputeConfig` schema.

    Args:
        path: Explicit path to a definition file. If ``None``, discovery walks
            up from the current directory looking for ``.praisonai/environment.yaml``.

    Returns:
        A :class:`ComputeConfig`, or ``None`` when no file is found (callers then
        fall back to today's defaults — the file is strictly opt-in).

    Raises:
        ValueError: If the file contains unknown top-level keys or is malformed.
    """
    if path is None:
        path = find_environment_definition()
        if path is None:
            return None

    import yaml  # lazy — stdlib-adjacent, already a dependency

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: environment definition must be a mapping, got {type(data).__name__}"
        )

    unknown = set(data) - _ENV_KNOWN_KEYS
    if unknown:
        raise ValueError(
            f"{path}: unknown key(s) {sorted(unknown)}; "
            f"allowed keys are {sorted(_ENV_KNOWN_KEYS)}"
        )

    def _require(key: str, value: Any, expected: type, kind: str) -> None:
        if value is not None and not isinstance(value, expected):
            raise ValueError(
                f"{path}: '{key}' must be {kind}, got {type(value).__name__}"
            )

    cfg = ComputeConfig()

    if "image" in data:
        _require("image", data["image"], str, "a string")
        cfg.image = data["image"]
    if "packages" in data:
        pkgs = data["packages"] or {}
        _require("packages", pkgs, dict, "a mapping")
        cfg.packages = pkgs
    if "setup" in data:
        setup = data["setup"] or []
        if isinstance(setup, str):
            setup = [setup]
        _require("setup", setup, list, "a string or list of strings")
        cfg.setup = list(setup)
    if "env" in data:
        env = data["env"] or {}
        _require("env", env, dict, "a mapping")
        cfg.env = {str(k): str(v) for k, v in env.items()}
    if "working_dir" in data:
        _require("working_dir", data["working_dir"], str, "a string")
        cfg.working_dir = data["working_dir"]
    if "mount_paths" in data:
        mounts = data["mount_paths"] or []
        _require("mount_paths", mounts, list, "a list")
        cfg.mount_paths = list(mounts)

    resources = data.get("resources") or {}
    _require("resources", resources, dict, "a mapping")
    if "cpu" in resources:
        cfg.cpu = int(resources["cpu"])
    if "memory_mb" in resources:
        cfg.memory_mb = int(resources["memory_mb"])
    if "gpu" in resources:
        cfg.gpu = resources["gpu"]

    # Carry network / backend preferences in existing typed fields so no new
    # dataclass surface is added without a consumer.
    if "network" in data:
        cfg.networking = {"type": data["network"]}
    if "backend" in data:
        cfg.metadata["backend"] = data["backend"]

    return cfg


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
    
    Separates from ComputeProviderProtocol which only sandboxes tool execution.
    Here, the entire agent loop (LLM calls, tool calling, event streaming, 
    memory, session management) runs remotely.
    
    This is the protocol that Anthropic Managed Agents, E2B Managed Runtime,
    Modal Managed Functions, etc. should implement.
    
    Example lifecycle::
    
        runtime = AnthropicManagedAgent(config=cfg)
        agent_id = await runtime.create_agent(config)
        env_id = await runtime.create_environment(config)
        session_id = await runtime.create_session(agent_id, env_id)
        
        # Send user message and stream agent responses
        await runtime.send_event(session_id, {"type": "user.message", ...})
        async for event in runtime.stream_events(session_id):
            if event["type"] == "agent.message":
                print(event["content"])
    """

    async def create_agent(self, config: Dict[str, Any]) -> str:
        """Create agent definition on remote infrastructure.
        
        Args:
            config: Agent configuration (model, system, tools, etc.)
            
        Returns:
            Agent ID assigned by the remote provider
        """
        ...

    async def create_environment(self, config: Dict[str, Any]) -> str:
        """Create environment (container/sandbox) on remote infrastructure.
        
        Args:
            config: Environment configuration (packages, networking, etc.)
            
        Returns:
            Environment ID assigned by the remote provider
        """
        ...

    async def create_session(
        self, 
        agent_id: str, 
        environment_id: str, 
        **kwargs
    ) -> str:
        """Create running session (agent-in-environment) on remote infrastructure.
        
        Args:
            agent_id: Agent ID from create_agent()
            environment_id: Environment ID from create_environment()
            **kwargs: Additional session config (vault_ids, resources, etc.)
            
        Returns:
            Session ID assigned by the remote provider
        """
        ...

    async def send_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """Send event to running session.
        
        Args:
            session_id: Session ID from create_session()
            event: Event dict (e.g. {"type": "user.message", "content": [...]})
        """
        ...

    def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream events from running session.

        Implementations should be async generators: ``async def`` with ``yield``.
        Declared without ``async def`` here so the protocol signature matches the
        async-generator return type (``AsyncIterator``) rather than a coroutine
        that resolves to one, letting callers write ``async for e in runtime.stream_events(sid)``.

        Args:
            session_id: Session ID from create_session()

        Yields:
            Event dicts (agent.message, agent.tool_use, session.status_idle, etc.)
        """
        ...

    async def interrupt(self, session_id: str) -> None:
        """Send interrupt signal to running session.
        
        Args:
            session_id: Session ID to interrupt
        """
        ...

    async def retrieve_session(self, session_id: str) -> Dict[str, Any]:
        """Retrieve session metadata and status.
        
        Args:
            session_id: Session ID to retrieve
            
        Returns:
            Session info dict with id, status, title, usage, etc.
        """
        ...

    async def list_sessions(self, **filters) -> List[Dict[str, Any]]:
        """List sessions with optional filtering.
        
        Args:
            **filters: Filter criteria (agent_id, status, limit, etc.)
            
        Returns:
            List of session info dicts
        """
        ...

    async def archive_session(self, session_id: str) -> None:
        """Archive session (preserve but mark inactive).
        
        Args:
            session_id: Session ID to archive
        """
        ...

    async def delete_session(self, session_id: str) -> None:
        """Delete session permanently.
        
        Args:
            session_id: Session ID to delete
        """
        ...
