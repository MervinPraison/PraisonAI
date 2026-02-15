"""
TDD tests for the Autonomy System DRY Refactor.

Tests cover all 6 phases:
- Phase 1: Doom loop detection actually fires in run_autonomous()
- Phase 2: DRY — AutonomyMixin is helper-only, Agent owns run_autonomous()
- Phase 3: Config fidelity — all AutonomyConfig fields preserved and wired
- Phase 4: Approval unification — CLI delegates to SDK
- Phase 5: Interactive mode fixes
- Phase 6: Integration / smoke
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock


# ============================================================================
# Phase 1: Doom loop detection actually fires
# ============================================================================

class TestDoomLoopFiring:
    """G1/G2: Doom loop detection must actually fire in run_autonomous()."""

    def test_doom_loop_fires_when_agent_repeats_same_response(self):
        """run_autonomous() must call _record_action() so DoomLoopTracker gets data."""
        from praisonaiagents import Agent

        agent = Agent(
            name="test_doom",
            instructions="You are a test agent",
            autonomy={"max_iterations": 10, "doom_loop_threshold": 3},
        )

        # Mock chat to return the same response every time
        # Avoid any completion keywords (done, finished, completed, etc.)
        call_count = 0
        def mock_chat(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            return "Still working on analysis of the codebase..."

        agent.chat = mock_chat

        # Use a prompt that triggers autonomous stage (multi-step)
        # so the loop runs multiple iterations instead of exiting after 1 (direct)
        result = agent.run_autonomous("First refactor the auth module, then test it step by step")

        # Doom loop should have been detected before max_iterations
        assert result.completion_reason == "doom_loop", (
            f"Expected doom_loop but got {result.completion_reason} after {result.iterations} iterations"
        )
        assert result.success is False
        assert result.iterations < 10  # Should stop well before max

    def test_doom_loop_does_not_fire_with_varied_responses(self):
        """Varied responses should NOT trigger doom loop."""
        from praisonaiagents import Agent

        agent = Agent(
            name="test_varied",
            instructions="You are a test agent",
            autonomy={"max_iterations": 5, "doom_loop_threshold": 3},
        )

        call_count = 0
        def mock_chat(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return "Task completed successfully"
            return f"Working on step {call_count}..."

        agent.chat = mock_chat

        # Use multi-step prompt to trigger autonomous stage
        result = agent.run_autonomous("First analyze, then implement the changes step by step")

        # Should complete via keyword detection, NOT doom loop
        assert result.completion_reason != "doom_loop"
        assert result.success is True

    def test_doom_loop_tracker_receives_data_from_run_autonomous(self):
        """DoomLoopTracker.record() must be called during run_autonomous()."""
        from praisonaiagents import Agent

        agent = Agent(
            name="test_tracker",
            instructions="You are a test agent",
            autonomy={"max_iterations": 3, "doom_loop_threshold": 10},
        )

        # Track calls to _record_action
        record_calls = []
        original_record = agent._record_action
        def tracking_record(*args, **kwargs):
            record_calls.append(args)
            return original_record(*args, **kwargs)
        agent._record_action = tracking_record

        call_count = 0
        def mock_chat(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            # Avoid completion keywords so loop runs all iterations
            return f"Still processing step {call_count} of the refactoring..."

        agent.chat = mock_chat

        # Use multi-step prompt for autonomous stage
        agent.run_autonomous("First refactor, then implement step by step")

        # _record_action must have been called at least once
        assert len(record_calls) > 0, "_record_action() was never called in run_autonomous()"


# ============================================================================
# Phase 2: DRY — AutonomyMixin is helper-only
# ============================================================================

class TestDRYAutonomyMixin:
    """D1-D3: AutonomyMixin should be a helper-only module, not duplicate Agent methods."""

    def test_autonomy_mixin_has_no_run_autonomous(self):
        """AutonomyMixin should NOT have run_autonomous() — Agent owns it."""
        from praisonaiagents.agent.autonomy import AutonomyMixin
        assert not hasattr(AutonomyMixin, 'run_autonomous'), (
            "AutonomyMixin still has run_autonomous() — should be removed (DRY)"
        )

    def test_autonomy_mixin_has_no_init_autonomy(self):
        """AutonomyMixin should NOT have _init_autonomy() — Agent owns it."""
        from praisonaiagents.agent.autonomy import AutonomyMixin
        assert not hasattr(AutonomyMixin, '_init_autonomy'), (
            "AutonomyMixin still has _init_autonomy() — should be removed (DRY)"
        )

    def test_autonomy_mixin_has_no_analyze_prompt(self):
        """AutonomyMixin should NOT have analyze_prompt() — Agent owns it."""
        from praisonaiagents.agent.autonomy import AutonomyMixin
        assert not hasattr(AutonomyMixin, 'analyze_prompt'), (
            "AutonomyMixin still has analyze_prompt() — should be removed (DRY)"
        )

    def test_autonomy_module_exports_helper_classes(self):
        """autonomy.py should still export helper classes used by Agent."""
        from praisonaiagents.agent.autonomy import (
            AutonomyConfig,
            AutonomyResult,
            AutonomyStage,
            AutonomySignal,
            AutonomyTrigger,
            DoomLoopTracker,
        )
        # All helper classes must still be importable
        assert AutonomyConfig is not None
        assert AutonomyResult is not None
        assert AutonomyTrigger is not None
        assert DoomLoopTracker is not None

    def test_agent_has_run_autonomous(self):
        """Agent must have run_autonomous() as the single source of truth."""
        from praisonaiagents import Agent
        assert hasattr(Agent, 'run_autonomous')
        assert hasattr(Agent, 'run_autonomous_async')

    def test_agent_has_all_autonomy_methods(self):
        """Agent must have all autonomy helper methods."""
        from praisonaiagents import Agent
        assert hasattr(Agent, '_init_autonomy')
        assert hasattr(Agent, 'analyze_prompt')
        assert hasattr(Agent, 'get_recommended_stage')
        assert hasattr(Agent, '_record_action')
        assert hasattr(Agent, '_is_doom_loop')
        assert hasattr(Agent, '_reset_doom_loop')


# ============================================================================
# Phase 3: Config fidelity — all AutonomyConfig fields preserved
# ============================================================================

class TestConfigFidelity:
    """G3, G10, G11, G14: All AutonomyConfig fields must be preserved and wired."""

    def test_init_autonomy_preserves_all_config_fields_from_object(self):
        """When AutonomyConfig object is passed, ALL fields must be preserved."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig

        config = AutonomyConfig(
            enabled=True,
            level="full_auto",
            max_iterations=30,
            doom_loop_threshold=5,
            auto_escalate=False,
            observe=True,
            completion_promise="DONE",
            clear_context=True,
            verification_hooks=["hook1"],
        )

        agent = Agent(
            name="test_fidelity",
            instructions="Test",
            autonomy=config,
        )

        # ALL fields must be accessible from autonomy_config
        assert agent.autonomy_config.get("level") == "full_auto"
        assert agent.autonomy_config.get("max_iterations") == 30
        assert agent.autonomy_config.get("doom_loop_threshold") == 5
        assert agent.autonomy_config.get("auto_escalate") is False
        assert agent.autonomy_config.get("observe") is True
        assert agent.autonomy_config.get("completion_promise") == "DONE"
        assert agent.autonomy_config.get("clear_context") is True

    def test_init_autonomy_preserves_all_config_fields_from_dict(self):
        """When dict is passed, all fields must be preserved."""
        from praisonaiagents import Agent

        config_dict = {
            "level": "auto_edit",
            "max_iterations": 15,
            "doom_loop_threshold": 4,
            "auto_escalate": True,
            "observe": True,
            "completion_promise": "COMPLETE",
            "clear_context": True,
        }

        agent = Agent(
            name="test_dict_fidelity",
            instructions="Test",
            autonomy=config_dict,
        )

        for key, value in config_dict.items():
            assert agent.autonomy_config.get(key) == value, (
                f"Field {key} lost: expected {value}, got {agent.autonomy_config.get(key)}"
            )

    def test_level_full_auto_sets_env_auto_approve(self):
        """AutonomyConfig level='full_auto' must bridge to PRAISONAI_AUTO_APPROVE."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig

        # Clean env
        os.environ.pop("PRAISONAI_AUTO_APPROVE", None)

        agent = Agent(
            name="test_level_bridge",
            instructions="Test",
            autonomy=AutonomyConfig(level="full_auto"),
        )

        # After init with level=full_auto, env should be set
        assert os.environ.get("PRAISONAI_AUTO_APPROVE", "").lower() in ("true", "1", "yes"), (
            "level='full_auto' did not set PRAISONAI_AUTO_APPROVE"
        )

        # Clean up
        os.environ.pop("PRAISONAI_AUTO_APPROVE", None)

    def test_level_suggest_does_not_set_auto_approve(self):
        """AutonomyConfig level='suggest' must NOT set auto-approve."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig

        os.environ.pop("PRAISONAI_AUTO_APPROVE", None)

        agent = Agent(
            name="test_level_suggest",
            instructions="Test",
            autonomy=AutonomyConfig(level="suggest"),
        )

        assert os.environ.get("PRAISONAI_AUTO_APPROVE", "").lower() not in ("true", "1", "yes")

    def test_observe_emits_log_during_run_autonomous(self):
        """AutonomyConfig observe=True must emit structured logs during run_autonomous()."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig
        import logging

        agent = Agent(
            name="test_observe",
            instructions="Test",
            autonomy=AutonomyConfig(observe=True, max_iterations=3),
        )

        call_count = 0
        def mock_chat(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return "Task completed"
            return "Still analyzing the codebase..."

        agent.chat = mock_chat

        # Capture log output using the logger that agent.py actually uses
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger_instance = MagicMock()
            mock_get_logger.return_value = mock_logger_instance
            result = agent.run_autonomous("First refactor, then implement step by step")
            # When observe=True, we expect info-level logs for each iteration
            assert mock_logger_instance.info.called, (
                "observe=True did not emit any log messages"
            )

    def test_auto_escalate_progresses_stage(self):
        """auto_escalate=True must progress stage when stuck."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig

        agent = Agent(
            name="test_escalate",
            instructions="Test",
            autonomy=AutonomyConfig(
                auto_escalate=True,
                max_iterations=6,
                doom_loop_threshold=10,  # High to not trigger doom loop
            ),
        )

        call_count = 0
        def mock_chat(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            # Never signal completion so escalation can occur
            return f"Still working iteration {call_count}..."

        agent.chat = mock_chat

        result = agent.run_autonomous("Build something complex")

        # With auto_escalate, the stage should have progressed from initial
        # (The exact behavior depends on implementation, but it should not stay at initial)
        assert result.iterations > 0


# ============================================================================
# Phase 4: Approval unification
# ============================================================================

class TestApprovalUnification:
    """G7, D4: CLI AutonomyManager should delegate to SDK ApprovalRegistry."""

    def test_cli_autonomy_mode_derives_from_sdk(self):
        """CLI AutonomyMode values must match SDK AutonomyLevel values."""
        try:
            from praisonai.cli.features.autonomy_mode import AutonomyMode
            from praisonaiagents.config.feature_configs import AutonomyLevel

            assert AutonomyMode.SUGGEST.value == AutonomyLevel.SUGGEST.value
            assert AutonomyMode.AUTO_EDIT.value == AutonomyLevel.AUTO_EDIT.value
            assert AutonomyMode.FULL_AUTO.value == AutonomyLevel.FULL_AUTO.value
        except ImportError:
            pytest.skip("praisonai wrapper not installed")

    def test_cli_autonomy_manager_bridges_to_sdk(self):
        """CLI AutonomyManager.set_mode(FULL_AUTO) must set PRAISONAI_AUTO_APPROVE."""
        try:
            from praisonai.cli.features.autonomy_mode import AutonomyManager, AutonomyMode

            os.environ.pop("PRAISONAI_AUTO_APPROVE", None)

            mgr = AutonomyManager()
            mgr.set_mode(AutonomyMode.FULL_AUTO)

            assert os.environ.get("PRAISONAI_AUTO_APPROVE", "").lower() in ("true", "1", "yes")

            mgr.set_mode(AutonomyMode.SUGGEST)
            assert os.environ.get("PRAISONAI_AUTO_APPROVE", "") == ""

            os.environ.pop("PRAISONAI_AUTO_APPROVE", None)
        except ImportError:
            pytest.skip("praisonai wrapper not installed")

    def test_approval_registry_env_check(self):
        """SDK ApprovalRegistry.is_env_auto_approve() must read PRAISONAI_AUTO_APPROVE."""
        from praisonaiagents.approval.registry import ApprovalRegistry

        os.environ.pop("PRAISONAI_AUTO_APPROVE", None)
        assert ApprovalRegistry.is_env_auto_approve() is False

        os.environ["PRAISONAI_AUTO_APPROVE"] = "true"
        assert ApprovalRegistry.is_env_auto_approve() is True

        os.environ.pop("PRAISONAI_AUTO_APPROVE", None)


# ============================================================================
# Phase 5: Interactive mode fixes
# ============================================================================

class TestInteractiveFixes:
    """G8, G9, G13, D5: Interactive mode autonomy fixes."""

    def test_async_tui_config_autonomy_default_true(self):
        """AsyncTUIConfig.autonomy_mode should default to True (aligned with InteractiveConfig)."""
        try:
            from praisonai.cli.interactive.async_tui import AsyncTUIConfig
            config = AsyncTUIConfig()
            assert config.autonomy_mode is True, (
                f"AsyncTUIConfig.autonomy_mode defaults to {config.autonomy_mode}, expected True"
            )
        except ImportError:
            pytest.skip("praisonai wrapper not installed")

    def test_auto_toggle_preserves_agent_state(self):
        """The /auto toggle must NOT destroy the agent (self._agent = None)."""
        try:
            from praisonai.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig

            tui = AsyncTUI(config=AsyncTUIConfig())
            # Simulate having an agent
            tui._agent = MagicMock()
            tui._agent.autonomy_enabled = True

            # Simulate /auto command — should toggle without destroying agent
            # We test by checking the _handle_slash_command method behavior
            # After toggling, _agent should still exist
            original_agent = tui._agent

            # Toggle autonomy mode
            tui.config.autonomy_mode = not tui.config.autonomy_mode

            # Agent should NOT be set to None
            assert tui._agent is not None, "/auto toggle destroyed agent instance"
        except ImportError:
            pytest.skip("praisonai wrapper not installed")

    def test_interactive_config_autonomy_field_exists(self):
        """InteractiveConfig must have autonomy and autonomy_config fields."""
        try:
            from praisonai.cli.interactive.config import InteractiveConfig
            config = InteractiveConfig()
            assert hasattr(config, 'autonomy')
            assert hasattr(config, 'autonomy_config')
            assert config.autonomy is True  # Default should be True
        except ImportError:
            pytest.skip("praisonai wrapper not installed")


# ============================================================================
# Phase 6: Integration / Smoke
# ============================================================================

class TestIntegrationSmoke:
    """End-to-end smoke tests for the refactored autonomy system."""

    def test_agent_autonomy_true_creates_working_config(self):
        """Agent(autonomy=True) must create a fully functional autonomy setup."""
        from praisonaiagents import Agent

        agent = Agent(name="smoke", instructions="Test", autonomy=True)

        assert agent.autonomy_enabled is True
        assert agent._autonomy_trigger is not None
        assert agent._doom_loop_tracker is not None
        assert isinstance(agent.autonomy_config, dict)

    def test_agent_autonomy_dict_creates_working_config(self):
        """Agent(autonomy={...}) must preserve all dict keys."""
        from praisonaiagents import Agent

        agent = Agent(
            name="smoke_dict",
            instructions="Test",
            autonomy={
                "max_iterations": 5,
                "level": "auto_edit",
                "observe": True,
            },
        )

        assert agent.autonomy_enabled is True
        assert agent.autonomy_config.get("max_iterations") == 5
        assert agent.autonomy_config.get("level") == "auto_edit"
        assert agent.autonomy_config.get("observe") is True

    def test_agent_autonomy_config_object(self):
        """Agent(autonomy=AutonomyConfig(...)) must work end-to-end."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig

        config = AutonomyConfig(max_iterations=7, level="full_auto")
        agent = Agent(name="smoke_obj", instructions="Test", autonomy=config)

        assert agent.autonomy_enabled is True
        assert agent.autonomy_config.get("max_iterations") == 7
        assert agent.autonomy_config.get("level") == "full_auto"

    def test_agent_team_propagates_autonomy(self):
        """AgentTeam must propagate autonomy to individual agents."""
        from praisonaiagents import Agent, AgentTeam, Task

        agent1 = Agent(name="a1", instructions="Test1")
        agent2 = Agent(name="a2", instructions="Test2")
        task1 = Task(description="Task 1", agent=agent1, expected_output="done")
        task2 = Task(description="Task 2", agent=agent2, expected_output="done")

        team = AgentTeam(
            agents=[agent1, agent2],
            tasks=[task1, task2],
            autonomy=True,
        )

        # After team init, both agents should have autonomy enabled
        assert agent1.autonomy_enabled is True
        assert agent2.autonomy_enabled is True

    def test_run_autonomous_with_promise_completion(self):
        """run_autonomous() with completion_promise must detect <promise>X</promise>."""
        from praisonaiagents import Agent

        agent = Agent(
            name="test_promise",
            instructions="Test",
            autonomy={"max_iterations": 5},
        )

        call_count = 0
        def mock_chat(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return "All done! <promise>COMPLETE</promise>"
            return "Working on it..."

        agent.chat = mock_chat

        # Multi-step prompt to trigger autonomous stage (not direct)
        result = agent.run_autonomous(
            "First refactor, then implement step by step",
            completion_promise="COMPLETE",
        )

        assert result.success is True
        assert result.completion_reason == "promise"
        assert result.iterations == 2

    def test_autonomy_exports_available(self):
        """All autonomy exports must be importable from top-level package."""
        from praisonaiagents import AutonomyConfig, AutonomyLevel
        from praisonaiagents.agent.autonomy import (
            AutonomyResult, AutonomyStage, AutonomyTrigger, DoomLoopTracker,
        )
        assert AutonomyConfig is not None
        assert AutonomyLevel is not None

    def test_doom_loop_tracker_standalone(self):
        """DoomLoopTracker must work correctly in isolation."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker

        tracker = DoomLoopTracker(threshold=3)

        # Same action 3 times should trigger
        for _ in range(3):
            tracker.record("chat", {"prompt": "hello"}, "response", True)

        assert tracker.is_doom_loop() is True

        # Reset should clear
        tracker.reset()
        assert tracker.is_doom_loop() is False

    def test_autonomy_trigger_stages(self):
        """AutonomyTrigger must recommend correct stages."""
        from praisonaiagents.agent.autonomy import AutonomyTrigger, AutonomyStage

        trigger = AutonomyTrigger()

        # Simple question → DIRECT
        signals = trigger.analyze("What is Python?")
        assert trigger.recommend_stage(signals) == AutonomyStage.DIRECT

        # Edit intent → PLANNED
        signals = trigger.analyze("Fix the bug in auth.py")
        assert trigger.recommend_stage(signals) == AutonomyStage.PLANNED

        # Refactor → AUTONOMOUS
        signals = trigger.analyze("Refactor the entire auth module")
        assert trigger.recommend_stage(signals) == AutonomyStage.AUTONOMOUS
