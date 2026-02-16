"""
TDD Tests for Autonomy Gap Fixes.

Tests all gaps identified in the deep analysis:
- G-COMPLETION-1: Word-boundary completion detection
- G-RECOVERY-2: Graduated recovery actions in doom loop path
- G-ASYNC-1: Async run_autonomous_async() tests
- G-DUP-2: DoomLoopTracker delegates to DoomLoopDetector
- G-EXPORT-1: Escalation types exported from __init__
- G-DEAD-1: AutonomySignal deprecation warning
- G-CANCEL-1: Cancellation support
- G-ESCALATION-BEHAVIOR: De-escalation support
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock


# ============================================================
# G-COMPLETION-1: Word-boundary completion detection
# ============================================================

class TestCompletionDetection:
    """Tests that completion detection uses word boundaries, not substrings."""

    def _make_agent(self):
        """Create a minimal autonomy-enabled agent."""
        from praisonaiagents import Agent
        return Agent(
            instructions="Test agent",
            autonomy={"max_iterations": 5, "auto_escalate": False},
        )

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_done_as_word_triggers_completion(self, mock_stage, mock_chat):
        """'done' as a standalone word should trigger completion."""
        mock_chat.return_value = "The task is done."
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        assert result.completion_reason == "goal"

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_not_done_yet_does_not_trigger(self, mock_stage, mock_chat):
        """'not done yet' should NOT trigger completion — negation."""
        # First call: 'not done yet', second call: 'all done' (to avoid infinite loop)
        mock_chat.side_effect = ["I'm not done yet, still working", "All done now."]
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        # Should take 2 iterations, not 1
        assert result.iterations >= 2

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_abandoned_does_not_trigger_done(self, mock_stage, mock_chat):
        """'abandoned' contains 'done' as substring but should NOT trigger."""
        mock_chat.side_effect = ["I abandoned the old approach", "Task completed."]
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        assert result.iterations >= 2

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_condoned_does_not_trigger_done(self, mock_stage, mock_chat):
        """'condoned' contains 'done' as substring but should NOT trigger."""
        mock_chat.side_effect = ["The action was condoned by the team", "Task completed."]
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        assert result.iterations >= 2

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_task_completed_triggers(self, mock_stage, mock_chat):
        """'task completed' should trigger completion."""
        mock_chat.return_value = "I have task completed the work successfully."
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        assert result.completion_reason == "goal"

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_finished_as_word_triggers(self, mock_stage, mock_chat):
        """'finished' as standalone word should trigger."""
        mock_chat.return_value = "I have finished the refactoring."
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        assert result.completion_reason == "goal"

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_unfinished_does_not_trigger(self, mock_stage, mock_chat):
        """'unfinished' contains 'finished' but should NOT trigger."""
        mock_chat.side_effect = ["The work is unfinished", "All done."]
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        assert result.iterations >= 2

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_all_done_triggers(self, mock_stage, mock_chat):
        """'all done' should trigger completion."""
        mock_chat.return_value = "All done with the task."
        agent = self._make_agent()
        result = agent.run_autonomous("Do something")
        assert result.success is True
        assert result.completion_reason == "goal"


# ============================================================
# G-RECOVERY-2: Graduated recovery in doom loop path
# ============================================================

class TestDoomLoopRecovery:
    """Tests that doom loop detection uses graduated recovery."""

    def _make_agent(self, threshold=2):
        from praisonaiagents import Agent
        return Agent(
            instructions="Test agent",
            autonomy={
                "max_iterations": 20,
                "doom_loop_threshold": threshold,
                "auto_escalate": False,
            },
        )

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_doom_loop_retry_different_continues(self, mock_stage, mock_chat):
        """First doom loop detection should retry with different approach, not abort."""
        call_count = [0]
        def side_effect(prompt):
            call_count[0] += 1
            if call_count[0] <= 4:
                return "Working on iteration processing"
            return "Task completed."
        mock_chat.side_effect = side_effect
        agent = self._make_agent(threshold=2)
        result = agent.run_autonomous("Do something")
        # Should NOT immediately abort at first doom loop; recovery retries
        assert result.success is True or result.iterations > 2

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_doom_loop_eventually_aborts(self, mock_stage, mock_chat):
        """After exhausting recovery attempts, should abort."""
        mock_chat.return_value = "Still processing the same thing"
        agent = self._make_agent(threshold=2)
        result = agent.run_autonomous("Do something")
        assert result.success is False
        assert result.completion_reason == "doom_loop"

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_doom_loop_recovery_emits_observability(self, mock_stage, mock_chat):
        """Recovery actions should emit observability events when observe=True."""
        from praisonaiagents import Agent
        mock_chat.return_value = "Still processing the same thing"
        agent = Agent(
            instructions="Test agent",
            autonomy={
                "max_iterations": 20,
                "doom_loop_threshold": 2,
                "auto_escalate": False,
                "observe": True,
            },
        )
        result = agent.run_autonomous("Do something")
        obs = getattr(agent, '_observability_hooks', None)
        assert obs is not None
        events = obs.get_events()
        # Should have doom loop recovery events
        doom_events = [e for e in events if "doom" in str(e.data).lower() or "recovery" in str(e.data).lower()]
        assert len(doom_events) >= 1


# ============================================================
# G-ASYNC-1: Async run_autonomous_async() tests
# ============================================================

class TestRunAutonomousAsync:
    """Tests for the async variant of run_autonomous()."""

    def _make_agent(self, **autonomy_overrides):
        from praisonaiagents import Agent
        config = {"max_iterations": 5, "auto_escalate": False}
        config.update(autonomy_overrides)
        return Agent(instructions="Test agent", autonomy=config)

    @pytest.mark.asyncio
    async def test_async_basic_completion(self):
        """Async variant should complete on keyword signal."""
        agent = self._make_agent()
        with patch.object(agent, 'achat', new_callable=AsyncMock, return_value="Task completed."):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something")
        assert result.success is True
        assert result.completion_reason == "goal"

    @pytest.mark.asyncio
    async def test_async_promise_completion(self):
        """Async variant should detect promise tags."""
        agent = self._make_agent()
        with patch.object(agent, 'achat', new_callable=AsyncMock, return_value="Here: <promise>DONE</promise>"):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something", completion_promise="DONE")
        assert result.success is True
        assert result.completion_reason == "promise"

    @pytest.mark.asyncio
    async def test_async_timeout(self):
        """Async variant should respect timeout."""
        agent = self._make_agent()
        async def slow_chat(prompt):
            await asyncio.sleep(0.2)
            return "Still processing..."
        with patch.object(agent, 'achat', side_effect=slow_chat):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something", timeout_seconds=0.05)
        assert result.success is False
        assert result.completion_reason == "timeout"

    @pytest.mark.asyncio
    async def test_async_max_iterations(self):
        """Async variant should respect max iterations."""
        agent = self._make_agent(max_iterations=3)
        with patch.object(agent, 'achat', new_callable=AsyncMock, return_value="Still working on it..."):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something")
        assert result.success is False
        assert result.completion_reason == "max_iterations"
        assert result.iterations == 3

    @pytest.mark.asyncio
    async def test_async_doom_loop(self):
        """Async variant should detect doom loops and eventually stop."""
        agent = self._make_agent(doom_loop_threshold=2, max_iterations=30)
        with patch.object(agent, 'achat', new_callable=AsyncMock, return_value="Same response..."):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something")
        assert result.success is False
        # With graduated recovery: retry_different → escalate_model → request_help → abort
        assert result.completion_reason in ("doom_loop", "needs_help")

    @pytest.mark.asyncio
    async def test_async_error_handling(self):
        """Async variant should handle exceptions from achat."""
        agent = self._make_agent()
        with patch.object(agent, 'achat', new_callable=AsyncMock, side_effect=RuntimeError("LLM error")):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something")
        assert result.success is False
        assert result.completion_reason == "error"
        assert "LLM error" in result.error

    @pytest.mark.asyncio
    async def test_async_observability_events(self):
        """Async variant should emit observability events when observe=True."""
        agent = self._make_agent(observe=True)
        with patch.object(agent, 'achat', new_callable=AsyncMock, return_value="Task completed."):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something")
        obs = getattr(agent, '_observability_hooks', None)
        assert obs is not None
        events = obs.get_events()
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_async_clear_context(self):
        """Async variant should clear history when clear_context=True."""
        agent = self._make_agent()
        call_count = [0]
        async def chat_fn(prompt):
            call_count[0] += 1
            if call_count[0] >= 2:
                return "Task completed."
            return "Still working..."
        with patch.object(agent, 'achat', side_effect=chat_fn):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                with patch.object(agent, 'clear_history') as mock_clear:
                    result = await agent.run_autonomous_async("Do something", clear_context=True)
        assert result.success is True
        # clear_history should have been called at least once
        assert mock_clear.call_count >= 1

    @pytest.mark.asyncio
    async def test_async_not_enabled_raises(self):
        """Async variant should raise ValueError when autonomy is disabled."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test")
        with pytest.raises(ValueError, match="Autonomy must be enabled"):
            await agent.run_autonomous_async("Do something")

    @pytest.mark.asyncio
    async def test_async_word_boundary_completion(self):
        """Async variant should also use word-boundary completion detection."""
        agent = self._make_agent()
        with patch.object(agent, 'achat', new_callable=AsyncMock, side_effect=["I abandoned the old approach", "All done."]):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something")
        assert result.success is True
        assert result.iterations >= 2


# ============================================================
# G-DUP-2: DoomLoopTracker delegates to DoomLoopDetector
# ============================================================

class TestDoomLoopTrackerDelegation:
    """Tests that DoomLoopTracker delegates to DoomLoopDetector."""

    def test_tracker_has_delegate(self):
        """DoomLoopTracker should have a _delegate attribute (DoomLoopDetector)."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        assert hasattr(tracker, '_delegate')
        from praisonaiagents.escalation.doom_loop import DoomLoopDetector
        assert isinstance(tracker._delegate, DoomLoopDetector)

    def test_tracker_record_delegates(self):
        """record() should delegate to DoomLoopDetector.record_action()."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        with patch.object(tracker._delegate, 'record_action') as mock_record:
            tracker.record("read_file", {"path": "foo.py"}, "content", True)
        mock_record.assert_called_once()

    def test_tracker_is_doom_loop_delegates(self):
        """is_doom_loop() should delegate to DoomLoopDetector.is_doom_loop()."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        with patch.object(tracker._delegate, 'is_doom_loop', return_value=True) as mock_check:
            result = tracker.is_doom_loop()
        assert result is True
        mock_check.assert_called_once()

    def test_tracker_recovery_returns_graduated(self):
        """get_recovery_action() should return graduated recovery strings."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=2)
        # Feed enough identical actions to trigger doom loop
        tracker.record("chat", {"prompt": "test"}, "same", True)
        tracker.record("chat", {"prompt": "test"}, "same", True)
        assert tracker.is_doom_loop() is True
        # First recovery: retry_different
        assert tracker.get_recovery_action() == "retry_different"
        # Second recovery: escalate_model
        assert tracker.get_recovery_action() == "escalate_model"
        # Third recovery: request_help
        assert tracker.get_recovery_action() == "request_help"
        # Fourth: abort
        assert tracker.get_recovery_action() == "abort"

    def test_tracker_reset_delegates(self):
        """reset() should call DoomLoopDetector.start_session()."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        with patch.object(tracker._delegate, 'start_session') as mock_start:
            tracker.reset()
        mock_start.assert_called_once()

    def test_tracker_progress_marks(self):
        """DoomLoopTracker should expose mark_progress."""
        from praisonaiagents.agent.autonomy import DoomLoopTracker
        tracker = DoomLoopTracker(threshold=3)
        tracker.mark_progress("step_done")
        # Should not raise


# ============================================================
# G-EXPORT-1: Escalation types exported from __init__
# ============================================================

class TestEscalationExports:
    """Tests that key escalation types are importable from top-level package."""

    def test_escalation_stage_importable(self):
        from praisonaiagents import EscalationStage
        assert EscalationStage.DIRECT.value == 0
        assert EscalationStage.AUTONOMOUS.value == 3

    def test_escalation_pipeline_importable(self):
        from praisonaiagents import EscalationPipeline
        assert EscalationPipeline is not None

    def test_observability_hooks_importable(self):
        from praisonaiagents import ObservabilityHooks
        assert ObservabilityHooks is not None

    def test_observability_event_type_importable(self):
        from praisonaiagents import ObservabilityEventType
        assert hasattr(ObservabilityEventType, 'STEP_END')

    def test_doom_loop_detector_importable(self):
        from praisonaiagents import DoomLoopDetector
        assert DoomLoopDetector is not None


# ============================================================
# G-DEAD-1: AutonomySignal deprecation
# ============================================================

class TestAutonomySignalDeprecation:
    """Tests that AutonomySignal still works (backward compat) and has deprecation docstring."""

    def test_autonomy_signal_still_works(self):
        """AutonomySignal should still be importable and functional."""
        from praisonaiagents.agent.autonomy import AutonomySignal
        assert AutonomySignal.EDIT_INTENT.value == "edit_intent"
        assert AutonomySignal.SIMPLE_QUESTION.value == "simple_question"

    def test_autonomy_signal_has_deprecation_docstring(self):
        """AutonomySignal docstring should mention deprecation."""
        from praisonaiagents.agent.autonomy import AutonomySignal
        assert "deprecated" in AutonomySignal.__doc__.lower()


# ============================================================
# G-CANCEL-1: Cancellation support
# ============================================================

class TestCancellationSupport:
    """Tests for cancellation support in autonomous loop."""

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
    def test_keyboard_interrupt_returns_cancelled(self, mock_stage, mock_chat):
        """KeyboardInterrupt during chat should return cancelled result."""
        mock_chat.side_effect = [
            "Working...",
            KeyboardInterrupt("User cancelled"),
        ]
        from praisonaiagents import Agent
        agent = Agent(instructions="Test", autonomy={"max_iterations": 5, "auto_escalate": False})
        result = agent.run_autonomous("Do something")
        assert result.success is False
        assert result.completion_reason == "cancelled"

    @pytest.mark.asyncio
    async def test_async_cancelled_error_returns_cancelled(self):
        """asyncio.CancelledError during achat should return cancelled result."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test", autonomy={"max_iterations": 5, "auto_escalate": False})
        call_count = [0]
        async def chat_fn(prompt):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise asyncio.CancelledError()
            return "Working..."
        with patch.object(agent, 'achat', side_effect=chat_fn):
            with patch.object(agent, 'get_recommended_stage', return_value="heuristic"):
                result = await agent.run_autonomous_async("Do something")
        assert result.success is False
        assert result.completion_reason == "cancelled"


# ============================================================
# G-ESCALATION-BEHAVIOR: De-escalation support
# ============================================================

class TestDeescalation:
    """Tests for de-escalation when task becomes simpler."""

    @patch("praisonaiagents.agent.agent.Agent.chat")
    @patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="planned")
    def test_deescalation_on_consecutive_success(self, mock_stage, mock_chat):
        """Stage should de-escalate after consecutive successes if enabled."""
        call_count = [0]
        def side_effect(prompt):
            call_count[0] += 1
            if call_count[0] >= 4:
                return "Task completed."
            return "Processing step by step..."
        mock_chat.side_effect = side_effect
        from praisonaiagents import Agent
        agent = Agent(
            instructions="Test",
            autonomy={"max_iterations": 10, "auto_escalate": True},
        )
        result = agent.run_autonomous("Do something")
        # Should complete (we mainly test that de-escalation doesn't break anything)
        assert result.success is True


# ============================================================
# CLI Parity: Loop command flags
# ============================================================

class TestCLILoopParity:
    """Tests that CLI loop command has parity with SDK features."""

    def test_loop_command_has_observe_flag(self):
        """loop command should accept --observe flag."""
        from praisonai.cli.commands.loop import loop_main
        import inspect
        sig = inspect.signature(loop_main)
        assert "observe" in sig.parameters

    def test_loop_command_has_recovery_flag(self):
        """loop command should accept --recovery flag."""
        from praisonai.cli.commands.loop import loop_main
        import inspect
        sig = inspect.signature(loop_main)
        assert "recovery" in sig.parameters

    def test_loop_command_has_level_flag(self):
        """loop command should accept --level flag for autonomy level."""
        from praisonai.cli.commands.loop import loop_main
        import inspect
        sig = inspect.signature(loop_main)
        assert "level" in sig.parameters


# ============================================================
# CLI Bridge: Per-agent approval (not global env var)
# ============================================================

class TestCLIBridgeApproval:
    """Tests that CLI bridge no longer uses global env var."""

    def test_autonomy_manager_get_config_full_auto(self):
        """get_autonomy_config() should return per-agent config with full_auto level."""
        from praisonai.cli.features.autonomy_mode import AutonomyManager, AutonomyMode
        mgr = AutonomyManager(mode=AutonomyMode.FULL_AUTO)
        config = mgr.get_autonomy_config()
        assert config["level"] == "full_auto"
        assert config["enabled"] is True

    def test_autonomy_manager_bridges_via_config(self):
        """AutonomyManager should provide autonomy_config for Agent constructor."""
        from praisonai.cli.features.autonomy_mode import AutonomyManager, AutonomyMode
        mgr = AutonomyManager(mode=AutonomyMode.FULL_AUTO)
        config = mgr.get_autonomy_config()
        assert config["level"] == "full_auto"
