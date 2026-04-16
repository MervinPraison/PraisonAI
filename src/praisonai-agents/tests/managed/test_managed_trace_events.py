"""
Tests for managed agent trace events emission.

Verifies that AnthropicManagedAgent and LocalManagedAgent emit proper
ContextTraceEmitter events so that langextract/langfuse traces are non-empty.
"""

import pytest
from unittest.mock import Mock, patch
from praisonaiagents.trace.context_events import (
    ContextListSink, 
    ContextTraceEmitter, 
    ContextEventType,
    trace_context
)


class TestAnthropicManagedAgentTraceEvents:
    """Test trace event emission for AnthropicManagedAgent."""

    def test_execute_sync_emits_trace_events(self):
        """Test that _execute_sync emits agent_start, llm_response, and agent_end events."""
        from praisonai.integrations.managed_agents import AnthropicManagedAgent, ManagedConfig
        
        # Create a mock client and session
        mock_client = Mock()
        mock_stream = Mock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=None)
        
        # Mock events for the stream
        mock_event = Mock()
        mock_event.type = "session.status_idle"
        mock_stream.__iter__ = Mock(return_value=iter([mock_event]))
        
        mock_client.beta.sessions.events.stream.return_value = mock_stream
        
        # Create agent with mocked client
        config = ManagedConfig(name="TestAgent", system="Test system")
        agent = AnthropicManagedAgent(config=config)
        agent._client = mock_client
        agent.agent_id = "test_agent_id"
        agent.environment_id = "test_env_id"
        agent._session_id = "test_session_id"
        
        # Set up trace sink
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test_session", enabled=True)
        
        with trace_context(emitter):
            agent._execute_sync("Write a haiku")
        
        # Verify events were emitted
        events = sink.get_events()
        assert len(events) >= 2, f"Expected at least 2 events, got {len(events)}"
        
        # Check agent_start event
        start_events = [e for e in events if e.event_type == ContextEventType.AGENT_START]
        assert len(start_events) == 1, f"Expected 1 agent_start event, got {len(start_events)}"
        assert start_events[0].agent_name == "TestAgent"
        assert start_events[0].data["input"] == "Write a haiku"
        assert start_events[0].data["goal"] == "Test system"
        
        # Check agent_end event
        end_events = [e for e in events if e.event_type == ContextEventType.AGENT_END]
        assert len(end_events) == 1, f"Expected 1 agent_end event, got {len(end_events)}"
        assert end_events[0].agent_name == "TestAgent"

    def test_process_events_emits_tool_events(self):
        """Test that _process_events emits tool_call_start and tool_call_end for tool_use events."""
        from praisonai.integrations.managed_agents import AnthropicManagedAgent, ManagedConfig
        
        # Create agent
        config = ManagedConfig(name="TestAgent")
        agent = AnthropicManagedAgent(config=config)
        
        # Mock tool_use event
        mock_event = Mock()
        mock_event.type = "agent.tool_use"
        mock_event.name = "test_tool"
        mock_event.id = "tool_123"
        mock_event.input = {"query": "test"}
        mock_event.needs_confirmation = False
        mock_event.usage = None
        mock_event.model_usage = None
        
        # Mock session idle event
        mock_idle = Mock()
        mock_idle.type = "session.status_idle"
        mock_idle.usage = None
        mock_idle.model_usage = None
        
        # Set up trace sink
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test_session", enabled=True)
        
        # Call _process_events with emitter
        with trace_context(emitter):
            text_parts, tool_log = agent._process_events(
                client=Mock(), 
                session_id="test_session",
                stream=[mock_event, mock_idle],
                emitter=emitter
            )
        
        # Verify tool events were emitted
        events = sink.get_events()
        
        start_events = [e for e in events if e.event_type == ContextEventType.TOOL_CALL_START]
        assert len(start_events) == 1, f"Expected 1 tool_call_start event, got {len(start_events)}"
        assert start_events[0].agent_name == "TestAgent"
        assert start_events[0].data["tool_name"] == "test_tool"
        assert start_events[0].data["tool_args"] == {"query": "test"}
        
        end_events = [e for e in events if e.event_type == ContextEventType.TOOL_CALL_END]
        assert len(end_events) == 1, f"Expected 1 tool_call_end event, got {len(end_events)}"
        assert end_events[0].agent_name == "TestAgent"
        assert end_events[0].data["tool_name"] == "test_tool"
        assert end_events[0].data["duration_ms"] >= 0


class TestLocalManagedAgentTraceEvents:
    """Test trace event emission for LocalManagedAgent."""

    def test_execute_sync_emits_trace_events(self):
        """Test that _execute_sync emits agent_start, llm_response, and agent_end events."""
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        # Create agent with minimal config
        config = LocalManagedConfig(name="TestAgent", system="Test system", tools=[])
        agent = LocalManagedAgent(config=config)
        
        # Mock the inner agent
        mock_inner_agent = Mock()
        mock_inner_agent.chat.return_value = "This is a haiku response"
        agent._inner_agent = mock_inner_agent
        agent.agent_id = "test_agent_id"
        agent.environment_id = "test_env_id"
        agent._session_id = "test_session_id"
        
        # Mock session store methods
        agent._persist_message = Mock()
        agent._sync_usage = Mock()
        agent._persist_state = Mock()
        
        # Set up trace sink
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test_session", enabled=True)
        
        with trace_context(emitter):
            result = agent._execute_sync("Write a haiku")
        
        assert result == "This is a haiku response"
        
        # Verify events were emitted
        events = sink.get_events()
        assert len(events) >= 2, f"Expected at least 2 events, got {len(events)}"
        
        # Check agent_start event
        start_events = [e for e in events if e.event_type == ContextEventType.AGENT_START]
        assert len(start_events) == 1, f"Expected 1 agent_start event, got {len(start_events)}"
        assert start_events[0].agent_name == "TestAgent"
        assert start_events[0].data["input"] == "Write a haiku"
        assert start_events[0].data["goal"] == "Test system"
        
        # Check llm_response event
        response_events = [e for e in events if e.event_type == ContextEventType.LLM_RESPONSE]
        assert len(response_events) == 1, f"Expected 1 llm_response event, got {len(response_events)}"
        assert response_events[0].agent_name == "TestAgent"
        assert response_events[0].data["response_content"] == "This is a haiku response"
        
        # Check agent_end event
        end_events = [e for e in events if e.event_type == ContextEventType.AGENT_END]
        assert len(end_events) == 1, f"Expected 1 agent_end event, got {len(end_events)}"
        assert end_events[0].agent_name == "TestAgent"

    def test_zero_overhead_when_no_emitter(self):
        """Test that trace events have zero overhead when no emitter is installed."""
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        # Create agent
        config = LocalManagedConfig(name="TestAgent", tools=[])
        agent = LocalManagedAgent(config=config)
        
        # Mock the inner agent
        mock_inner_agent = Mock()
        mock_inner_agent.chat.return_value = "Response"
        agent._inner_agent = mock_inner_agent
        
        # Mock session methods
        agent._persist_message = Mock()
        agent._sync_usage = Mock()
        agent._persist_state = Mock()
        
        # Execute without any trace context - should work normally
        result = agent._execute_sync("Test prompt")
        
        assert result == "Response"
        mock_inner_agent.chat.assert_called_once_with("Test prompt")


class TestRealAgenticTest:
    """Real agentic test with actual Agent and managed backend."""
    
    @pytest.mark.skipif(True, reason="Gated real agentic test - requires API keys")
    def test_agent_with_managed_backend_shows_events(self):
        """Real agentic test: Agent(backend=ManagedAgent()).start() with ContextListSink shows ≥ 2 events."""
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        from praisonaiagents import Agent
        
        # Create local managed backend
        managed_config = LocalManagedConfig(
            name="TestAgent",
            system="You are a helpful assistant. Respond in exactly one sentence.",
            tools=[],  # No tools for simple test
        )
        managed_backend = LocalManagedAgent(config=managed_config)
        
        # Create Agent with managed backend
        agent = Agent(name="test", backend=managed_backend)
        
        # Set up trace collection
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="real_test", enabled=True)
        
        # Run agent with trace context
        with trace_context(emitter):
            result = agent.start("Say hi")
        
        print(f"Agent response: {result}")
        
        # Verify we got events
        events = sink.get_events()
        print(f"Collected {len(events)} events:")
        for i, event in enumerate(events):
            print(f"  {i+1}. {event.event_type} - {event.agent_name}")
        
        assert len(events) >= 2, f"Expected ≥ 2 events for real agentic test, got {len(events)}"
        
        # Should have at least agent_start and agent_end
        event_types = [e.event_type for e in events]
        assert ContextEventType.AGENT_START in event_types
        assert ContextEventType.AGENT_END in event_types
