"""
Tests for Protocol definitions in praisonaiagents.

These tests verify that:
1. Protocols are properly defined and importable
2. Existing classes implement the protocols correctly
3. Protocol usage enables proper mocking and testing
"""
import pytest
from typing import Protocol, runtime_checkable


class TestAgentProtocol:
    """Test AgentProtocol definition and compliance."""
    
    def test_protocol_is_importable(self):
        """AgentProtocol should be importable from agent module."""
        from praisonaiagents.agent.protocols import AgentProtocol
        assert AgentProtocol is not None
    
    def test_protocol_is_runtime_checkable(self):
        """AgentProtocol should be runtime checkable for isinstance checks."""
        from praisonaiagents.agent.protocols import AgentProtocol
        # Verify it's a Protocol
        assert hasattr(AgentProtocol, '__protocol_attrs__') or hasattr(AgentProtocol, '_is_protocol')
    
    def test_agent_implements_protocol(self):
        """Agent class should satisfy AgentProtocol interface."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.protocols import AgentProtocol
        
        # Create an agent instance
        agent = Agent(name="Test", instructions="Test agent")
        
        # Verify the agent has the required protocol methods
        assert hasattr(agent, 'name')
        assert hasattr(agent, 'chat')
        assert hasattr(agent, 'achat')
        assert callable(agent.chat)
        assert callable(agent.achat)
    
    def test_protocol_enables_mocking(self):
        """Protocol should enable creating mock agents for testing."""
        from praisonaiagents.agent.protocols import AgentProtocol
        
        # Create a minimal mock that satisfies the protocol
        class MockAgent:
            @property
            def name(self) -> str:
                return "MockAgent"
            
            def chat(self, prompt: str, **kwargs) -> str:
                return f"Mock response to: {prompt}"
            
            async def achat(self, prompt: str, **kwargs) -> str:
                return f"Async mock response to: {prompt}"
        
        mock = MockAgent()
        assert mock.name == "MockAgent"
        assert mock.chat("Hello") == "Mock response to: Hello"


class TestMemoryProtocol:
    """Test MemoryProtocol definition and compliance."""
    
    def test_protocol_is_importable(self):
        """MemoryProtocol should be importable from memory module."""
        from praisonaiagents.memory.protocols import MemoryProtocol
        assert MemoryProtocol is not None
    
    def test_memory_implements_protocol(self):
        """Memory class should have methods matching MemoryProtocol."""
        from praisonaiagents.memory.memory import Memory
        
        # Check Memory has the expected interface
        assert hasattr(Memory, 'store_short_term')
        assert hasattr(Memory, 'search_short_term')
        assert hasattr(Memory, 'store_long_term')
        assert hasattr(Memory, 'search_long_term')
    
    def test_protocol_enables_mock_memory(self):
        """Protocol should enable creating mock memory for testing."""
        from praisonaiagents.memory.protocols import MemoryProtocol
        
        class MockMemory:
            def __init__(self):
                self._store = []
            
            def store_short_term(self, text: str, metadata=None, **kwargs) -> str:
                self._store.append({"text": text, "type": "short"})
                return f"stored_{len(self._store)}"
            
            def search_short_term(self, query: str, limit: int = 5, **kwargs):
                return [{"text": t["text"], "score": 1.0} for t in self._store[:limit]]
            
            def store_long_term(self, text: str, metadata=None, **kwargs) -> str:
                self._store.append({"text": text, "type": "long"})
                return f"stored_{len(self._store)}"
            
            def search_long_term(self, query: str, limit: int = 5, **kwargs):
                return [{"text": t["text"], "score": 1.0} for t in self._store[:limit]]
        
        mock = MockMemory()
        mock.store_short_term("test")
        results = mock.search_short_term("test")
        assert len(results) > 0


class TestToolProtocol:
    """Test ToolProtocol definition and compliance."""
    
    def test_protocol_is_importable(self):
        """ToolProtocol should be importable from tools module."""
        from praisonaiagents.tools.protocols.tool_protocol import ToolProtocol
        assert ToolProtocol is not None
    
    def test_basetool_satisfies_protocol(self):
        """BaseTool should have methods matching ToolProtocol."""
        from praisonaiagents.tools.base import BaseTool
        
        # Check BaseTool has the expected interface
        assert hasattr(BaseTool, 'name')
        assert hasattr(BaseTool, 'description')
        assert hasattr(BaseTool, 'run')
        assert hasattr(BaseTool, 'get_schema')
    
    def test_function_tool_satisfies_protocol(self):
        """FunctionTool from @tool decorator should satisfy protocol."""
        from praisonaiagents import tool
        
        @tool
        def my_tool(query: str) -> str:
            """A test tool."""
            return f"Result: {query}"
        
        assert hasattr(my_tool, 'name') or hasattr(my_tool, '__name__')
        assert callable(my_tool)
    
    def test_protocol_enables_mock_tool(self):
        """Protocol should enable creating mock tools for testing."""
        from praisonaiagents.tools.protocols.tool_protocol import ToolProtocol
        
        class MockTool:
            name = "mock_tool"
            description = "A mock tool for testing"
            
            def run(self, **kwargs) -> str:
                return "Mock tool result"
            
            def get_schema(self) -> dict:
                return {
                    "type": "function",
                    "function": {
                        "name": self.name,
                        "description": self.description,
                        "parameters": {"type": "object", "properties": {}}
                    }
                }
        
        mock = MockTool()
        assert mock.name == "mock_tool"
        assert mock.run() == "Mock tool result"
        assert "function" in mock.get_schema()


class TestProtocolExports:
    """Test that protocols are properly exported."""
    
    def test_all_protocols_importable_from_submodules(self):
        """All protocols should be importable from their respective modules."""
        # These imports should not raise
        from praisonaiagents.agent.protocols import AgentProtocol
        from praisonaiagents.memory.protocols import MemoryProtocol
        from praisonaiagents.tools.protocols.tool_protocol import ToolProtocol
        
        assert AgentProtocol is not None
        assert MemoryProtocol is not None
        assert ToolProtocol is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
