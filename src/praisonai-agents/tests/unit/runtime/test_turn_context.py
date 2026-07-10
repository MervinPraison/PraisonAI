"""
Test suite for PreparedTurnContext and runtime components.

This module provides tests to verify the turn context implementation
works correctly and maintains backward compatibility.
"""

import asyncio
import pytest
from typing import List, Dict, Any
from unittest.mock import Mock, patch

from praisonaiagents.runtime.turn_context import (
    PreparedTurnContext,
    ModelReference,
    ToolSchema, 
    TranscriptWindow,
    DeliveryChannels,
    SessionCorrelation,
    RuntimeMode,
    create_default_model_ref,
    create_empty_transcript,
    create_default_delivery,
    create_session_correlation,
)
from praisonaiagents.runtime.context_builder import DefaultTurnContextBuilder


class MockAgent:
    """Mock agent for testing context building."""
    
    def __init__(self):
        self.name = "TestAgent"
        self.model = "gpt-3.5-turbo"
        self.tools = []
        self.chat_history = []
        self.role = "assistant"
        self.goal = "help users"
        self.use_system_prompt = True
    
    def _build_system_prompt(self):
        return f"You are {self.role}. Your goal: {self.goal}"


class MockRuntime:
    """Mock runtime for testing execution."""
    
    def __init__(self):
        self.executed_contexts = []
    
    async def run_turn(self, context: PreparedTurnContext) -> str:
        self.executed_contexts.append(context)
        return f"Response to: {context.correlation.turn_id}"
    
    def supports_runtime_mode(self, mode: RuntimeMode) -> bool:
        return True
    
    def get_supported_modes(self) -> List[RuntimeMode]:
        return list(RuntimeMode)


def test_model_reference_creation():
    """Test ModelReference creation and validation."""
    # Test valid reference
    model_ref = ModelReference(
        model_id="gpt-4",
        provider="openai",
        supports_streaming=True,
        supports_tools=True,
        temperature=0.7
    )
    
    assert model_ref.model_id == "gpt-4"
    assert model_ref.provider == "openai"
    assert model_ref.supports_streaming is True
    assert model_ref.temperature == 0.7
    
    # Test validation
    with pytest.raises(ValueError, match="model_id is required"):
        ModelReference(model_id="", provider="openai")


def test_tool_schema_creation():
    """Test ToolSchema creation and validation."""
    tool = ToolSchema(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        source_type="function"
    )
    
    assert tool.name == "test_tool"
    assert tool.source_type == "function"
    
    # Test validation
    with pytest.raises(ValueError, match="Tool name is required"):
        ToolSchema(name="", description="test", parameters={})


def test_transcript_window():
    """Test TranscriptWindow creation."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    
    transcript = TranscriptWindow(
        messages=messages,
        total_tokens=20,
        system_prompt="You are helpful"
    )
    
    assert len(transcript.messages) == 2
    assert transcript.total_tokens == 20
    assert transcript.system_prompt == "You are helpful"


def test_prepared_turn_context():
    """Test PreparedTurnContext creation and validation."""
    model_ref = create_default_model_ref()
    agent = MockAgent()
    tools = []
    transcript = create_empty_transcript()
    delivery = create_default_delivery()
    correlation = create_session_correlation()
    
    context = PreparedTurnContext(
        model_ref=model_ref,
        agent_runtime=agent,
        tools=tools,
        transcript=transcript,
        delivery=delivery,
        correlation=correlation,
        runtime_mode=RuntimeMode.SYNC
    )
    
    assert context.model_ref.model_id == "gpt-3.5-turbo"
    assert context.runtime_mode == RuntimeMode.SYNC
    assert context.has_tools() is False
    assert context.get_message_count() == 0
    
    # Test dict conversion
    context_dict = context.to_dict()
    assert "model_id" in context_dict
    assert "tools_count" in context_dict
    assert context_dict["tools_count"] == 0


def test_context_builder():
    """Test DefaultTurnContextBuilder functionality."""
    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    
    # Test basic context building
    context = builder.build_context(
        agent=agent,
        prompt="Hello, world!",
        temperature=0.7,
        stream=False
    )
    
    assert isinstance(context, PreparedTurnContext)
    assert context.model_ref.model_id == "gpt-3.5-turbo"
    assert context.model_ref.temperature == 0.7
    assert context.runtime_mode == RuntimeMode.SYNC
    
    # Check transcript contains prompt
    user_messages = [msg for msg in context.transcript.messages if msg.get('role') == 'user']
    assert len(user_messages) == 1
    assert user_messages[0]['content'] == "Hello, world!"


def test_context_builder_with_streaming():
    """Test context building with streaming enabled."""
    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    
    context = builder.build_context(
        agent=agent,
        prompt="Stream test",
        stream=True,
        async_execution=False
    )
    
    assert context.runtime_mode == RuntimeMode.STREAM
    assert context.delivery.enable_streaming is True


def test_context_builder_with_async():
    """Test context building with async execution."""
    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    
    context = builder.build_context(
        agent=agent,
        prompt="Async test",
        stream=False,
        async_execution=True
    )
    
    assert context.runtime_mode == RuntimeMode.ASYNC


def test_context_builder_with_tools():
    """Test context building with tools."""
    def test_function(query: str) -> str:
        """A test function."""
        return f"Result for {query}"
    
    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    agent.tools = [test_function]
    
    context = builder.build_context(
        agent=agent,
        prompt="Use tools",
        tools=None  # Should use agent.tools
    )
    
    assert len(context.tools) == 1
    assert context.tools[0].name == "test_function"
    assert context.tools[0].source_type == "function"
    assert context.tools[0].callable == test_function


@pytest.mark.parametrize(
    "tools_kwargs,expected_count",
    [
        ({}, 1),  # omitted -> use agent.tools
        ({"tools": None}, 1),  # explicit None -> use agent.tools
        ({"tools": []}, 0),  # explicit empty list -> disable tools
    ],
)
def test_context_builder_tools_kwarg_semantics(tools_kwargs, expected_count):
    """None/omitted tools use agent.tools; [] explicitly disables tools."""
    def agent_function(query: str) -> str:
        """Agent default tool."""
        return f"Result for {query}"

    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    agent.tools = [agent_function]

    context = builder.build_context(
        agent=agent,
        prompt="Use tools",
        **tools_kwargs,
    )

    assert len(context.tools) == expected_count


def test_context_builder_tools_override():
    """An explicit non-empty tools list overrides agent.tools."""
    def agent_function(query: str) -> str:
        """Agent default tool."""
        return query

    def override_function(value: str) -> str:
        """Override tool."""
        return value

    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    agent.tools = [agent_function]

    context = builder.build_context(
        agent=agent,
        prompt="Use tools",
        tools=[override_function],
    )

    assert len(context.tools) == 1
    assert context.tools[0].name == "override_function"


def test_context_immutability():
    """Test that PreparedTurnContext is immutable."""
    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    
    context = builder.build_context(agent=agent, prompt="Test")
    
    # Should not be able to modify the context attributes
    with pytest.raises(AttributeError):
        context.model_ref = create_default_model_ref("gpt-4")
    
    # Tools should be a tuple (immutable)
    assert isinstance(context.tools, tuple)
    
    # Messages should be tuple of immutable mappings
    assert isinstance(context.transcript.messages, tuple)
    if context.transcript.messages:
        # Each message should be immutable
        assert hasattr(context.transcript.messages[0], 'keys')  # Is mapping-like


@pytest.mark.asyncio
async def test_runtime_execution():
    """Test runtime execution with prepared context."""
    builder = DefaultTurnContextBuilder()
    agent = MockAgent()
    runtime = MockRuntime()
    
    # Build context
    context = builder.build_context(
        agent=agent,
        prompt="Execute this",
        session_id="test-session"
    )
    
    # Execute with runtime
    response = await runtime.run_turn(context)
    
    assert isinstance(response, str)
    assert len(runtime.executed_contexts) == 1
    assert runtime.executed_contexts[0].correlation.session_id == "test-session"


def test_utility_functions():
    """Test utility functions for creating context components."""
    # Test create_default_model_ref
    model_ref = create_default_model_ref("claude-3", "anthropic")
    assert model_ref.model_id == "claude-3"
    assert model_ref.provider == "anthropic"
    
    # Test create_empty_transcript
    transcript = create_empty_transcript("System prompt")
    assert len(transcript.messages) == 0
    assert transcript.system_prompt == "System prompt"
    
    # Test create_default_delivery
    delivery = create_default_delivery()
    assert delivery.enable_streaming is False
    
    # Test create_session_correlation
    correlation = create_session_correlation("session-123", "agent-456")
    assert correlation.session_id == "session-123"
    assert correlation.agent_id == "agent-456"
    assert correlation.turn_id.startswith("turn-")


def test_runtime_mode_validation():
    """Test runtime mode validation in context."""
    # Test that streaming mode requires streaming configuration
    with pytest.raises(ValueError, match="requires streaming configuration"):
        PreparedTurnContext(
            model_ref=create_default_model_ref(),
            agent_runtime=MockAgent(),
            tools=(),
            transcript=create_empty_transcript(),
            delivery=create_default_delivery(),  # No streaming
            correlation=create_session_correlation(),
            runtime_mode=RuntimeMode.STREAM  # But stream mode requested
        )


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running basic tests...")
    
    test_model_reference_creation()
    print("✓ ModelReference tests passed")
    
    test_tool_schema_creation()
    print("✓ ToolSchema tests passed")
    
    test_transcript_window()
    print("✓ TranscriptWindow tests passed")
    
    test_prepared_turn_context()
    print("✓ PreparedTurnContext tests passed")
    
    test_context_builder()
    print("✓ Context builder tests passed")
    
    test_utility_functions()
    print("✓ Utility function tests passed")
    
    print("All basic tests completed!")