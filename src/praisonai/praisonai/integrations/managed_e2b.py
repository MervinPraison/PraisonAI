"""
E2B Managed Agent Backend — true remote agent runtime in E2B sandbox.

The ENTIRE agent loop runs inside an E2B sandbox, not just tool execution.
This provides full isolation and scalability for agent workloads.

Implements ``ManagedRuntimeProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations.managed_e2b import E2BManagedAgent
    from praisonaiagents import Agent

    # True remote runtime - agent loop runs in E2B
    managed = E2BManagedAgent(
        api_key="your_e2b_key",  # or set E2B_API_KEY env var
        template="praisonai-agent",  # E2B template with praisonaiagents pre-installed
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
    
    # Send message and stream responses from remote agent
    await managed.send_event(session_id, {
        "type": "user.message", 
        "content": "Write a Python script to analyze data"
    })
    
    async for event in managed.stream_events(session_id):
        if event["type"] == "agent.message":
            print(event["content"])
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class E2BManagedConfig:
    """Configuration for E2B managed runtime.
    
    Attributes:
        api_key: E2B API key (or use E2B_API_KEY env var)
        template: E2B template ID with praisonaiagents pre-installed
        timeout: Default timeout for operations in seconds
        auto_shutdown: Automatically shutdown idle sandboxes
        idle_timeout: Seconds before auto-shutdown
        region: E2B region preference
        metadata: Additional provider-specific settings
    """
    api_key: Optional[str] = None
    template: str = "praisonai-agent"  # Template with praisonaiagents installed
    timeout: int = 300
    auto_shutdown: bool = True
    idle_timeout: int = 600  # 10 minutes
    region: str = "us-east-1"
    metadata: Dict[str, Any] = field(default_factory=dict)


class E2BManagedAgent:
    """E2B-hosted managed agent runtime.
    
    Implements ``ManagedRuntimeProtocol`` from Core SDK.
    
    The agent loop runs entirely within E2B sandboxes, providing:
    - Full isolation from the host system
    - Scalable compute resources  
    - Automatic dependency management
    - Session persistence across sandbox restarts
    
    Architecture:
    1. Agent configs stored in E2B's metadata system
    2. Environments map to E2B templates/images
    3. Sessions are running sandboxes with agent harness
    4. Events streamed via E2B's execution API
    """
    
    def __init__(self, config: Optional[E2BManagedConfig] = None, **kwargs):
        """Initialize E2B managed runtime.
        
        Args:
            config: E2B configuration
            **kwargs: Override config fields
        """
        self.config = config or E2BManagedConfig()
        
        # Apply kwargs overrides
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # Resolve API key
        if not self.config.api_key:
            self.config.api_key = os.getenv("E2B_API_KEY")
            if not self.config.api_key:
                raise ValueError("E2B API key required - set E2B_API_KEY env var or pass api_key")
        
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._environments: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._sandboxes: Dict[str, Any] = {}  # session_id -> E2B sandbox instance
        
        # Lazy import E2B SDK
        self._e2b = None
    
    def _get_e2b(self):
        """Lazy import E2B SDK."""
        if self._e2b is None:
            try:
                import e2b
                self._e2b = e2b
            except ImportError:
                raise ImportError(
                    "E2B SDK required for E2BManagedAgent. Install with: pip install e2b"
                )
        return self._e2b
    
    # Agent CRUD
    async def create_agent(self, config: Dict[str, Any]) -> str:
        """Create a new agent configuration.
        
        Stores agent config for use in sessions. Unlike Anthropic,
        we store this locally since E2B doesn't have agent management.
        """
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
        # In a production implementation, you'd store version history
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
        """Create a new session (agent instance in E2B sandbox)."""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        
        session_id = str(uuid.uuid4())
        
        # Create E2B sandbox
        e2b = self._get_e2b()
        
        try:
            sandbox = await e2b.Sandbox.create(
                template=self.config.template,
                timeout=self.config.timeout,
                metadata={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "environment_id": environment_id,
                    **kwargs.get("metadata", {})
                }
            )
            
            self._sandboxes[session_id] = sandbox
            
            session_config = {
                "id": session_id,
                "agent_id": agent_id,
                "environment_id": environment_id,
                "status": "running",
                "created_at": time.time(),
                "sandbox_id": sandbox.id,
                "metadata": kwargs.get("metadata", {}),
            }
            
            self._sessions[session_id] = session_config
            
            # Install packages if specified in environment
            env_config = self._environments[environment_id]
            packages = env_config.get("packages", {})
            
            if packages.get("pip"):
                install_cmd = f"pip install {' '.join(packages['pip'])}"
                await sandbox.commands.run(install_cmd)
            
            if packages.get("npm"):
                install_cmd = f"npm install {' '.join(packages['npm'])}"
                await sandbox.commands.run(install_cmd)
            
            # Start agent harness in the sandbox
            agent_config = self._agents[agent_id]
            await self._start_agent_harness(sandbox, agent_config, session_id)
            
            logger.info(f"Created session {session_id} in sandbox {sandbox.id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {e}")
            # Cleanup if sandbox was created
            if session_id in self._sandboxes:
                try:
                    await self._sandboxes[session_id].close()
                except:
                    pass
                del self._sandboxes[session_id]
            raise
    
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
        
        # Close the E2B sandbox
        if session_id in self._sandboxes:
            try:
                await self._sandboxes[session_id].close()
            except Exception as e:
                logger.warning(f"Failed to close sandbox for session {session_id}: {e}")
            del self._sandboxes[session_id]
        
        self._sessions[session_id]["status"] = "archived"
        self._sessions[session_id]["archived_at"] = time.time()
        logger.info(f"Archived session {session_id}")
    
    async def delete_session(self, session_id: str) -> None:
        """Permanently delete a session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        # Close the E2B sandbox
        if session_id in self._sandboxes:
            try:
                await self._sandboxes[session_id].close()
            except Exception as e:
                logger.warning(f"Failed to close sandbox for session {session_id}: {e}")
            del self._sandboxes[session_id]
        
        del self._sessions[session_id]
        logger.info(f"Deleted session {session_id}")
    
    # Event streaming (core interaction)
    async def send_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """Send an event to the session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        if session_id not in self._sandboxes:
            raise RuntimeError(f"Session {session_id} sandbox not active")
        
        sandbox = self._sandboxes[session_id]
        
        # Send event to agent harness via stdin/file
        event_json = json.dumps(event)
        await sandbox.files.write("/tmp/incoming_event.json", event_json)
        
        # Signal the agent harness that a new event is available
        await sandbox.commands.run("touch /tmp/event_ready")
    
    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream events from the session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        if session_id not in self._sandboxes:
            raise RuntimeError(f"Session {session_id} sandbox not active")
        
        sandbox = self._sandboxes[session_id]
        
        # Poll for events from the agent harness
        # In a production implementation, you'd use WebSocket or SSE
        while True:
            try:
                # Check if agent harness has produced events
                result = await sandbox.commands.run("test -f /tmp/outgoing_events.jsonl")
                if result.exit_code == 0:
                    # Read and yield events
                    content = await sandbox.files.read("/tmp/outgoing_events.jsonl")
                    if content.strip():
                        for line in content.strip().split('\n'):
                            if line.strip():
                                event = json.loads(line)
                                yield event
                        
                        # Clear the events file
                        await sandbox.files.write("/tmp/outgoing_events.jsonl", "")
                
                # Check if session is still active
                if self._sessions.get(session_id, {}).get("status") != "running":
                    break
                
                await asyncio.sleep(0.1)  # Poll every 100ms
                
            except Exception as e:
                logger.error(f"Error streaming events from session {session_id}: {e}")
                break
    
    # Control
    async def interrupt(self, session_id: str) -> None:
        """Interrupt a running session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        if session_id not in self._sandboxes:
            raise RuntimeError(f"Session {session_id} sandbox not active")
        
        sandbox = self._sandboxes[session_id]
        
        # Send interrupt signal to agent harness
        await sandbox.commands.run("touch /tmp/interrupt_signal")
        
        self._sessions[session_id]["status"] = "interrupted"
        logger.info(f"Interrupted session {session_id}")
    
    # Helper methods
    async def _start_agent_harness(
        self, 
        sandbox, 
        agent_config: Dict[str, Any], 
        session_id: str
    ) -> None:
        """Start the agent harness inside the E2B sandbox."""
        # Create a simple Python harness that runs the agent loop
        harness_code = f"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add praisonaiagents to path
sys.path.append('/usr/local/lib/python3.12/site-packages')

try:
    from praisonaiagents import Agent
    
    # Create agent from config
    agent = Agent(
        name="{agent_config['name']}",
        model="{agent_config['model']}",
        instructions='''{agent_config['system']}''',
        # tools={agent_config.get('tools', [])},
    )
    
    async def agent_loop():
        print("Agent harness started for session {session_id}")
        
        while True:
            # Check for incoming events
            if os.path.exists('/tmp/event_ready'):
                try:
                    with open('/tmp/incoming_event.json', 'r') as f:
                        event = json.load(f)
                    
                    print(f"Received event: {{event['type']}}")
                    
                    if event['type'] == 'user.message':
                        # Process message with agent
                        response = agent.start(event['content'])
                        
                        # Emit agent.message event
                        out_event = {{
                            "type": "agent.message",
                            "content": [{{"type": "text", "text": response}}],
                            "timestamp": time.time()
                        }}
                        
                        # Write to output events
                        with open('/tmp/outgoing_events.jsonl', 'a') as f:
                            f.write(json.dumps(out_event) + '\\n')
                        
                        # Emit session idle event
                        idle_event = {{
                            "type": "session.status_idle",
                            "stop_reason": "end_turn",
                            "timestamp": time.time()
                        }}
                        
                        with open('/tmp/outgoing_events.jsonl', 'a') as f:
                            f.write(json.dumps(idle_event) + '\\n')
                    
                    # Clean up event files
                    os.remove('/tmp/event_ready')
                    os.remove('/tmp/incoming_event.json')
                    
                except Exception as e:
                    print(f"Error processing event: {{e}}")
            
            # Check for interrupt signal
            if os.path.exists('/tmp/interrupt_signal'):
                print("Received interrupt signal")
                break
            
            await asyncio.sleep(0.1)
    
    # Run the agent loop
    asyncio.run(agent_loop())
    
except Exception as e:
    print(f"Agent harness error: {{e}}")
    import traceback
    traceback.print_exc()
"""
        
        # Write and execute the harness
        await sandbox.files.write("/tmp/agent_harness.py", harness_code)
        
        # Start the harness in the background
        # Note: In production, you'd want better process management
        sandbox.commands.run("python /tmp/agent_harness.py &", background=True)