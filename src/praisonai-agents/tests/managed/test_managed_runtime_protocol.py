"""
Tests for ManagedRuntimeProtocol conformance and functionality.
"""

import asyncio
from typing import Dict, Any, AsyncIterator, List

from praisonaiagents.managed.protocols import ManagedRuntimeProtocol


class MockManagedRuntime:
    """Mock implementation of ManagedRuntimeProtocol for testing."""
    
    def __init__(self):
        self.agents = {}
        self.environments = {} 
        self.sessions = {}
        self._next_id = 1
    
    def _get_id(self) -> str:
        self._next_id += 1
        return f"mock_{self._next_id}"
    
    async def create_agent(self, config: Dict[str, Any]) -> str:
        agent_id = self._get_id()
        self.agents[agent_id] = {**config, "id": agent_id}
        return agent_id
    
    async def create_environment(self, config: Dict[str, Any]) -> str:
        env_id = self._get_id()
        self.environments[env_id] = {**config, "id": env_id}
        return env_id
    
    async def create_session(self, agent_id: str, environment_id: str, **kwargs) -> str:
        session_id = self._get_id()
        self.sessions[session_id] = {
            "id": session_id,
            "agent_id": agent_id,
            "environment_id": environment_id,
            "status": "idle",
            **kwargs
        }
        return session_id
    
    async def send_event(self, session_id: str, event: Dict[str, Any]) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["last_event"] = event
    
    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        if session_id in self.sessions:
            yield {"type": "agent.message", "content": [{"type": "text", "text": "Hello!"}]}
            yield {"type": "session.status_idle"}
    
    async def interrupt(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["interrupted"] = True
    
    async def retrieve_session(self, session_id: str) -> Dict[str, Any]:
        return self.sessions.get(session_id, {})
    
    async def list_sessions(self, **filters) -> List[Dict[str, Any]]:
        return list(self.sessions.values())
    
    async def archive_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["archived"] = True
    
    async def delete_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            del self.sessions[session_id]


def test_protocol_compliance():
    """Test that our mock implements ManagedRuntimeProtocol correctly."""
    mock = MockManagedRuntime()
    assert isinstance(mock, ManagedRuntimeProtocol)


async def test_managed_runtime_lifecycle():
    """Test basic lifecycle of agent -> environment -> session."""
    runtime = MockManagedRuntime()
    
    # Create agent
    agent_id = await runtime.create_agent({"name": "test-agent", "model": "claude-3"})
    assert agent_id.startswith("mock_")
    assert runtime.agents[agent_id]["name"] == "test-agent"
    
    # Create environment
    env_id = await runtime.create_environment({"packages": {"pip": ["pandas"]}})
    assert env_id.startswith("mock_")
    assert runtime.environments[env_id]["packages"]["pip"] == ["pandas"]
    
    # Create session
    session_id = await runtime.create_session(agent_id, env_id, title="Test Session")
    assert session_id.startswith("mock_")
    session = runtime.sessions[session_id]
    assert session["agent_id"] == agent_id
    assert session["environment_id"] == env_id
    assert session["title"] == "Test Session"


async def test_event_streaming():
    """Test event sending and streaming."""
    runtime = MockManagedRuntime()
    
    # Setup session
    agent_id = await runtime.create_agent({"name": "test"})
    env_id = await runtime.create_environment({})
    session_id = await runtime.create_session(agent_id, env_id)
    
    # Send event
    await runtime.send_event(session_id, {
        "type": "user.message", 
        "content": [{"type": "text", "text": "Hello"}]
    })
    
    # Check event was stored
    session = await runtime.retrieve_session(session_id)
    assert session["last_event"]["type"] == "user.message"
    
    # Test streaming
    events = []
    async for event in runtime.stream_events(session_id):
        events.append(event)
    
    assert len(events) == 2
    assert events[0]["type"] == "agent.message"
    assert events[1]["type"] == "session.status_idle"


async def test_session_management():
    """Test session lifecycle operations."""
    runtime = MockManagedRuntime()
    
    # Setup
    agent_id = await runtime.create_agent({"name": "test"})
    env_id = await runtime.create_environment({})
    session_id = await runtime.create_session(agent_id, env_id)
    
    # List sessions
    sessions = await runtime.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    
    # Interrupt
    await runtime.interrupt(session_id)
    session = await runtime.retrieve_session(session_id)
    assert session["interrupted"] is True
    
    # Archive
    await runtime.archive_session(session_id)
    session = await runtime.retrieve_session(session_id)
    assert session["archived"] is True
    
    # Delete
    await runtime.delete_session(session_id)
    sessions = await runtime.list_sessions()
    assert len(sessions) == 0


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        print("Testing protocol compliance...")
        test_protocol_compliance()
        print("✅ Protocol compliance")
        
        print("Testing managed runtime lifecycle...")
        await test_managed_runtime_lifecycle()
        print("✅ Lifecycle tests")
        
        print("Testing event streaming...")
        await test_event_streaming()
        print("✅ Event streaming")
        
        print("Testing session management...")
        await test_session_management()
        print("✅ Session management")
        
        print("All tests passed! 🎉")
    
    asyncio.run(run_tests())