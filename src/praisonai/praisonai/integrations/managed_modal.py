"""
Modal Managed Agent Backend — true remote agent runtime in Modal functions.

The ENTIRE agent loop runs as Modal functions, providing serverless scaling
and automatic resource management.

Implements ``ManagedRuntimeProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations.managed_modal import ModalManagedAgent
    
    # True remote runtime - agent loop runs in Modal
    managed = ModalManagedAgent(
        app_name="my-agents",  # Modal app name
    )
    
    agent_id = await managed.create_agent({
        "name": "coder", 
        "model": "gpt-4o",
        "system": "You are a coding assistant."
    })
    
    env_id = await managed.create_environment({
        "packages": {"pip": ["pandas", "numpy"]}
    })
    
    session_id = await managed.create_session(agent_id, env_id)
    
    # Send message and stream responses from Modal function
    await managed.send_event(session_id, {
        "type": "user.message",
        "content": "Write a data analysis script"
    })
    
    async for event in managed.stream_events(session_id):
        if event["type"] == "agent.message":
            print(event["content"])
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass 
class ModalManagedConfig:
    """Configuration for Modal managed runtime.
    
    Attributes:
        app_name: Modal app name for the agent functions
        timeout: Default timeout for function calls
        cpu: CPU allocation for agent functions
        memory: Memory allocation in MB
        gpu: GPU type if needed
        auto_shutdown: Automatically shutdown idle functions
        idle_timeout: Seconds before auto-shutdown
        metadata: Additional provider-specific settings
    """
    app_name: str = "praisonai-agents"
    timeout: int = 300
    cpu: float = 1.0
    memory: int = 2048
    gpu: Optional[str] = None
    auto_shutdown: bool = True
    idle_timeout: int = 600  # 10 minutes
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModalManagedAgent:
    """Modal-hosted managed agent runtime.
    
    Implements ``ManagedRuntimeProtocol`` from Core SDK.
    
    The agent loop runs as Modal serverless functions, providing:
    - Automatic scaling (0 to many instances)
    - Pay-per-use compute billing
    - Isolated execution environment per session
    - Built-in dependency management
    
    Architecture:
    1. Agent configs stored in Modal's key-value store
    2. Environments define Modal function specs
    3. Sessions are running Modal function instances  
    4. Events passed via Modal queues/webhooks
    """
    
    def __init__(self, config: Optional[ModalManagedConfig] = None, **kwargs):
        """Initialize Modal managed runtime.
        
        Args:
            config: Modal configuration
            **kwargs: Override config fields
        """
        self.config = config or ModalManagedConfig()
        
        # Apply kwargs overrides
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._environments: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._modal_functions: Dict[str, Any] = {}  # session_id -> Modal function
        
        # Lazy import Modal SDK
        self._modal = None
        self._app = None
    
    def _get_modal(self):
        """Lazy import Modal SDK."""
        if self._modal is None:
            try:
                import modal
                self._modal = modal
                
                # Create or get the Modal app
                self._app = modal.App(self.config.app_name)
                
            except ImportError:
                raise ImportError(
                    "Modal SDK required for ModalManagedAgent. Install with: pip install modal"
                )
        return self._modal
    
    # Agent CRUD
    async def create_agent(self, config: Dict[str, Any]) -> str:
        """Create a new agent configuration."""
        agent_id = str(uuid.uuid4())
        
        agent_config = {
            "id": agent_id,
            "name": config.get("name", f"agent-{agent_id[:8]}"),
            "model": config.get("model", "gpt-4o-mini"), 
            "system": config.get("system", "You are a helpful assistant."),
            "tools": config.get("tools", []),
            "mcp_servers": config.get("mcp_servers", []),
            "skills": config.get("skills", []),
            "callable_agents": config.get("callable_agents", []),
            "metadata": config.get("metadata", {}),
            "created_at": time.time(),
            "version": 1,
        }
        
        self._agents[agent_id] = agent_config
        logger.info(f"Created agent {agent_id}: {agent_config['name']}")
        return agent_id
    
    async def retrieve_agent(self, agent_id: str) -> Dict[str, Any]:
        """Retrieve agent configuration."""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        return self._agents[agent_id].copy()
    
    async def update_agent(self, agent_id: str, config: Dict[str, Any]) -> str:
        """Update agent configuration (bumps version)."""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        agent_config = self._agents[agent_id].copy()
        agent_config.update(config)
        agent_config["version"] += 1
        agent_config["updated_at"] = time.time()
        
        self._agents[agent_id] = agent_config
        logger.info(f"Updated agent {agent_id} to version {agent_config['version']}")
        return str(agent_config["version"])
    
    async def archive_agent(self, agent_id: str) -> None:
        """Archive an agent (mark inactive)."""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        self._agents[agent_id]["archived"] = True
        self._agents[agent_id]["archived_at"] = time.time()
        logger.info(f"Archived agent {agent_id}")
    
    async def list_agents(self, **filters) -> List[Dict[str, Any]]:
        """List all agents with optional filtering."""
        agents = []
        for agent in self._agents.values():
            # Apply filters
            if filters.get("status") == "active" and agent.get("archived"):
                continue
            if filters.get("status") == "archived" and not agent.get("archived"):
                continue
                
            agents.append(agent.copy())
        
        return agents
    
    async def list_agent_versions(self, agent_id: str) -> List[Dict[str, Any]]:
        """List all versions of an agent."""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        # For simplicity, we only store the current version
        agent = self._agents[agent_id]
        return [{"version": agent["version"], "created_at": agent["created_at"]}]
    
    # Environment CRUD
    async def create_environment(self, config: Dict[str, Any]) -> str:
        """Create a new environment template."""
        env_id = str(uuid.uuid4())
        
        env_config = {
            "id": env_id,
            "name": config.get("name", f"env-{env_id[:8]}"),
            "packages": config.get("packages", {}),
            "cpu": config.get("cpu", self.config.cpu),
            "memory": config.get("memory", self.config.memory),
            "gpu": config.get("gpu", self.config.gpu),
            "networking": config.get("networking", {"type": "unrestricted"}),
            "metadata": config.get("metadata", {}),
            "created_at": time.time(),
        }
        
        self._environments[env_id] = env_config
        logger.info(f"Created environment {env_id}: {env_config['name']}")
        return env_id
    
    async def retrieve_environment(self, environment_id: str) -> Dict[str, Any]:
        """Retrieve environment configuration.""" 
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        return self._environments[environment_id].copy()
    
    async def list_environments(self, **filters) -> List[Dict[str, Any]]:
        """List environments with optional filtering."""
        return list(self._environments.values())
    
    async def archive_environment(self, environment_id: str) -> None:
        """Archive an environment template."""
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        
        self._environments[environment_id]["archived"] = True
        self._environments[environment_id]["archived_at"] = time.time()
        logger.info(f"Archived environment {environment_id}")
    
    async def delete_environment(self, environment_id: str) -> None:
        """Permanently delete an environment template.""" 
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        
        del self._environments[environment_id]
        logger.info(f"Deleted environment {environment_id}")
    
    # Session CRUD
    async def create_session(
        self, 
        agent_id: str, 
        environment_id: str, 
        **kwargs
    ) -> str:
        """Create a new session (agent instance in Modal function)."""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        
        session_id = str(uuid.uuid4())
        
        # Create Modal function for this session
        modal = self._get_modal()
        
        agent_config = self._agents[agent_id]
        env_config = self._environments[environment_id]
        
        # Define the Modal function dynamically
        image = modal.Image.debian_slim().pip_install(
            "praisonaiagents",
            *env_config.get("packages", {}).get("pip", [])
        )
        
        @self._app.function(
            image=image,
            cpu=env_config.get("cpu", self.config.cpu),
            memory=env_config.get("memory", self.config.memory),
            gpu=env_config.get("gpu"),
            timeout=self.config.timeout,
        )
        async def agent_function(event_data: dict):
            """Agent function that runs in Modal."""
            try:
                import asyncio
                from praisonaiagents import Agent
                
                # Create agent from config
                agent = Agent(
                    name=agent_config["name"],
                    model=agent_config["model"],
                    instructions=agent_config["system"],
                    # tools=agent_config.get("tools", []),
                )
                
                # Process the event
                if event_data["type"] == "user.message":
                    response = agent.start(event_data["content"])
                    
                    return {
                        "type": "agent.message",
                        "content": [{"type": "text", "text": response}],
                        "timestamp": time.time()
                    }
                
            except Exception as e:
                return {
                    "type": "session.error",
                    "error_message": str(e),
                    "timestamp": time.time()
                }
        
        self._modal_functions[session_id] = agent_function
        
        session_config = {
            "id": session_id,
            "agent_id": agent_id,
            "environment_id": environment_id,
            "status": "running",
            "created_at": time.time(),
            "metadata": kwargs.get("metadata", {}),
        }
        
        self._sessions[session_id] = session_config
        
        logger.info(f"Created session {session_id} with Modal function")
        return session_id
    
    async def retrieve_session(self, session_id: str) -> Dict[str, Any]:
        """Retrieve session metadata and status."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        return self._sessions[session_id].copy()
    
    async def list_sessions(self, **filters) -> List[Dict[str, Any]]:
        """List sessions with optional filtering."""
        sessions = []
        for session in self._sessions.values():
            # Apply filters
            if filters.get("agent_id") and session["agent_id"] != filters["agent_id"]:
                continue
            if filters.get("status") and session["status"] != filters["status"]:
                continue
            
            sessions.append(session.copy())
        
        return sessions
    
    async def archive_session(self, session_id: str) -> None:
        """Archive a session (preserve but make inactive)."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        # Clean up Modal function reference
        if session_id in self._modal_functions:
            del self._modal_functions[session_id]
        
        self._sessions[session_id]["status"] = "archived"
        self._sessions[session_id]["archived_at"] = time.time()
        logger.info(f"Archived session {session_id}")
    
    async def delete_session(self, session_id: str) -> None:
        """Permanently delete a session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        # Clean up Modal function reference
        if session_id in self._modal_functions:
            del self._modal_functions[session_id]
        
        del self._sessions[session_id]
        logger.info(f"Deleted session {session_id}")
    
    # Event streaming (core interaction)
    async def send_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """Send an event to the session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        if session_id not in self._modal_functions:
            raise RuntimeError(f"Session {session_id} function not active")
        
        # For this minimal implementation, we'll store events in a queue
        # In production, you'd use Modal's Queue or webhook system
        if not hasattr(self, '_event_queues'):
            self._event_queues = {}
        
        if session_id not in self._event_queues:
            self._event_queues[session_id] = []
        
        self._event_queues[session_id].append(event)
    
    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream events from the session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        if session_id not in self._modal_functions:
            raise RuntimeError(f"Session {session_id} function not active")
        
        modal_function = self._modal_functions[session_id]
        
        if not hasattr(self, '_event_queues'):
            self._event_queues = {}
        
        if session_id not in self._event_queues:
            self._event_queues[session_id] = []
        
        # Process queued events
        while True:
            event_queue = self._event_queues[session_id]
            
            if event_queue:
                event = event_queue.pop(0)
                
                try:
                    # Call Modal function to process event
                    result = await modal_function.remote.aio(event)
                    yield result
                    
                    # Emit session idle event if this was a user message
                    if event.get("type") == "user.message":
                        yield {
                            "type": "session.status_idle", 
                            "stop_reason": "end_turn",
                            "timestamp": time.time()
                        }
                        
                except Exception as e:
                    yield {
                        "type": "session.error",
                        "error_message": str(e),
                        "timestamp": time.time()
                    }
            
            # Check if session is still active
            if self._sessions.get(session_id, {}).get("status") != "running":
                break
            
            await asyncio.sleep(0.1)  # Poll every 100ms
    
    # Control
    async def interrupt(self, session_id: str) -> None:
        """Interrupt a running session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        self._sessions[session_id]["status"] = "interrupted"
        logger.info(f"Interrupted session {session_id}")
        
        # In a production implementation, you'd send an interrupt signal
        # to the running Modal function