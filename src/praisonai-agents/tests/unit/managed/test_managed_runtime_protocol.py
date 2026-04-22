"""
Tests for ManagedRuntimeProtocol conformance and implementations.

Ensures all managed runtime implementations satisfy the protocol contract.
"""

import asyncio
import pytest
import time
from typing import Any, AsyncIterator, Dict, List
from unittest.mock import AsyncMock

from praisonaiagents.managed.protocols import ManagedRuntimeProtocol


class TestManagedRuntimeProtocol:
    """Test ManagedRuntimeProtocol is properly defined."""
    
    def test_protocol_exists(self):
        """ManagedRuntimeProtocol should exist and be runtime checkable."""
        from praisonaiagents.managed.protocols import ManagedRuntimeProtocol
        assert ManagedRuntimeProtocol is not None
    
    def test_protocol_methods(self):
        """ManagedRuntimeProtocol should define all required methods."""
        from praisonaiagents.managed.protocols import ManagedRuntimeProtocol
        import inspect
        
        # Get all abstract methods
        methods = [method for method in dir(ManagedRuntimeProtocol) 
                  if not method.startswith('_') and callable(getattr(ManagedRuntimeProtocol, method, None))]
        
        # Check key methods exist
        expected_methods = [
            'create_agent', 'retrieve_agent', 'update_agent', 'archive_agent', 'list_agents',
            'list_agent_versions', 'create_environment', 'retrieve_environment', 
            'list_environments', 'archive_environment', 'delete_environment',
            'create_session', 'retrieve_session', 'list_sessions', 'archive_session',
            'delete_session', 'send_event', 'stream_events', 'interrupt'
        ]
        
        for method in expected_methods:
            assert method in methods, f"Method {method} missing from ManagedRuntimeProtocol"
    
    def test_protocol_import_from_package(self):
        """ManagedRuntimeProtocol should be importable from main package."""
        from praisonaiagents import ManagedRuntimeProtocol
        assert ManagedRuntimeProtocol is not None
    
    def test_protocol_import_from_managed(self):
        """ManagedRuntimeProtocol should be importable from managed module."""
        from praisonaiagents.managed import ManagedRuntimeProtocol
        assert ManagedRuntimeProtocol is not None


class MockManagedRuntime:
    """Mock implementation of ManagedRuntimeProtocol for testing."""
    
    def __init__(self):
        self._agents = {}
        self._environments = {}
        self._sessions = {}
    
    # Agent CRUD
    async def create_agent(self, config: Dict[str, Any]) -> str:
        agent_id = f"agent-{len(self._agents)}"
        self._agents[agent_id] = {**config, "id": agent_id, "created_at": time.time()}
        return agent_id
    
    async def retrieve_agent(self, agent_id: str) -> Dict[str, Any]:
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        return self._agents[agent_id].copy()
    
    async def update_agent(self, agent_id: str, config: Dict[str, Any]) -> str:
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        self._agents[agent_id].update(config)
        return "v2"
    
    async def archive_agent(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        self._agents[agent_id]["archived"] = True
    
    async def list_agents(self, **filters) -> List[Dict[str, Any]]:
        return list(self._agents.values())
    
    async def list_agent_versions(self, agent_id: str) -> List[Dict[str, Any]]:
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        return [{"version": 1, "created_at": time.time()}]
    
    # Environment CRUD
    async def create_environment(self, config: Dict[str, Any]) -> str:
        env_id = f"env-{len(self._environments)}"
        self._environments[env_id] = {**config, "id": env_id, "created_at": time.time()}
        return env_id
    
    async def retrieve_environment(self, environment_id: str) -> Dict[str, Any]:
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        return self._environments[environment_id].copy()
    
    async def list_environments(self, **filters) -> List[Dict[str, Any]]:
        return list(self._environments.values())
    
    async def archive_environment(self, environment_id: str) -> None:
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        self._environments[environment_id]["archived"] = True
    
    async def delete_environment(self, environment_id: str) -> None:
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        del self._environments[environment_id]
    
    # Session CRUD
    async def create_session(self, agent_id: str, environment_id: str, **kwargs) -> str:
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        if environment_id not in self._environments:
            raise ValueError(f"Environment {environment_id} not found")
        
        session_id = f"session-{len(self._sessions)}"
        self._sessions[session_id] = {
            "id": session_id,
            "agent_id": agent_id,
            "environment_id": environment_id,
            "status": "running",
            "created_at": time.time(),
            **kwargs
        }
        return session_id
    
    async def retrieve_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        return self._sessions[session_id].copy()
    
    async def list_sessions(self, **filters) -> List[Dict[str, Any]]:
        return list(self._sessions.values())
    
    async def archive_session(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id]["status"] = "archived"
    
    async def delete_session(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        del self._sessions[session_id]
    
    # Event streaming
    async def send_event(self, session_id: str, event: Dict[str, Any]) -> None:
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        # Store event for streaming
        if not hasattr(self, '_events'):
            self._events = {}
        if session_id not in self._events:
            self._events[session_id] = []
        self._events[session_id].append(event)
    
    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        # Mock streaming events
        if hasattr(self, '_events') and session_id in self._events:
            for event in self._events[session_id]:
                yield {
                    "type": "agent.message",
                    "content": [{"type": "text", "text": "Mock response"}],
                    "timestamp": time.time()
                }
        
        # Always end with idle event
        yield {
            "type": "session.status_idle",
            "stop_reason": "end_turn",
            "timestamp": time.time()
        }
    
    # Control
    async def interrupt(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id]["status"] = "interrupted"


class TestManagedRuntimeConformance:
    """Test that mock implementation conforms to protocol."""
    
    def test_protocol_conformance(self):
        """MockManagedRuntime should satisfy ManagedRuntimeProtocol."""
        from praisonaiagents.managed.protocols import ManagedRuntimeProtocol
        
        mock = MockManagedRuntime()
        assert isinstance(mock, ManagedRuntimeProtocol)
    
    @pytest.mark.asyncio
    async def test_agent_lifecycle(self):
        """Test complete agent lifecycle."""
        runtime = MockManagedRuntime()
        
        # Create agent
        agent_id = await runtime.create_agent({
            "name": "test-agent",
            "model": "gpt-4o",
            "system": "You are a helpful assistant."
        })
        assert agent_id.startswith("agent-")
        
        # Retrieve agent
        agent = await runtime.retrieve_agent(agent_id)
        assert agent["name"] == "test-agent"
        assert agent["model"] == "gpt-4o"
        
        # Update agent
        version = await runtime.update_agent(agent_id, {"model": "gpt-4o-mini"})
        assert version == "v2"
        
        # List agents
        agents = await runtime.list_agents()
        assert len(agents) == 1
        assert agents[0]["model"] == "gpt-4o-mini"
        
        # List versions
        versions = await runtime.list_agent_versions(agent_id)
        assert len(versions) == 1
        
        # Archive agent
        await runtime.archive_agent(agent_id)
        archived_agent = await runtime.retrieve_agent(agent_id)
        assert archived_agent["archived"] is True
    
    @pytest.mark.asyncio
    async def test_environment_lifecycle(self):
        """Test complete environment lifecycle."""
        runtime = MockManagedRuntime()
        
        # Create environment
        env_id = await runtime.create_environment({
            "name": "test-env",
            "packages": {"pip": ["pandas", "numpy"]}
        })
        assert env_id.startswith("env-")
        
        # Retrieve environment
        env = await runtime.retrieve_environment(env_id)
        assert env["name"] == "test-env"
        assert "pandas" in env["packages"]["pip"]
        
        # List environments
        environments = await runtime.list_environments()
        assert len(environments) == 1
        
        # Archive environment
        await runtime.archive_environment(env_id)
        archived_env = await runtime.retrieve_environment(env_id)
        assert archived_env["archived"] is True
        
        # Delete environment
        await runtime.delete_environment(env_id)
        environments = await runtime.list_environments()
        assert len(environments) == 0
    
    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle."""
        runtime = MockManagedRuntime()
        
        # Create agent and environment first
        agent_id = await runtime.create_agent({"name": "test-agent"})
        env_id = await runtime.create_environment({"name": "test-env"})
        
        # Create session
        session_id = await runtime.create_session(agent_id, env_id)
        assert session_id.startswith("session-")
        
        # Retrieve session
        session = await runtime.retrieve_session(session_id)
        assert session["agent_id"] == agent_id
        assert session["environment_id"] == env_id
        assert session["status"] == "running"
        
        # List sessions
        sessions = await runtime.list_sessions()
        assert len(sessions) == 1
        
        # Archive session
        await runtime.archive_session(session_id)
        archived_session = await runtime.retrieve_session(session_id)
        assert archived_session["status"] == "archived"
        
        # Delete session
        await runtime.delete_session(session_id)
        sessions = await runtime.list_sessions()
        assert len(sessions) == 0
    
    @pytest.mark.asyncio
    async def test_event_streaming(self):
        """Test event sending and streaming."""
        runtime = MockManagedRuntime()
        
        # Create session
        agent_id = await runtime.create_agent({"name": "test-agent"})
        env_id = await runtime.create_environment({"name": "test-env"})
        session_id = await runtime.create_session(agent_id, env_id)
        
        # Send event
        await runtime.send_event(session_id, {
            "type": "user.message",
            "content": "Hello"
        })
        
        # Stream events
        events = []
        async for event in runtime.stream_events(session_id):
            events.append(event)
            if event["type"] == "session.status_idle":
                break
        
        assert len(events) == 2  # agent.message + session.status_idle
        assert events[0]["type"] == "agent.message"
        assert events[1]["type"] == "session.status_idle"
    
    @pytest.mark.asyncio
    async def test_interrupt(self):
        """Test session interruption."""
        runtime = MockManagedRuntime()
        
        # Create session
        agent_id = await runtime.create_agent({"name": "test-agent"})
        env_id = await runtime.create_environment({"name": "test-env"})
        session_id = await runtime.create_session(agent_id, env_id)
        
        # Interrupt session
        await runtime.interrupt(session_id)
        
        # Check status
        session = await runtime.retrieve_session(session_id)
        assert session["status"] == "interrupted"


class TestProtocolComparison:
    """Test differences between ManagedBackendProtocol vs ManagedRuntimeProtocol."""
    
    def test_both_protocols_exist(self):
        """Both protocols should exist with different purposes."""
        from praisonaiagents.agent.protocols import ManagedBackendProtocol
        from praisonaiagents.managed.protocols import ManagedRuntimeProtocol
        
        assert ManagedBackendProtocol is not None
        assert ManagedRuntimeProtocol is not None
        assert ManagedBackendProtocol != ManagedRuntimeProtocol
    
    def test_protocol_methods_differ(self):
        """Protocols should have different method signatures."""
        from praisonaiagents.agent.protocols import ManagedBackendProtocol  
        from praisonaiagents.managed.protocols import ManagedRuntimeProtocol
        
        backend_methods = set(method for method in dir(ManagedBackendProtocol) 
                            if not method.startswith('_') and callable(getattr(ManagedBackendProtocol, method, None)))
        runtime_methods = set(method for method in dir(ManagedRuntimeProtocol)
                            if not method.startswith('_') and callable(getattr(ManagedRuntimeProtocol, method, None)))
        
        # ManagedBackendProtocol focuses on execute/stream
        assert 'execute' in backend_methods
        assert 'stream' in runtime_methods  # Both have streaming, but different purpose
        
        # ManagedRuntimeProtocol has CRUD operations
        assert 'create_agent' in runtime_methods
        assert 'create_environment' in runtime_methods
        assert 'create_session' in runtime_methods
        
        # These should NOT be in ManagedBackendProtocol (different abstraction levels)
        assert 'create_agent' not in backend_methods
        assert 'create_environment' not in backend_methods
        assert 'create_session' not in backend_methods