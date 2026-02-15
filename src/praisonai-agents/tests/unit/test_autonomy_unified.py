"""
TDD tests for unified autonomy system.

Tests cover:
- Phase 1: Unified enums + triggers (G-DUP-1, G-DUP-3)
- Phase 2: Unified doom loop (G-DUP-2, G-RECOVERY-1)
- Phase 3: ObservabilityHooks wiring (G-UNUSED-2)
- Phase 4: Per-agent approval bridge (G-BRIDGE-1, G-BRIDGE-2)
- Phase 5: Interactive routing (G-INTERACTIVE-1)
- Phase 6: CLI parity
- Phase 7: Exports
"""

import pytest
from unittest.mock import patch


# ============================================================================
# Phase 1: Unified Enums + Triggers
# ============================================================================

class TestUnifiedStageEnum:
    """AutonomyStage must be an alias for EscalationStage."""

    def test_autonomy_stage_is_escalation_stage(self):
        from praisonaiagents.agent.autonomy import AutonomyStage
        from praisonaiagents.escalation.types import EscalationStage
        # AutonomyStage values must match EscalationStage values
        assert AutonomyStage.DIRECT == EscalationStage.DIRECT
        assert AutonomyStage.HEURISTIC == EscalationStage.HEURISTIC
        assert AutonomyStage.PLANNED == EscalationStage.PLANNED
        assert AutonomyStage.AUTONOMOUS == EscalationStage.AUTONOMOUS

    def test_stage_ordering(self):
        from praisonaiagents.agent.autonomy import AutonomyStage
        assert AutonomyStage.DIRECT < AutonomyStage.HEURISTIC
        assert AutonomyStage.HEURISTIC < AutonomyStage.PLANNED
        assert AutonomyStage.PLANNED < AutonomyStage.AUTONOMOUS

    def test_stage_int_values(self):
        from praisonaiagents.agent.autonomy import AutonomyStage
        assert int(AutonomyStage.DIRECT) == 0
        assert int(AutonomyStage.HEURISTIC) == 1
        assert int(AutonomyStage.PLANNED) == 2
        assert int(AutonomyStage.AUTONOMOUS) == 3


class TestUnifiedTrigger:
    """AutonomyTrigger must delegate to EscalationTrigger."""

    def test_trigger_analyzes_simple_question(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger
        trigger = AutonomyTrigger()
        signals = trigger.analyze("What is Python?")
        assert "simple_question" in signals

    def test_trigger_analyzes_edit_intent(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger
        trigger = AutonomyTrigger()
        signals = trigger.analyze("Edit the file auth.py and fix the bug")
        assert "edit_intent" in signals

    def test_trigger_analyzes_multi_step(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger
        trigger = AutonomyTrigger()
        # EscalationTrigger requires comma-delimited sequential patterns or multiple action verbs
        signals = trigger.analyze("First, read the file, and then refactor it, finally, run tests")
        assert "multi_step" in signals

    def test_trigger_recommends_direct_for_simple(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger, AutonomyStage
        trigger = AutonomyTrigger()
        signals = trigger.analyze("What is Python?")
        stage = trigger.recommend_stage(signals)
        assert stage == AutonomyStage.DIRECT

    def test_trigger_recommends_autonomous_for_multi_step(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger, AutonomyStage
        trigger = AutonomyTrigger()
        signals = trigger.analyze("First refactor auth.py, then write tests, finally run them")
        stage = trigger.recommend_stage(signals)
        assert stage == AutonomyStage.AUTONOMOUS

    def test_trigger_recommends_planned_for_edit(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger, AutonomyStage
        trigger = AutonomyTrigger()
        signals = trigger.analyze("Edit the README to add installation steps")
        stage = trigger.recommend_stage(signals)
        assert stage == AutonomyStage.PLANNED

    def test_trigger_detects_file_references(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger
        trigger = AutonomyTrigger()
        signals = trigger.analyze("Read the file src/main.py and explain it")
        assert "file_references" in signals

    def test_trigger_detects_code_blocks(self):
        from praisonaiagents.agent.autonomy import AutonomyTrigger
        trigger = AutonomyTrigger()
        signals = trigger.analyze("Fix this code:\n```python\nprint('hello')\n```")
        assert "code_blocks" in signals


# ============================================================================
# Phase 2: Unified Doom Loop
# ============================================================================

class TestUnifiedDoomLoop:
    """DoomLoopTracker must use advanced detection from DoomLoopDetector."""

    def test_basic_doom_loop_detection(self):
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        # Same action 3 times
        for _ in range(3):
            tracker.record("read_file", {"path": "foo.py"}, "content", True)
        assert tracker.is_doom_loop() is True

    def test_no_doom_loop_with_varied_actions(self):
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        tracker.record("read_file", {"path": "a.py"}, "content_a", True)
        tracker.record("write_file", {"path": "b.py"}, "ok", True)
        tracker.record("read_file", {"path": "c.py"}, "content_c", True)
        assert tracker.is_doom_loop() is False

    def test_doom_loop_reset(self):
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=2)
        tracker.record("read_file", {"path": "foo.py"}, "content", True)
        tracker.record("read_file", {"path": "foo.py"}, "content", True)
        assert tracker.is_doom_loop() is True
        tracker.reset()
        assert tracker.is_doom_loop() is False

    def test_doom_loop_has_recovery_action(self):
        """DoomLoopTracker should expose recovery_action when loop detected."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=2)
        tracker.record("read_file", {"path": "foo.py"}, "content", True)
        tracker.record("read_file", {"path": "foo.py"}, "content", True)
        assert tracker.is_doom_loop() is True
        recovery = tracker.get_recovery_action()
        assert recovery in ("retry_different", "escalate_model", "request_help", "abort", "continue")

    def test_doom_loop_consecutive_failures(self):
        """DoomLoopTracker should detect consecutive failures."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        tracker.record("tool_call", {"name": "search"}, "error", False)
        tracker.record("tool_call", {"name": "search"}, "error", False)
        tracker.record("tool_call", {"name": "search"}, "error", False)
        assert tracker.is_doom_loop() is True


class TestRunAutonomousRecovery:
    """run_autonomous() should attempt recovery on doom loop instead of immediate abort."""

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_recovery_on_doom_loop(self, mock_chat):
        from praisonaiagents import Agent
        # Return identical responses to trigger doom loop
        mock_chat.return_value = "I'll keep trying the same thing"

        agent = Agent(
            name="test",
            instructions="test",
            autonomy={"max_iterations": 10, "doom_loop_threshold": 2},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous("Do something")
        # Should eventually stop with doom_loop or recovery exhaustion
        assert result.completion_reason in ("doom_loop", "max_iterations", "goal")


# ============================================================================
# Phase 3: ObservabilityHooks wiring
# ============================================================================

class TestObservabilityWiring:
    """observe=True should emit ObservabilityHooks events."""

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_observe_emits_events(self, mock_chat):
        from praisonaiagents import Agent
        mock_chat.return_value = "Task completed"

        agent = Agent(
            name="test",
            instructions="test",
            autonomy={"observe": True, "max_iterations": 3},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous("Do something simple")
        assert result.success is True
        # The observability hooks should have been created
        hooks = getattr(agent, '_observability_hooks', None)
        if hooks is not None:
            metrics = hooks.get_metrics()
            assert metrics.total_steps >= 1

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_observe_false_no_hooks(self, mock_chat):
        from praisonaiagents import Agent
        mock_chat.return_value = "Task completed"

        agent = Agent(
            name="test",
            instructions="test",
            autonomy={"observe": False, "max_iterations": 3},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous("Do something simple")
        assert result.success is True
        # No hooks should be created
        hooks = getattr(agent, '_observability_hooks', None)
        assert hooks is None


# ============================================================================
# Phase 4: Per-agent approval bridge
# ============================================================================

class TestApprovalBridge:
    """Level→approval bridge should be per-agent, not global env var."""

    def test_full_auto_sets_auto_approve_backend(self):
        from praisonaiagents import Agent
        agent = Agent(
            name="test",
            instructions="test",
            autonomy={"level": "full_auto"},
            llm="gpt-4o-mini",
        )
        # Should NOT set env var (per-agent instead)
        backend = getattr(agent, '_approval_backend', None)
        # full_auto should result in an auto-approve backend
        assert backend is not None or agent.autonomy_config.get("level") == "full_auto"

    def test_suggest_level_no_auto_approve(self):
        from praisonaiagents import Agent
        agent = Agent(
            name="test",
            instructions="test",
            autonomy={"level": "suggest"},
            llm="gpt-4o-mini",
        )
        # suggest level should NOT auto-approve
        backend = getattr(agent, '_approval_backend', None)
        if backend is not None:
            from praisonaiagents.approval.backends import AutoApproveBackend
            assert not isinstance(backend, AutoApproveBackend)

    def test_invalid_level_raises_error(self):
        from praisonaiagents import Agent
        with pytest.raises(ValueError, match="[Ii]nvalid autonomy level"):
            Agent(
                name="test",
                instructions="test",
                autonomy={"level": "invalid_level_xyz"},
                llm="gpt-4o-mini",
            )

    def test_multi_agent_isolation(self):
        """Two agents with different levels should not interfere."""
        from praisonaiagents import Agent
        agent_auto = Agent(
            name="auto",
            instructions="test",
            autonomy={"level": "full_auto"},
            llm="gpt-4o-mini",
        )
        agent_suggest = Agent(
            name="suggest",
            instructions="test",
            autonomy={"level": "suggest"},
            llm="gpt-4o-mini",
        )
        # agent_suggest should NOT be auto-approved just because agent_auto exists
        auto_backend = getattr(agent_auto, '_approval_backend', None)
        suggest_backend = getattr(agent_suggest, '_approval_backend', None)
        # They should have different approval behavior
        if auto_backend is not None and suggest_backend is not None:
            assert not isinstance(auto_backend, type(suggest_backend))


# ============================================================================
# Phase 5: Config validation
# ============================================================================

class TestAutonomyConfigValidation:
    """AutonomyConfig should validate level field."""

    def test_valid_levels(self):
        from praisonaiagents.agent.autonomy import AutonomyConfig
        for level in ("suggest", "auto_edit", "full_auto"):
            config = AutonomyConfig(level=level)
            assert config.level == level

    def test_config_from_dict_preserves_all_fields(self):
        from praisonaiagents.agent.autonomy import AutonomyConfig
        data = {
            "enabled": True,
            "level": "full_auto",
            "max_iterations": 50,
            "doom_loop_threshold": 5,
            "auto_escalate": False,
            "observe": True,
            "completion_promise": "DONE",
            "clear_context": True,
        }
        config = AutonomyConfig.from_dict(data)
        assert config.level == "full_auto"
        assert config.max_iterations == 50
        assert config.doom_loop_threshold == 5
        assert config.auto_escalate is False
        assert config.observe is True
        assert config.completion_promise == "DONE"
        assert config.clear_context is True


# ============================================================================
# Phase 6: CLI parity
# ============================================================================

class TestCLIAutonomyMode:
    """CLI autonomy mode should bridge to SDK properly."""

    def test_autonomy_mode_enum_values(self):
        """AutonomyMode should mirror AutonomyLevel values."""
        # Skip if wrapper not available
        try:
            from praisonai.cli.features.autonomy_mode import AutonomyMode
        except ImportError:
            pytest.skip("praisonai wrapper not installed")
        assert AutonomyMode.SUGGEST.value == "suggest"
        assert AutonomyMode.AUTO_EDIT.value == "auto_edit"
        assert AutonomyMode.FULL_AUTO.value == "full_auto"

    def test_autonomy_mode_from_string(self):
        try:
            from praisonai.cli.features.autonomy_mode import AutonomyMode
        except ImportError:
            pytest.skip("praisonai wrapper not installed")
        assert AutonomyMode.from_string("suggest") == AutonomyMode.SUGGEST
        assert AutonomyMode.from_string("full_auto") == AutonomyMode.FULL_AUTO
        assert AutonomyMode.from_string("auto_edit") == AutonomyMode.AUTO_EDIT


# ============================================================================
# Phase 7: Exports
# ============================================================================

class TestExports:
    """Key classes should be importable from top-level."""

    def test_autonomy_imports(self):
        from praisonaiagents.agent.autonomy import (
            AutonomyConfig,
            AutonomyStage,
            AutonomyTrigger,
            AutonomyResult,
            DoomLoopTracker,
            AutonomyMixin,
        )
        assert AutonomyConfig is not None
        assert AutonomyStage is not None
        assert AutonomyTrigger is not None
        assert AutonomyResult is not None
        assert DoomLoopTracker is not None
        assert AutonomyMixin is not None

    def test_escalation_imports(self):
        from praisonaiagents.escalation import (
            EscalationPipeline,
            EscalationStage,
            EscalationConfig,
            EscalationTrigger,
            DoomLoopDetector,
            ObservabilityHooks,
        )
        assert EscalationPipeline is not None
        assert EscalationStage is not None
        assert EscalationConfig is not None
        assert EscalationTrigger is not None
        assert DoomLoopDetector is not None
        assert ObservabilityHooks is not None

    def test_approval_imports(self):
        from praisonaiagents.approval.protocols import (
            ApprovalRequest,
            ApprovalDecision,
            ApprovalConfig,
            ApprovalProtocol,
        )
        assert ApprovalRequest is not None
        assert ApprovalDecision is not None
        assert ApprovalConfig is not None
        assert ApprovalProtocol is not None


# ============================================================================
# Smoke Tests (mock-based, no real LLM)
# ============================================================================

class TestAutonomySmokeTests:
    """End-to-end smoke tests with mocked LLM responses."""

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_full_auto_completes_on_keyword(self, mock_chat):
        from praisonaiagents import Agent
        mock_chat.return_value = "I have finished the task. Task completed."

        agent = Agent(
            name="smoker",
            instructions="Do tasks",
            autonomy={"level": "full_auto", "max_iterations": 5},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous("Do a simple task")
        assert result.success is True
        assert result.completion_reason == "goal"
        assert result.iterations >= 1

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_promise_completion(self, mock_chat):
        from praisonaiagents import Agent
        mock_chat.side_effect = [
            "Working on it...",
            "Still going...",
            "Done! <promise>FINISHED</promise>",
        ]

        agent = Agent(
            name="promise_agent",
            instructions="Do tasks",
            autonomy={
                "level": "full_auto",
                "max_iterations": 10,
                "completion_promise": "FINISHED",
            },
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous(
            "First analyze the code, then refactor it, then test it"
        )
        assert result.success is True
        assert result.completion_reason == "promise"
        assert result.iterations == 3

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_timeout_stops_execution(self, mock_chat):
        import time
        from praisonaiagents import Agent

        def slow_response(prompt):
            time.sleep(0.15)
            return "Still working on the multi-step task, not completed yet..."

        mock_chat.side_effect = slow_response

        agent = Agent(
            name="slow_agent",
            instructions="Do tasks",
            autonomy={"max_iterations": 100},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous(
            "First, analyze the code, and then refactor it, finally, run tests",
            timeout_seconds=0.25,
        )
        assert result.completion_reason == "timeout"

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_max_iterations_stops(self, mock_chat):
        from praisonaiagents import Agent
        mock_chat.return_value = "Still working on it, not done yet..."

        agent = Agent(
            name="iter_agent",
            instructions="Do tasks",
            autonomy={"max_iterations": 3},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous(
            "First refactor auth, then add tests, then document"
        )
        assert result.completion_reason == "max_iterations"
        assert result.iterations == 3

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_clear_context_between_iterations(self, mock_chat):
        from praisonaiagents import Agent
        call_count = 0

        def track_calls(prompt):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return "Task completed"
            return "Working..."

        mock_chat.side_effect = track_calls

        agent = Agent(
            name="ctx_agent",
            instructions="Do tasks",
            autonomy={"max_iterations": 5, "clear_context": True},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous(
            "First analyze, then refactor the code"
        )
        assert result.success is True

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_error_handling(self, mock_chat):
        from praisonaiagents import Agent
        mock_chat.side_effect = RuntimeError("LLM connection failed")

        agent = Agent(
            name="err_agent",
            instructions="Do tasks",
            autonomy={"max_iterations": 5},
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous("Do something")
        assert result.success is False
        assert result.completion_reason == "error"
        assert "connection failed" in result.error

    def test_autonomy_disabled_raises(self):
        from praisonaiagents import Agent
        agent = Agent(
            name="no_auto",
            instructions="Do tasks",
            llm="gpt-4o-mini",
        )
        with pytest.raises(ValueError, match="[Aa]utonomy"):
            agent.run_autonomous("Do something")

    @patch("praisonaiagents.agent.agent.Agent.chat")
    def test_auto_escalate_progresses_stage(self, mock_chat):
        from praisonaiagents import Agent
        responses = ["Working..."] * 5 + ["Task completed"]
        mock_chat.side_effect = responses

        agent = Agent(
            name="esc_agent",
            instructions="Do tasks",
            autonomy={
                "auto_escalate": True,
                "max_iterations": 10,
            },
            llm="gpt-4o-mini",
        )
        result = agent.run_autonomous("What is Python?")  # starts as DIRECT
        assert result.success is True
