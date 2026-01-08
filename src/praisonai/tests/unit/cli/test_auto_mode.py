"""
Tests for Auto Mode Handler.

TDD tests for CLI auto mode integration with escalation pipeline.
"""

import pytest
from unittest.mock import Mock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from praisonai.cli.features.auto_mode import (
    AutoModeHandler,
    AutoModeConfig,
    AutoModeState,
    AutoModeLevel,
    RouterMode,
    auto_execute,
)


class TestAutoModeLevel:
    """Tests for AutoModeLevel enum."""
    
    def test_mode_values(self):
        """Test mode enum values."""
        assert AutoModeLevel.OFF.value == "off"
        assert AutoModeLevel.SUGGEST.value == "suggest"
        assert AutoModeLevel.AUTO.value == "auto"
        assert AutoModeLevel.FULL_AUTO.value == "full_auto"


class TestRouterMode:
    """Tests for RouterMode enum."""
    
    def test_router_mode_values(self):
        """Test router mode values."""
        assert RouterMode.HEURISTIC.value == "heuristic"
        assert RouterMode.TRAINED.value == "trained"
        assert RouterMode.OFF.value == "off"


class TestAutoModeConfig:
    """Tests for AutoModeConfig."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = AutoModeConfig()
        
        assert config.mode == AutoModeLevel.AUTO
        assert config.dry_run is False
        assert config.budget_steps == 50
        assert config.budget_time_seconds == 300
        assert config.budget_tokens == 100000
        assert config.enable_checkpoints is True
        assert config.router_mode == RouterMode.HEURISTIC
    
    def test_from_cli_args_basic(self):
        """Test config from basic CLI args."""
        config = AutoModeConfig.from_cli_args(
            budget_steps=20,
            budget_time=60,
        )
        
        assert config.budget_steps == 20
        assert config.budget_time_seconds == 60
    
    def test_from_cli_args_dry_run(self):
        """Test config with dry run."""
        config = AutoModeConfig.from_cli_args(dry_run=True)
        assert config.dry_run is True
        
        config = AutoModeConfig.from_cli_args(apply=True)
        assert config.dry_run is False
    
    def test_from_cli_args_mode(self):
        """Test config with different modes."""
        config = AutoModeConfig.from_cli_args(auto=False)
        assert config.mode == AutoModeLevel.OFF
        
        config = AutoModeConfig.from_cli_args(full_auto=True)
        assert config.mode == AutoModeLevel.FULL_AUTO
        
        config = AutoModeConfig.from_cli_args(suggest=True)
        assert config.mode == AutoModeLevel.SUGGEST
    
    def test_from_cli_args_tools(self):
        """Test config with tool filters."""
        config = AutoModeConfig.from_cli_args(
            allow_tools="read_file,grep",
            deny_tools="write_file,bash",
        )
        
        assert "read_file" in config.allow_tools
        assert "grep" in config.allow_tools
        assert "write_file" in config.deny_tools
        assert "bash" in config.deny_tools
    
    def test_from_cli_args_checkpoint(self):
        """Test config with checkpoint settings."""
        config = AutoModeConfig.from_cli_args(checkpoint=False)
        assert config.enable_checkpoints is False
        
        config = AutoModeConfig.from_cli_args(no_checkpoint=True)
        assert config.enable_checkpoints is False
    
    def test_from_cli_args_router(self):
        """Test config with router mode."""
        config = AutoModeConfig.from_cli_args(router="off")
        assert config.router_mode == RouterMode.OFF
        
        config = AutoModeConfig.from_cli_args(router="trained")
        assert config.router_mode == RouterMode.TRAINED


class TestAutoModeState:
    """Tests for AutoModeState."""
    
    def test_initial_state(self):
        """Test initial state values."""
        state = AutoModeState()
        
        assert state.current_stage == 0
        assert state.steps_taken == 0
        assert state.tokens_used == 0
        assert state.tool_calls == 0
        assert len(state.errors) == 0
    
    def test_is_within_budget(self):
        """Test budget checking."""
        config = AutoModeConfig(
            budget_steps=10,
            budget_time_seconds=60,
            budget_tokens=1000,
        )
        state = AutoModeState()
        
        # Initially within budget
        assert state.is_within_budget(config)
        
        # Exceed steps
        state.steps_taken = 15
        assert not state.is_within_budget(config)
        
        # Reset and exceed time
        state.steps_taken = 5
        state.time_elapsed = 120
        assert not state.is_within_budget(config)
    
    def test_get_budget_status(self):
        """Test budget status reporting."""
        config = AutoModeConfig(
            budget_steps=100,
            budget_time_seconds=300,
        )
        state = AutoModeState(
            steps_taken=50,
            time_elapsed=150,
        )
        
        status = state.get_budget_status(config)
        
        assert status["steps"]["used"] == 50
        assert status["steps"]["limit"] == 100
        assert status["steps"]["percent"] == 50.0
        
        assert status["time"]["used"] == 150
        assert status["time"]["percent"] == 50.0


class TestAutoModeHandler:
    """Tests for AutoModeHandler."""
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = AutoModeHandler()
        
        assert handler.feature_name == "auto_mode"
        assert handler.get_config() is None
        assert handler.get_state() is None
    
    def test_parse_args(self):
        """Test argument parsing."""
        handler = AutoModeHandler()
        
        config = handler.parse_args(
            budget_steps=30,
            dry_run=True,
        )
        
        assert config.budget_steps == 30
        assert config.dry_run is True
        assert handler.get_config() is config
        assert handler.get_state() is not None
    
    def test_filter_tools_allow_list(self):
        """Test tool filtering with allow list."""
        handler = AutoModeHandler()
        handler.parse_args(allow_tools="read_file,grep")
        
        mock_tools = [
            Mock(__name__="read_file"),
            Mock(__name__="write_file"),
            Mock(__name__="grep"),
            Mock(__name__="bash"),
        ]
        
        filtered = handler._filter_tools(mock_tools)
        
        names = [t.__name__ for t in filtered]
        assert "read_file" in names
        assert "grep" in names
        assert "write_file" not in names
        assert "bash" not in names
    
    def test_filter_tools_deny_list(self):
        """Test tool filtering with deny list."""
        handler = AutoModeHandler()
        handler.parse_args(deny_tools="bash,write_file")
        
        mock_tools = [
            Mock(__name__="read_file"),
            Mock(__name__="write_file"),
            Mock(__name__="grep"),
            Mock(__name__="bash"),
        ]
        
        filtered = handler._filter_tools(mock_tools)
        
        names = [t.__name__ for t in filtered]
        assert "read_file" in names
        assert "grep" in names
        assert "write_file" not in names
        assert "bash" not in names
    
    def test_get_cli_options(self):
        """Test CLI option definitions."""
        handler = AutoModeHandler()
        
        options = handler.get_cli_options()
        
        assert len(options) > 0
        option_names = [o["name"] for o in options]
        assert "--auto/--no-auto" in option_names
        assert "--dry-run" in option_names
        assert "--budget-steps" in option_names
    
    @pytest.mark.asyncio
    async def test_execute_without_agent(self):
        """Test execution without agent."""
        handler = AutoModeHandler()
        handler.parse_args()
        
        result = await handler.execute("Test prompt")
        
        # Should fail gracefully without agent
        assert "success" in result
    
    @pytest.mark.asyncio
    async def test_execute_with_mock_agent(self):
        """Test execution with mock agent."""
        handler = AutoModeHandler()
        handler.parse_args()
        
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Hello!")
        
        result = await handler.execute("Test prompt", agent=mock_agent)
        
        assert result["success"]
        assert "Hello" in result["response"]
    
    def test_stage_change_callback(self):
        """Test stage change callback."""
        callback_calls = []
        
        def on_change(old, new):
            callback_calls.append((old, new))
        
        handler = AutoModeHandler(on_stage_change=on_change)
        
        # Simulate stage change
        class MockStage:
            def __init__(self, val, name):
                self.value = val
                self.name = name
        
        handler._state = AutoModeState()
        handler._handle_stage_change(
            MockStage(0, "DIRECT"),
            MockStage(1, "HEURISTIC")
        )
        
        assert len(callback_calls) == 1
        assert callback_calls[0] == (0, 1)


class TestAutoExecuteFunction:
    """Tests for auto_execute convenience function."""
    
    @pytest.mark.asyncio
    async def test_auto_execute_basic(self):
        """Test basic auto_execute call."""
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Done")
        
        result = await auto_execute(
            "Test prompt",
            agent=mock_agent,
            budget_steps=10,
        )
        
        assert "success" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
