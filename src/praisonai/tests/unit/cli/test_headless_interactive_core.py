"""
Tests for Headless Interactive Core Executor.

Tests that the headless executor uses the same interactive core pipeline
as the TUI (InteractiveRuntime, get_interactive_tools, etc.).
"""

from unittest.mock import MagicMock

import pytest


class TestHeadlessConfig:
    """Tests for HeadlessConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        from praisonai.cli.features.interactive_core_headless import HeadlessConfig
        
        config = HeadlessConfig()
        assert config.model == "gpt-4o-mini"
        assert config.approval_mode == "auto"
        assert config.enable_acp is True
        assert config.enable_lsp is True
        assert config.enable_basic is True
        assert config.timeout == 60
    
    def test_custom_config(self):
        """Test custom configuration values."""
        from praisonai.cli.features.interactive_core_headless import HeadlessConfig
        
        config = HeadlessConfig(
            workspace="/tmp/test",
            model="gpt-4o",
            approval_mode="manual",
            timeout=120,
        )
        assert config.workspace == "/tmp/test"
        assert config.model == "gpt-4o"
        assert config.approval_mode == "manual"
        assert config.timeout == 120
    
    def test_default_agent_created(self):
        """Test that default agent is created if none provided."""
        from praisonai.cli.features.interactive_core_headless import HeadlessConfig
        
        config = HeadlessConfig()
        assert len(config.agents) == 1
        assert config.agents[0].name == "HeadlessAgent"


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""
    
    def test_default_values(self):
        """Test default agent config values."""
        from praisonai.cli.features.interactive_core_headless import AgentConfig
        
        config = AgentConfig()
        assert config.name == "HeadlessAgent"
        assert config.role == "assistant"
        assert config.llm == "gpt-4o-mini"
    
    def test_custom_values(self):
        """Test custom agent config values."""
        from praisonai.cli.features.interactive_core_headless import AgentConfig
        
        config = AgentConfig(
            name="TestAgent",
            instructions="Test instructions",
            role="tester",
            llm="gpt-4o",
        )
        assert config.name == "TestAgent"
        assert config.instructions == "Test instructions"
        assert config.role == "tester"
        assert config.llm == "gpt-4o"


class TestToolCallTrace:
    """Tests for ToolCallTrace dataclass."""
    
    def test_to_dict(self):
        """Test trace serialization."""
        from praisonai.cli.features.interactive_core_headless import ToolCallTrace
        
        trace = ToolCallTrace(
            tool_name="test_tool",
            args=("arg1",),
            kwargs={"key": "value"},
            result="result",
            success=True,
            error=None,
            duration=0.5,
            timestamp="2024-01-01T00:00:00",
        )
        
        d = trace.to_dict()
        assert d["tool_name"] == "test_tool"
        assert d["success"] is True
        assert d["duration"] == 0.5


class TestHeadlessExecutionResult:
    """Tests for HeadlessExecutionResult dataclass."""
    
    def test_to_dict(self):
        """Test result serialization."""
        from praisonai.cli.features.interactive_core_headless import (
            HeadlessExecutionResult,
        )
        
        result = HeadlessExecutionResult(
            success=True,
            responses=["Hello"],
            tool_trace=[],
            duration=1.0,
            transcript=[{"role": "user", "content": "Hi"}],
        )
        
        d = result.to_dict()
        assert d["success"] is True
        assert d["responses"] == ["Hello"]
        assert d["duration"] == 1.0


class TestHeadlessInteractiveCore:
    """Tests for HeadlessInteractiveCore class."""
    
    def test_initialization(self):
        """Test executor initialization."""
        from praisonai.cli.features.interactive_core_headless import (
            HeadlessConfig,
            HeadlessInteractiveCore,
        )
        
        config = HeadlessConfig(workspace="/tmp/test")
        executor = HeadlessInteractiveCore(config)
        
        assert executor.config.workspace == "/tmp/test"
        assert executor._initialized is False
        assert executor._tools == []
    
    def test_wrap_tool_for_trace(self):
        """Test that tool wrapping captures traces."""
        from praisonai.cli.features.interactive_core_headless import (
            HeadlessConfig,
            HeadlessInteractiveCore,
        )
        
        config = HeadlessConfig()
        executor = HeadlessInteractiveCore(config)
        
        def sample_tool(x):
            return x * 2
        
        wrapped = executor._wrap_tool_for_trace(sample_tool)
        result = wrapped(5)
        
        assert result == 10
        assert len(executor._tool_trace) == 1
        assert executor._tool_trace[0].tool_name == "sample_tool"
        assert executor._tool_trace[0].success is True
    
    def test_wrap_tool_captures_errors(self):
        """Test that tool wrapping captures errors."""
        from praisonai.cli.features.interactive_core_headless import (
            HeadlessConfig,
            HeadlessInteractiveCore,
        )
        
        config = HeadlessConfig()
        executor = HeadlessInteractiveCore(config)
        
        def failing_tool():
            raise ValueError("Test error")
        
        wrapped = executor._wrap_tool_for_trace(failing_tool)
        
        with pytest.raises(ValueError):
            wrapped()
        
        assert len(executor._tool_trace) == 1
        assert executor._tool_trace[0].success is False
        assert "Test error" in executor._tool_trace[0].error
    
    def test_get_agent_for_prompt_single_agent(self):
        """Test agent selection with single agent."""
        from praisonai.cli.features.interactive_core_headless import (
            HeadlessConfig,
            HeadlessInteractiveCore,
        )
        
        config = HeadlessConfig()
        executor = HeadlessInteractiveCore(config)
        executor._agents = [MagicMock()]  # Single agent
        
        assert executor._get_agent_for_prompt(0, "test") == 0
        assert executor._get_agent_for_prompt(1, "test") == 0
    
    def test_get_agent_for_prompt_round_robin(self):
        """Test round-robin agent selection."""
        from praisonai.cli.features.interactive_core_headless import (
            HeadlessConfig,
            HeadlessInteractiveCore,
            AgentConfig,
        )
        
        config = HeadlessConfig(
            agents=[AgentConfig(name="A"), AgentConfig(name="B")],
            workflow={"routing": "round_robin"},
        )
        executor = HeadlessInteractiveCore(config)
        executor._agents = [MagicMock(), MagicMock()]
        
        assert executor._get_agent_for_prompt(0, "test") == 0
        assert executor._get_agent_for_prompt(1, "test") == 1
        assert executor._get_agent_for_prompt(2, "test") == 0
    
    def test_clear_trace(self):
        """Test clearing tool trace."""
        from praisonai.cli.features.interactive_core_headless import (
            HeadlessConfig,
            HeadlessInteractiveCore,
            ToolCallTrace,
        )
        
        config = HeadlessConfig()
        executor = HeadlessInteractiveCore(config)
        executor._tool_trace = [
            ToolCallTrace("t", (), {}, None, True, None, 0, "")
        ]
        
        executor.clear_trace()
        assert executor._tool_trace == []


class TestRunHeadlessFunction:
    """Tests for run_headless convenience function."""
    
    def test_function_creates_executor(self):
        """Test that run_headless creates executor with correct config."""
        # We can't easily test the full run without mocking Agent
        # Just verify the function exists and has correct signature
        from praisonai.cli.features.interactive_core_headless import run_headless
        
        import inspect
        sig = inspect.signature(run_headless)
        params = list(sig.parameters.keys())
        
        assert "prompts" in params
        assert "workspace" in params
        assert "model" in params
        assert "approval_mode" in params
        assert "agents" in params
        assert "workflow" in params


class TestRedactSensitive:
    """Tests for _redact_sensitive function."""
    
    def test_redacts_api_key(self):
        """Test that API keys are redacted."""
        from praisonai.cli.features.interactive_core_headless import _redact_sensitive
        
        data = {"api_key": "secret123", "name": "test"}
        result = _redact_sensitive(data)
        
        assert result["api_key"] == "[REDACTED]"
        assert result["name"] == "test"
    
    def test_redacts_nested(self):
        """Test that nested sensitive data is redacted."""
        from praisonai.cli.features.interactive_core_headless import _redact_sensitive
        
        data = {"config": {"password": "secret", "user": "admin"}}
        result = _redact_sensitive(data)
        
        assert result["config"]["password"] == "[REDACTED]"
        assert result["config"]["user"] == "admin"
    
    def test_truncates_long_strings(self):
        """Test that long strings are truncated."""
        from praisonai.cli.features.interactive_core_headless import _redact_sensitive
        
        long_string = "x" * 200
        result = _redact_sensitive(long_string)
        
        assert len(result) < 200
        assert "[truncated]" in result


class TestTruncate:
    """Tests for _truncate function."""
    
    def test_short_string_unchanged(self):
        """Test that short strings are unchanged."""
        from praisonai.cli.features.interactive_core_headless import _truncate
        
        result = _truncate("hello", 100)
        assert result == "hello"
    
    def test_long_string_truncated(self):
        """Test that long strings are truncated."""
        from praisonai.cli.features.interactive_core_headless import _truncate
        
        result = _truncate("x" * 100, 50)
        assert len(result) < 100
        assert "[truncated]" in result
