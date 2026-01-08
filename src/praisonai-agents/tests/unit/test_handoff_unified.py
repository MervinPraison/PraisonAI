"""
Unit tests for the unified Handoff system.

Tests cover:
- HandoffConfig dataclass and defaults
- ContextPolicy enum
- Cycle detection
- Depth limiting
- Timeout handling
- Programmatic handoff (handoff_to)
- Async handoff (handoff_to_async)
- Deprecation warning for delegate()
- handoff() convenience function with config
"""

import pytest
import warnings
from unittest.mock import Mock, patch, MagicMock
import asyncio

from praisonaiagents.agent.handoff import (
    Handoff,
    handoff,
    HandoffConfig,
    HandoffResult,
    HandoffInputData,
    ContextPolicy,
    HandoffError,
    HandoffCycleError,
    HandoffDepthError,
    HandoffTimeoutError,
    handoff_filters,
    _get_handoff_chain,
    _clear_handoff_chain,
    _push_handoff,
    _pop_handoff,
    _get_handoff_depth,
)


class TestHandoffConfig:
    """Tests for HandoffConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = HandoffConfig()
        
        assert config.context_policy == ContextPolicy.SUMMARY
        assert config.max_context_tokens == 4000
        assert config.max_context_messages == 10
        assert config.preserve_system is True
        assert config.timeout_seconds == 300.0
        assert config.max_concurrent == 3
        assert config.detect_cycles is True
        assert config.max_depth == 10
        assert config.async_mode is False
        assert config.on_handoff is None
        assert config.on_complete is None
        assert config.on_error is None
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = HandoffConfig(
            context_policy=ContextPolicy.FULL,
            max_context_tokens=2000,
            timeout_seconds=60.0,
            max_concurrent=5,
            detect_cycles=False,
            max_depth=5,
        )
        
        assert config.context_policy == ContextPolicy.FULL
        assert config.max_context_tokens == 2000
        assert config.timeout_seconds == 60.0
        assert config.max_concurrent == 5
        assert config.detect_cycles is False
        assert config.max_depth == 5
    
    def test_to_dict(self):
        """Test config serialization to dict."""
        config = HandoffConfig(context_policy=ContextPolicy.NONE)
        d = config.to_dict()
        
        assert d["context_policy"] == "none"
        assert d["max_context_tokens"] == 4000
        assert d["detect_cycles"] is True
    
    def test_from_dict(self):
        """Test config deserialization from dict."""
        data = {
            "context_policy": "full",
            "timeout_seconds": 120.0,
            "max_depth": 5,
        }
        config = HandoffConfig.from_dict(data)
        
        assert config.context_policy == ContextPolicy.FULL
        assert config.timeout_seconds == 120.0
        assert config.max_depth == 5


class TestContextPolicy:
    """Tests for ContextPolicy enum."""
    
    def test_policy_values(self):
        """Test all policy values exist."""
        assert ContextPolicy.FULL.value == "full"
        assert ContextPolicy.SUMMARY.value == "summary"
        assert ContextPolicy.NONE.value == "none"
        assert ContextPolicy.LAST_N.value == "last_n"
    
    def test_policy_from_string(self):
        """Test creating policy from string."""
        assert ContextPolicy("full") == ContextPolicy.FULL
        assert ContextPolicy("summary") == ContextPolicy.SUMMARY
        assert ContextPolicy("none") == ContextPolicy.NONE


class TestHandoffChainTracking:
    """Tests for handoff chain tracking functions."""
    
    def setup_method(self):
        """Clear chain before each test."""
        _clear_handoff_chain()
    
    def teardown_method(self):
        """Clear chain after each test."""
        _clear_handoff_chain()
    
    def test_empty_chain(self):
        """Test empty chain."""
        assert _get_handoff_chain() == []
        assert _get_handoff_depth() == 0
    
    def test_push_pop(self):
        """Test push and pop operations."""
        _push_handoff("AgentA")
        assert _get_handoff_chain() == ["AgentA"]
        assert _get_handoff_depth() == 1
        
        _push_handoff("AgentB")
        assert _get_handoff_chain() == ["AgentA", "AgentB"]
        assert _get_handoff_depth() == 2
        
        popped = _pop_handoff()
        assert popped == "AgentB"
        assert _get_handoff_chain() == ["AgentA"]
        assert _get_handoff_depth() == 1
    
    def test_clear_chain(self):
        """Test clearing the chain."""
        _push_handoff("AgentA")
        _push_handoff("AgentB")
        _clear_handoff_chain()
        
        assert _get_handoff_chain() == []
        assert _get_handoff_depth() == 0


class TestHandoffErrors:
    """Tests for handoff error classes."""
    
    def test_cycle_error(self):
        """Test HandoffCycleError."""
        chain = ["AgentA", "AgentB", "AgentA"]
        error = HandoffCycleError(chain)
        
        assert error.chain == chain
        assert "AgentA -> AgentB -> AgentA" in str(error)
    
    def test_depth_error(self):
        """Test HandoffDepthError."""
        error = HandoffDepthError(depth=11, max_depth=10)
        
        assert error.depth == 11
        assert error.max_depth == 10
        assert "11 > 10" in str(error)
    
    def test_timeout_error(self):
        """Test HandoffTimeoutError."""
        error = HandoffTimeoutError(timeout=60.0, agent_name="TestAgent")
        
        assert error.timeout == 60.0
        assert error.agent_name == "TestAgent"
        assert "60" in str(error)
        assert "TestAgent" in str(error)


class TestHandoffResult:
    """Tests for HandoffResult dataclass."""
    
    def test_success_result(self):
        """Test successful handoff result."""
        result = HandoffResult(
            success=True,
            response="Task completed",
            target_agent="AgentB",
            source_agent="AgentA",
            duration_seconds=1.5,
        )
        
        assert result.success is True
        assert result.response == "Task completed"
        assert result.error is None
    
    def test_failure_result(self):
        """Test failed handoff result."""
        result = HandoffResult(
            success=False,
            target_agent="AgentB",
            source_agent="AgentA",
            error="Connection failed",
        )
        
        assert result.success is False
        assert result.error == "Connection failed"


class TestHandoffInputData:
    """Tests for HandoffInputData dataclass."""
    
    def test_default_values(self):
        """Test default input data values."""
        data = HandoffInputData()
        
        assert data.messages == []
        assert data.context == {}
        assert data.source_agent is None
        assert data.handoff_depth == 0
        assert data.handoff_chain == []
    
    def test_with_data(self):
        """Test input data with values."""
        messages = [{"role": "user", "content": "Hello"}]
        data = HandoffInputData(
            messages=messages,
            context={"key": "value"},
            source_agent="AgentA",
            handoff_depth=2,
            handoff_chain=["AgentA", "AgentB"],
        )
        
        assert data.messages == messages
        assert data.source_agent == "AgentA"
        assert data.handoff_depth == 2


class TestHandoff:
    """Tests for Handoff class."""
    
    def setup_method(self):
        """Clear chain before each test."""
        _clear_handoff_chain()
    
    def teardown_method(self):
        """Clear chain after each test."""
        _clear_handoff_chain()
    
    def test_init_with_defaults(self):
        """Test Handoff initialization with defaults."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        
        h = Handoff(agent=mock_agent)
        
        assert h.agent == mock_agent
        assert h.config is not None
        assert h.config.context_policy == ContextPolicy.SUMMARY
    
    def test_init_with_config(self):
        """Test Handoff initialization with custom config."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        config = HandoffConfig(context_policy=ContextPolicy.FULL)
        
        h = Handoff(agent=mock_agent, config=config)
        
        assert h.config.context_policy == ContextPolicy.FULL
    
    def test_tool_name_default(self):
        """Test default tool name generation."""
        mock_agent = Mock()
        mock_agent.name = "Billing Agent"
        
        h = Handoff(agent=mock_agent)
        
        assert h.tool_name == "transfer_to_billing_agent"
    
    def test_tool_name_override(self):
        """Test tool name override."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        
        h = Handoff(agent=mock_agent, tool_name_override="custom_transfer")
        
        assert h.tool_name == "custom_transfer"
    
    def test_tool_description_default(self):
        """Test default tool description."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.role = "Support"
        mock_agent.goal = "Help users"
        
        h = Handoff(agent=mock_agent)
        
        assert "TestAgent" in h.tool_description
        assert "Support" in h.tool_description
    
    def test_cycle_detection(self):
        """Test cycle detection in handoff."""
        mock_source = Mock()
        mock_source.name = "AgentA"
        mock_source.chat_history = []
        
        mock_target = Mock()
        mock_target.name = "AgentA"  # Same as source - cycle!
        
        config = HandoffConfig(detect_cycles=True)
        h = Handoff(agent=mock_target, config=config)
        
        # Simulate being in a chain
        _push_handoff("AgentA")
        
        with pytest.raises(HandoffCycleError):
            h._check_safety(mock_source)
    
    def test_depth_limiting(self):
        """Test max depth limiting."""
        mock_source = Mock()
        mock_source.name = "AgentA"
        
        mock_target = Mock()
        mock_target.name = "AgentB"
        
        config = HandoffConfig(max_depth=2)
        h = Handoff(agent=mock_target, config=config)
        
        # Simulate being at max depth
        _push_handoff("Agent1")
        _push_handoff("Agent2")
        
        with pytest.raises(HandoffDepthError):
            h._check_safety(mock_source)
    
    def test_context_policy_none(self):
        """Test NONE context policy."""
        mock_source = Mock()
        mock_source.name = "AgentA"
        mock_source.chat_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        
        mock_target = Mock()
        mock_target.name = "AgentB"
        
        config = HandoffConfig(context_policy=ContextPolicy.NONE)
        h = Handoff(agent=mock_target, config=config)
        
        data = h._prepare_context(mock_source, {})
        
        assert data.messages == []
    
    def test_context_policy_last_n(self):
        """Test LAST_N context policy."""
        mock_source = Mock()
        mock_source.name = "AgentA"
        mock_source.chat_history = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "5"},
        ]
        
        mock_target = Mock()
        mock_target.name = "AgentB"
        
        config = HandoffConfig(
            context_policy=ContextPolicy.LAST_N,
            max_context_messages=2,
            preserve_system=False,
        )
        h = Handoff(agent=mock_target, config=config)
        
        data = h._prepare_context(mock_source, {})
        
        assert len(data.messages) == 2
        assert data.messages[0]["content"] == "4"
        assert data.messages[1]["content"] == "5"


class TestHandoffFunction:
    """Tests for handoff() convenience function."""
    
    def test_basic_usage(self):
        """Test basic handoff function usage."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        
        h = handoff(mock_agent)
        
        assert isinstance(h, Handoff)
        assert h.agent == mock_agent
    
    def test_with_config_kwargs(self):
        """Test handoff with config kwargs."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        
        h = handoff(
            mock_agent,
            context_policy="full",
            timeout_seconds=60.0,
            max_depth=5,
        )
        
        assert h.config.context_policy == ContextPolicy.FULL
        assert h.config.timeout_seconds == 60.0
        assert h.config.max_depth == 5
    
    def test_with_explicit_config(self):
        """Test handoff with explicit HandoffConfig."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        config = HandoffConfig(detect_cycles=False)
        
        h = handoff(mock_agent, config=config)
        
        assert h.config.detect_cycles is False


class TestHandoffFilters:
    """Tests for handoff_filters class."""
    
    def test_remove_all_tools(self):
        """Test removing tool calls from messages."""
        data = HandoffInputData(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi", "tool_calls": [{}]},
                {"role": "tool", "content": "result"},
                {"role": "assistant", "content": "Done"},
            ]
        )
        
        filtered = handoff_filters.remove_all_tools(data)
        
        assert len(filtered.messages) == 2
        assert filtered.messages[0]["content"] == "Hello"
        assert filtered.messages[1]["content"] == "Done"
    
    def test_keep_last_n_messages(self):
        """Test keeping last N messages."""
        data = HandoffInputData(
            messages=[
                {"role": "user", "content": "1"},
                {"role": "assistant", "content": "2"},
                {"role": "user", "content": "3"},
            ]
        )
        
        filter_func = handoff_filters.keep_last_n_messages(2)
        filtered = filter_func(data)
        
        assert len(filtered.messages) == 2
        assert filtered.messages[0]["content"] == "2"
        assert filtered.messages[1]["content"] == "3"
    
    def test_remove_system_messages(self):
        """Test removing system messages."""
        data = HandoffInputData(
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ]
        )
        
        filtered = handoff_filters.remove_system_messages(data)
        
        assert len(filtered.messages) == 2
        assert all(m.get("role") != "system" for m in filtered.messages)


class TestAgentHandoffMethods:
    """Tests for Agent handoff methods (delegate removed, handoff_to is canonical)."""
    
    def test_agent_has_handoff_to_method(self):
        """Test that Agent has handoff_to method."""
        from praisonaiagents.agent.agent import Agent
        
        assert hasattr(Agent, 'handoff_to')
        assert hasattr(Agent, 'handoff_to_async')
    
    def test_agent_does_not_have_delegate_method(self):
        """Test that Agent.delegate() has been removed."""
        from praisonaiagents.agent.agent import Agent
        
        # delegate method should no longer exist
        assert not hasattr(Agent, 'delegate'), "delegate() should be removed - use handoff_to() instead"


class TestImports:
    """Tests for proper imports from package."""
    
    def test_import_from_agent_module(self):
        """Test imports from agent module."""
        from praisonaiagents.agent import (
            Handoff,
            handoff,
            HandoffConfig,
            HandoffResult,
            ContextPolicy,
            HandoffError,
            HandoffCycleError,
        )
        
        assert Handoff is not None
        assert HandoffConfig is not None
    
    def test_import_from_main_package(self):
        """Test imports from main package."""
        from praisonaiagents import (
            Handoff,
            handoff,
            HandoffConfig,
            HandoffResult,
            ContextPolicy,
        )
        
        assert Handoff is not None
        assert HandoffConfig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
