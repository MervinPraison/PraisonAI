"""
TDD tests for autonomy mode redesign.

Tests the new `mode` field in AutonomyConfig and the caller-mode behavior
where autonomy=True does a single chat() call instead of the internal loop.
"""
import pytest
from unittest.mock import patch, MagicMock


# ============================================================================
# 1. AutonomyConfig mode field tests
# ============================================================================

class TestAutonomyConfigMode:
    """Tests for the 'mode' field on AutonomyConfig."""

    def test_mode_field_exists(self):
        """AutonomyConfig should have a mode field."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig()
        assert hasattr(config, 'mode'), "AutonomyConfig must have a 'mode' field"

    def test_default_mode_is_caller_for_suggest(self):
        """Default level='suggest' should default to mode='caller'."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig(level="suggest")
        assert config.mode == "caller"

    def test_default_mode_is_caller_for_auto_edit(self):
        """level='auto_edit' should default to mode='caller'."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig(level="auto_edit")
        assert config.mode == "caller"

    def test_default_mode_is_iterative_for_full_auto(self):
        """level='full_auto' should default to mode='iterative' (backward compat)."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig(level="full_auto")
        assert config.mode == "iterative"

    def test_explicit_mode_overrides_default(self):
        """Explicit mode should override the level-based default."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig(level="full_auto", mode="caller")
        assert config.mode == "caller"

    def test_explicit_iterative_with_suggest(self):
        """Should be able to set mode='iterative' even with level='suggest'."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig(level="suggest", mode="iterative")
        assert config.mode == "iterative"

    def test_invalid_mode_raises(self):
        """Invalid mode value should raise ValueError."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        with pytest.raises(ValueError, match="Invalid autonomy mode"):
            AutonomyConfig(mode="invalid_mode")

    def test_from_dict_with_mode(self):
        """AutonomyConfig.from_dict should parse mode field."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig.from_dict({"mode": "iterative"})
        assert config.mode == "iterative"

    def test_from_dict_without_mode_uses_smart_default(self):
        """from_dict without mode should use smart default based on level."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig.from_dict({"level": "full_auto"})
        assert config.mode == "iterative"

    def test_from_dict_suggest_defaults_to_caller(self):
        """from_dict with suggest level defaults to caller mode."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig.from_dict({"level": "suggest"})
        assert config.mode == "caller"


# ============================================================================
# 2. Agent _init_autonomy stores mode in autonomy_config dict
# ============================================================================

class TestAgentAutonomyModeInit:
    """Tests that Agent._init_autonomy correctly stores mode."""

    def _make_agent(self, **autonomy_kwargs):
        """Helper to create a minimal agent with autonomy config."""
        from praisonaiagents import Agent
        return Agent(
            name="test_mode",
            instructions="test",
            autonomy=autonomy_kwargs if autonomy_kwargs else True,
        )

    def test_autonomy_true_stores_mode(self):
        """Agent(autonomy=True) should store mode in autonomy_config."""
        agent = self._make_agent()
        assert "mode" in agent.autonomy_config, "autonomy_config must contain 'mode'"

    def test_autonomy_true_default_mode_is_caller(self):
        """Agent(autonomy=True) defaults to level='suggest', so mode='caller'."""
        agent = self._make_agent()
        assert agent.autonomy_config["mode"] == "caller"

    def test_autonomy_dict_full_auto_mode_iterative(self):
        """Agent(autonomy={'level':'full_auto'}) should default to mode='iterative'."""
        agent = self._make_agent(level="full_auto")
        assert agent.autonomy_config["mode"] == "iterative"

    def test_autonomy_dict_explicit_mode(self):
        """Agent(autonomy={'mode':'iterative'}) should store explicit mode."""
        agent = self._make_agent(mode="iterative")
        assert agent.autonomy_config["mode"] == "iterative"


# ============================================================================
# 3. start() caller-mode behavior
# ============================================================================

class TestStartCallerMode:
    """Tests that start() in caller mode does a single chat() call."""

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_caller_mode_calls_chat_once(self, mock_chat):
        """In caller mode, start() should call chat() exactly once."""
        mock_chat.return_value = "Hello! I'm here to help."
        from praisonaiagents import Agent
        agent = Agent(
            name="test_caller",
            instructions="You are helpful",
            autonomy=True,  # level=suggest → mode=caller
        )
        result = agent.start("Say hello")

        mock_chat.assert_called_once()

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_caller_mode_does_not_call_run_autonomous(self, mock_chat):
        """In caller mode, start() must NOT call run_autonomous."""
        mock_chat.return_value = "Done"
        from praisonaiagents import Agent
        agent = Agent(
            name="test_no_loop",
            instructions="You are helpful",
            autonomy=True,
        )
        with patch.object(agent, 'run_autonomous') as mock_autonomous:
            agent.start("Do something")
            mock_autonomous.assert_not_called()

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_caller_mode_returns_autonomy_result(self, mock_chat):
        """In caller mode, start() should return AutonomyResult."""
        mock_chat.return_value = "Task completed successfully"
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyResult
        agent = Agent(
            name="test_result",
            instructions="You are helpful",
            autonomy=True,
        )
        result = agent.start("Do task")

        assert isinstance(result, AutonomyResult)
        assert result.iterations == 1
        assert result.success is True
        assert result.completion_reason == "caller_mode"
        assert "Task completed" in str(result)

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_caller_mode_preserves_auto_approve(self, mock_chat):
        """Caller mode should still have auto-approve wired."""
        mock_chat.return_value = "Done"
        from praisonaiagents import Agent
        agent = Agent(
            name="test_approve",
            instructions="test",
            autonomy={"level": "auto_edit"},
        )
        # auto_edit should wire approval
        assert agent.autonomy_enabled is True
        assert agent.autonomy_config.get("mode") == "caller"


# ============================================================================
# 4. start() iterative-mode behavior (backward compat for full_auto)
# ============================================================================

class TestStartIterativeMode:
    """Tests that start() in iterative mode uses run_autonomous (backward compat)."""

    @patch("praisonaiagents.agent.agent.Agent.run_autonomous")
    def test_iterative_mode_calls_run_autonomous(self, mock_run):
        """In iterative mode, start() should call run_autonomous."""
        from praisonaiagents.agent.autonomy import AutonomyResult
        mock_run.return_value = AutonomyResult(
            success=True, output="Done", completion_reason="goal",
            iterations=1, stage="direct", actions=[], duration_seconds=1.0,
        )
        from praisonaiagents import Agent
        agent = Agent(
            name="test_iterative",
            instructions="test",
            autonomy={"level": "full_auto"},  # defaults to iterative
        )
        agent.start("Do something complex")
        mock_run.assert_called_once()

    @patch("praisonaiagents.agent.agent.Agent.run_autonomous")
    def test_explicit_iterative_mode_with_suggest(self, mock_run):
        """Explicit mode='iterative' should use run_autonomous."""
        from praisonaiagents.agent.autonomy import AutonomyResult
        mock_run.return_value = AutonomyResult(
            success=True, output="Done", completion_reason="goal",
            iterations=1, stage="direct", actions=[], duration_seconds=1.0,
        )
        from praisonaiagents import Agent
        agent = Agent(
            name="test_explicit_iterative",
            instructions="test",
            autonomy={"level": "suggest", "mode": "iterative"},
        )
        agent.start("Ralph loop task")
        mock_run.assert_called_once()


# ============================================================================
# 5. astart() caller-mode behavior (async parity)
# ============================================================================

class TestAstartCallerMode:
    """Tests that astart() in caller mode does a single achat() call."""

    @pytest.mark.asyncio
    async def test_caller_mode_achat_once(self):
        """In caller mode, astart() should call achat() exactly once."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyResult
        agent = Agent(
            name="test_async_caller",
            instructions="You are helpful",
            autonomy=True,
        )
        with patch.object(agent, 'achat', return_value="Hello async!") as mock_achat:
            result = await agent.astart("Say hello")
            mock_achat.assert_called_once()
            assert isinstance(result, AutonomyResult)
            assert result.iterations == 1
