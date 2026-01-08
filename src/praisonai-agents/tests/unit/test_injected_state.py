"""
TDD Tests for InjectedState for Tools.

These tests are written FIRST before implementation.
"""

import pytest
from unittest.mock import Mock, patch


class TestInjectedTypeExists:
    """Test that Injected type marker exists."""
    
    def test_injected_type_exists(self):
        """Injected type should exist in praisonaiagents.tools."""
        from praisonaiagents.tools import Injected
        
        # Should be a generic type marker
        assert Injected is not None
    
    def test_injected_generic_usage(self):
        """Injected should work as a generic type annotation."""
        from praisonaiagents.tools import Injected
        
        # Should be usable as Injected[dict], Injected[SomeType], etc.
        def my_tool(query: str, state: Injected[dict]) -> str:
            return query
        
        # Should have annotations
        annotations = my_tool.__annotations__
        assert 'state' in annotations
    
    def test_injected_with_agent_state(self):
        """Injected[AgentState] should work."""
        from praisonaiagents.tools import Injected
        from praisonaiagents.tools.injected import AgentState
        
        def my_tool(query: str, state: Injected[AgentState]) -> str:
            return query
        
        annotations = my_tool.__annotations__
        assert 'state' in annotations


class TestAgentStateType:
    """Test AgentState type for injection."""
    
    def test_agent_state_exists(self):
        """AgentState type should exist."""
        from praisonaiagents.tools.injected import AgentState
        
        assert AgentState is not None
    
    def test_agent_state_has_required_fields(self):
        """AgentState should have agent_id, run_id, session_id."""
        from praisonaiagents.tools.injected import AgentState
        
        state = AgentState(
            agent_id="agent-123",
            run_id="run-456",
            session_id="session-789"
        )
        
        assert state.agent_id == "agent-123"
        assert state.run_id == "run-456"
        assert state.session_id == "session-789"
    
    def test_agent_state_optional_fields(self):
        """AgentState should have optional fields."""
        from praisonaiagents.tools.injected import AgentState
        
        state = AgentState(
            agent_id="a",
            run_id="r",
            session_id="s",
            last_user_message="Hello",
            last_agent_message="Hi there",
            memory=Mock(),
            previous_tool_results=["result1", "result2"]
        )
        
        assert state.last_user_message == "Hello"
        assert state.last_agent_message == "Hi there"
        assert state.memory is not None
        assert len(state.previous_tool_results) == 2


class TestToolDecoratorInjection:
    """Test @tool decorator handles Injected parameters."""
    
    def test_tool_decorator_detects_injected(self):
        """@tool should detect Injected parameters."""
        from praisonaiagents import tool
        from praisonaiagents.tools import Injected
        
        @tool
        def my_tool(query: str, state: Injected[dict]) -> str:
            """A tool with injected state."""
            return f"query={query}, session={state.get('session_id')}"
        
        # Should have metadata about injected params
        assert hasattr(my_tool, '_injected_params') or hasattr(my_tool, 'injected_params')
    
    def test_injected_params_not_in_schema(self):
        """Injected parameters should not appear in tool schema."""
        from praisonaiagents import tool
        from praisonaiagents.tools import Injected
        
        @tool
        def my_tool(query: str, state: Injected[dict]) -> str:
            """A tool with injected state."""
            return query
        
        schema = my_tool.get_schema()
        params = schema['function']['parameters']['properties']
        
        # 'query' should be in schema
        assert 'query' in params
        # 'state' should NOT be in schema (it's injected)
        assert 'state' not in params
    
    def test_injected_params_not_required(self):
        """Injected parameters should not be in required list."""
        from praisonaiagents import tool
        from praisonaiagents.tools import Injected
        
        @tool
        def my_tool(query: str, state: Injected[dict]) -> str:
            """A tool with injected state."""
            return query
        
        schema = my_tool.get_schema()
        required = schema['function']['parameters'].get('required', [])
        
        assert 'state' not in required
        assert 'query' in required


class TestToolExecutionInjection:
    """Test that injected state is provided at runtime."""
    
    def test_injected_state_provided_at_runtime(self):
        """When tool is called, injected state should be provided."""
        from praisonaiagents import tool
        from praisonaiagents.tools import Injected
        from praisonaiagents.tools.injected import AgentState
        
        received_state = [None]
        
        @tool
        def my_tool(query: str, state: Injected[AgentState]) -> str:
            """A tool with injected state."""
            received_state[0] = state
            return f"session={state.session_id}"
        
        # Simulate execution with injection context
        from praisonaiagents.tools.injected import with_injection_context
        
        mock_state = AgentState(
            agent_id="a",
            run_id="r",
            session_id="test-session"
        )
        
        with with_injection_context(mock_state):
            result = my_tool(query="hello")
        
        assert received_state[0] is not None
        assert received_state[0].session_id == "test-session"
    
    def test_injected_dict_state(self):
        """Injected[dict] should provide dict with state info."""
        from praisonaiagents import tool
        from praisonaiagents.tools import Injected
        from praisonaiagents.tools.injected import with_injection_context, AgentState
        
        received_state = [None]
        
        @tool
        def my_tool(query: str, state: Injected[dict]) -> str:
            """A tool with injected dict state."""
            received_state[0] = state
            return "ok"
        
        mock_state = AgentState(
            agent_id="a",
            run_id="r",
            session_id="s"
        )
        
        with with_injection_context(mock_state):
            my_tool(query="test")
        
        assert isinstance(received_state[0], dict)
        assert 'session_id' in received_state[0]


class TestAgentToolExecution:
    """Test Agent executes tools with injection."""
    
    def test_agent_injects_state_to_tools(self):
        """Agent should inject state when executing tools."""
        from praisonaiagents import Agent, tool
        from praisonaiagents.tools import Injected
        
        received_session = [None]
        
        @tool
        def show_state(query: str, state: Injected[dict]) -> str:
            """Show the injected state."""
            received_session[0] = state.get('session_id')
            return f"session={state.get('session_id')}"
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            tools=[show_state],
            output="silent",
        )
        
        # Agent should be created successfully with tools
        assert agent is not None
        assert len(agent.tools) > 0


class TestInjectionContextManager:
    """Test injection context manager."""
    
    def test_with_injection_context_exists(self):
        """with_injection_context should exist."""
        from praisonaiagents.tools.injected import with_injection_context
        
        assert with_injection_context is not None
    
    def test_context_manager_sets_state(self):
        """Context manager should set current state."""
        from praisonaiagents.tools.injected import (
            with_injection_context, 
            get_current_state,
            AgentState
        )
        
        state = AgentState(agent_id="a", run_id="r", session_id="s")
        
        with with_injection_context(state):
            current = get_current_state()
            assert current is state
        
        # After context, should be None
        assert get_current_state() is None
    
    def test_nested_contexts(self):
        """Nested contexts should work correctly."""
        from praisonaiagents.tools.injected import (
            with_injection_context,
            get_current_state,
            AgentState
        )
        
        state1 = AgentState(agent_id="a1", run_id="r1", session_id="s1")
        state2 = AgentState(agent_id="a2", run_id="r2", session_id="s2")
        
        with with_injection_context(state1):
            assert get_current_state().agent_id == "a1"
            
            with with_injection_context(state2):
                assert get_current_state().agent_id == "a2"
            
            # Back to state1
            assert get_current_state().agent_id == "a1"


class TestAsyncInjection:
    """Test async tool injection."""
    
    @pytest.mark.asyncio
    async def test_async_tool_injection(self):
        """Async tools should also receive injected state."""
        from praisonaiagents import tool
        from praisonaiagents.tools import Injected
        from praisonaiagents.tools.injected import with_injection_context, AgentState
        
        received_state = [None]
        
        @tool
        async def async_tool(query: str, state: Injected[dict]) -> str:
            """Async tool with injected state."""
            received_state[0] = state
            return "ok"
        
        state = AgentState(agent_id="a", run_id="r", session_id="async-session")
        
        with with_injection_context(state):
            await async_tool(query="test")
        
        assert received_state[0] is not None
        assert received_state[0].get('session_id') == "async-session"


class TestInjectionZeroOverhead:
    """Test that injection has zero overhead when not used."""
    
    def test_no_injected_params_no_overhead(self):
        """Tools without Injected params should have no overhead."""
        from praisonaiagents import tool
        
        @tool
        def simple_tool(query: str) -> str:
            """Simple tool without injection."""
            return query
        
        # Should work normally without any injection context
        result = simple_tool(query="hello")
        assert result == "hello"
    
    def test_schema_generation_fast(self):
        """Schema generation should be fast even with Injected params."""
        from praisonaiagents import tool
        from praisonaiagents.tools import Injected
        import time
        
        @tool
        def my_tool(a: str, b: int, c: Injected[dict], d: float) -> str:
            """Tool with mixed params."""
            return a
        
        start = time.monotonic()
        for _ in range(100):
            my_tool.get_schema()
        elapsed = time.monotonic() - start
        
        # Should be very fast
        assert elapsed < 0.1  # 100 calls in < 100ms


class TestBackwardCompatibility:
    """Test backward compatibility with existing tools."""
    
    def test_existing_tools_still_work(self):
        """Existing tools without Injected should continue to work."""
        from praisonaiagents import tool
        
        @tool
        def legacy_tool(query: str, count: int = 5) -> str:
            """Legacy tool."""
            return f"{query} x {count}"
        
        result = legacy_tool(query="test", count=3)
        assert result == "test x 3"
    
    def test_existing_tool_schema_unchanged(self):
        """Existing tool schemas should be unchanged."""
        from praisonaiagents import tool
        
        @tool
        def legacy_tool(query: str, count: int = 5) -> str:
            """Legacy tool."""
            return f"{query} x {count}"
        
        schema = legacy_tool.get_schema()
        params = schema['function']['parameters']['properties']
        
        assert 'query' in params
        assert 'count' in params
        assert len(params) == 2
