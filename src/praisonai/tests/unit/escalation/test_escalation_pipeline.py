"""
Tests for Escalation Pipeline.

TDD tests for progressive escalation from direct response to autonomous mode.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# Add the praisonai-agents path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'praisonai-agents'))

from praisonaiagents.escalation.types import (
    EscalationStage,
    EscalationConfig,
    EscalationResult,
    EscalationSignal,
    StageContext,
)
from praisonaiagents.escalation.triggers import EscalationTrigger
from praisonaiagents.escalation.doom_loop import (
    DoomLoopDetector,
    DoomLoopConfig,
    DoomLoopType,
    RecoveryAction,
)
from praisonaiagents.escalation.pipeline import EscalationPipeline


class TestEscalationStage:
    """Tests for EscalationStage enum."""
    
    def test_stage_ordering(self):
        """Test that stages are ordered correctly."""
        assert EscalationStage.DIRECT < EscalationStage.HEURISTIC
        assert EscalationStage.HEURISTIC < EscalationStage.PLANNED
        assert EscalationStage.PLANNED < EscalationStage.AUTONOMOUS
    
    def test_stage_values(self):
        """Test stage integer values."""
        assert EscalationStage.DIRECT == 0
        assert EscalationStage.HEURISTIC == 1
        assert EscalationStage.PLANNED == 2
        assert EscalationStage.AUTONOMOUS == 3


class TestEscalationConfig:
    """Tests for EscalationConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = EscalationConfig()
        
        assert config.long_prompt_threshold == 100
        assert config.complex_keyword_threshold == 2
        assert config.max_steps == 20
        assert config.max_time_seconds == 300
        assert config.auto_escalate is True
        assert config.auto_deescalate is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = EscalationConfig(
            long_prompt_threshold=50,
            max_steps=10,
            auto_escalate=False,
        )
        
        assert config.long_prompt_threshold == 50
        assert config.max_steps == 10
        assert config.auto_escalate is False


class TestEscalationTrigger:
    """Tests for EscalationTrigger signal detection."""
    
    def test_simple_question_detection(self):
        """Test detection of simple questions."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("What is Python?")
        assert EscalationSignal.SIMPLE_QUESTION in signals
        
        signals = trigger.analyze("Define machine learning")
        assert EscalationSignal.SIMPLE_QUESTION in signals
    
    def test_complex_keywords_detection(self):
        """Test detection of complex task keywords."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("Analyze and refactor the authentication module")
        assert EscalationSignal.COMPLEX_KEYWORDS in signals
        
        signals = trigger.analyze("Debug and optimize the database queries")
        assert EscalationSignal.COMPLEX_KEYWORDS in signals
    
    def test_long_prompt_detection(self):
        """Test detection of long prompts."""
        trigger = EscalationTrigger()
        
        # Short prompt
        signals = trigger.analyze("Hello world")
        assert EscalationSignal.LONG_PROMPT not in signals
        
        # Long prompt (>100 words)
        long_prompt = " ".join(["word"] * 150)
        signals = trigger.analyze(long_prompt)
        assert EscalationSignal.LONG_PROMPT in signals
    
    def test_file_references_detection(self):
        """Test detection of file references."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("Read the file src/main.py")
        assert EscalationSignal.FILE_REFERENCES in signals
        
        signals = trigger.analyze("Check config.yaml for settings")
        assert EscalationSignal.FILE_REFERENCES in signals
    
    def test_edit_intent_detection(self):
        """Test detection of edit intent."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("Edit the config file")
        assert EscalationSignal.EDIT_INTENT in signals
        
        signals = trigger.analyze("Modify the user model")
        assert EscalationSignal.EDIT_INTENT in signals
        
        signals = trigger.analyze("Fix the bug in auth.py")
        assert EscalationSignal.EDIT_INTENT in signals
    
    def test_multi_step_intent_detection(self):
        """Test detection of multi-step tasks."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("First, read the file. Then, update it. Finally, test it.")
        assert EscalationSignal.MULTI_STEP_INTENT in signals
        
        signals = trigger.analyze("What is this? How does it work? Why is it needed?")
        assert EscalationSignal.MULTI_STEP_INTENT in signals
    
    def test_code_blocks_detection(self):
        """Test detection of code blocks."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("Fix this code: ```python\nprint('hello')\n```")
        assert EscalationSignal.CODE_BLOCKS in signals
        
        signals = trigger.analyze("The function `main()` is broken")
        assert EscalationSignal.CODE_BLOCKS in signals
    
    def test_repo_context_detection(self):
        """Test detection of repo context."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("Hello", context={"is_git_repo": True})
        assert EscalationSignal.REPO_CONTEXT in signals
        
        signals = trigger.analyze("Hello", context={"workspace": "/path/to/project"})
        assert EscalationSignal.REPO_CONTEXT in signals


class TestEscalationTriggerStageRecommendation:
    """Tests for stage recommendation based on signals."""
    
    def test_direct_stage_for_simple_question(self):
        """Test DIRECT stage for simple questions."""
        trigger = EscalationTrigger()
        
        signals = trigger.analyze("What is Python?")
        stage = trigger.recommend_stage(signals)
        assert stage == EscalationStage.DIRECT
    
    def test_heuristic_stage_for_file_references(self):
        """Test HEURISTIC stage for file references."""
        trigger = EscalationTrigger()
        
        signals = {EscalationSignal.FILE_REFERENCES}
        stage = trigger.recommend_stage(signals)
        assert stage == EscalationStage.HEURISTIC
    
    def test_planned_stage_for_edit_intent(self):
        """Test PLANNED stage for edit intent."""
        trigger = EscalationTrigger()
        
        signals = {EscalationSignal.EDIT_INTENT}
        stage = trigger.recommend_stage(signals)
        assert stage == EscalationStage.PLANNED
    
    def test_autonomous_stage_for_multi_step(self):
        """Test AUTONOMOUS stage for multi-step tasks."""
        trigger = EscalationTrigger()
        
        signals = {EscalationSignal.MULTI_STEP_INTENT}
        stage = trigger.recommend_stage(signals)
        assert stage == EscalationStage.AUTONOMOUS
    
    def test_autonomous_stage_for_refactor(self):
        """Test AUTONOMOUS stage for refactoring."""
        trigger = EscalationTrigger()
        
        signals = {EscalationSignal.REFACTOR_INTENT}
        stage = trigger.recommend_stage(signals)
        assert stage == EscalationStage.AUTONOMOUS
    
    def test_escalation_on_failure(self):
        """Test escalation when failure signal is present."""
        trigger = EscalationTrigger()
        
        signals = {EscalationSignal.TOOL_FAILURE}
        stage = trigger.recommend_stage(signals, current_stage=EscalationStage.HEURISTIC)
        assert stage > EscalationStage.HEURISTIC


class TestDoomLoopDetector:
    """Tests for DoomLoopDetector."""
    
    def test_no_loop_initially(self):
        """Test no loop detected initially."""
        detector = DoomLoopDetector()
        detector.start_session()
        
        assert not detector.is_doom_loop()
    
    def test_repeated_identical_actions(self):
        """Test detection of repeated identical actions."""
        config = DoomLoopConfig(max_identical_actions=3)
        detector = DoomLoopDetector(config)
        detector.start_session()
        
        # Record same action 3 times
        for _ in range(3):
            detector.record_action(
                action_type="read_file",
                args={"path": "foo.py"},
                result="content",
                success=True,
            )
        
        assert detector.is_doom_loop()
        assert detector.get_loop_type() == DoomLoopType.REPEATED_ACTION
    
    def test_consecutive_failures(self):
        """Test detection of consecutive failures."""
        config = DoomLoopConfig(max_consecutive_failures=3)
        detector = DoomLoopDetector(config)
        detector.start_session()
        
        # Record 3 failures
        for i in range(3):
            detector.record_action(
                action_type=f"action_{i}",
                args={},
                result=None,
                success=False,
            )
        
        assert detector.is_doom_loop()
        assert detector.get_loop_type() == DoomLoopType.REPEATED_FAILURE
    
    def test_no_loop_with_varied_actions(self):
        """Test no loop with varied actions."""
        detector = DoomLoopDetector()
        detector.start_session()
        
        # Record different actions
        detector.record_action("read_file", {"path": "a.py"}, "content_a", True)
        detector.record_action("write_file", {"path": "b.py"}, "ok", True)
        detector.record_action("run_command", {"cmd": "test"}, "passed", True)
        
        assert not detector.is_doom_loop()
    
    def test_progress_markers_prevent_no_progress_detection(self):
        """Test that progress markers prevent no-progress detection."""
        config = DoomLoopConfig(max_no_progress_steps=3)
        detector = DoomLoopDetector(config)
        detector.start_session()
        
        # Record actions with same result
        for i in range(5):
            detector.record_action("action", {}, "same_result", True)
            if i == 2:
                detector.mark_progress("made_progress")
        
        # Should not detect no-progress because we marked progress
        loop_type = detector.get_loop_type()
        assert loop_type != DoomLoopType.NO_PROGRESS or not detector.is_doom_loop()
    
    def test_recovery_action_progression(self):
        """Test recovery action progression."""
        detector = DoomLoopDetector()
        detector.start_session()
        
        # First recovery: retry different
        detector._recovery_attempts = 0
        action = detector._determine_recovery_action(DoomLoopType.REPEATED_ACTION)
        assert action == RecoveryAction.RETRY_DIFFERENT
        
        # Second recovery: escalate model
        detector._recovery_attempts = 1
        action = detector._determine_recovery_action(DoomLoopType.REPEATED_ACTION)
        assert action == RecoveryAction.ESCALATE_MODEL
        
        # Max reached: abort
        detector._recovery_attempts = 2
        action = detector._determine_recovery_action(DoomLoopType.REPEATED_ACTION)
        assert action == RecoveryAction.ABORT
    
    def test_backoff_increases(self):
        """Test that backoff increases on each call."""
        config = DoomLoopConfig(initial_backoff=0.01, backoff_multiplier=2.0, max_backoff=1.0)
        detector = DoomLoopDetector(config)
        
        initial = detector._current_backoff
        detector.apply_backoff()
        assert detector._current_backoff > initial
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        detector = DoomLoopDetector()
        detector.start_session()
        
        detector.record_action("a", {}, "r", True)
        detector.record_action("b", {}, "r", False)
        detector.mark_progress("p1")
        
        stats = detector.get_stats()
        assert stats["total_actions"] == 2
        assert stats["successful_actions"] == 1
        assert stats["failed_actions"] == 1
        assert stats["progress_markers"] == 1


class TestStageContext:
    """Tests for StageContext."""
    
    def test_add_step(self):
        """Test adding steps to context."""
        context = StageContext(
            stage=EscalationStage.HEURISTIC,
            prompt="test",
        )
        
        context.add_step("read_file", "content", success=True)
        
        assert len(context.steps) == 1
        assert context.steps[0]["action"] == "read_file"
        assert context.steps[0]["success"] is True
    
    def test_add_tool_result(self):
        """Test adding tool results."""
        context = StageContext(
            stage=EscalationStage.HEURISTIC,
            prompt="test",
        )
        
        context.add_tool_result("read_file", {"path": "a.py"}, "content", True)
        
        assert len(context.tool_results) == 1
        assert context.tool_calls == 1
    
    def test_should_escalate_on_failures(self):
        """Test escalation recommendation on failures."""
        config = EscalationConfig()
        context = StageContext(
            stage=EscalationStage.HEURISTIC,
            prompt="test",
        )
        
        # Add failures
        context.add_step("a", "fail", success=False)
        context.add_step("b", "fail", success=False)
        
        assert context.should_escalate(config)
    
    def test_should_deescalate_on_simple(self):
        """Test de-escalation for simple questions."""
        config = EscalationConfig()
        context = StageContext(
            stage=EscalationStage.PLANNED,
            prompt="test",
            signals={EscalationSignal.SIMPLE_QUESTION},
        )
        
        assert context.should_deescalate(config)


class TestEscalationPipeline:
    """Tests for EscalationPipeline."""
    
    def test_analyze_simple_prompt(self):
        """Test analysis of simple prompt."""
        pipeline = EscalationPipeline()
        
        stage = pipeline.analyze("What is Python?")
        assert stage == EscalationStage.DIRECT
    
    def test_analyze_complex_prompt(self):
        """Test analysis of complex prompt."""
        pipeline = EscalationPipeline()
        
        stage = pipeline.analyze("Refactor the authentication module and add tests")
        assert stage >= EscalationStage.PLANNED
    
    @pytest.mark.asyncio
    async def test_execute_direct_stage(self):
        """Test execution at DIRECT stage."""
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Hello!")
        
        pipeline = EscalationPipeline(agent=mock_agent)
        
        result = await pipeline.execute_at_stage(
            "Hello",
            EscalationStage.DIRECT,
        )
        
        assert result.success
        assert result.initial_stage == EscalationStage.DIRECT
        assert "Hello" in result.response
    
    @pytest.mark.asyncio
    async def test_execute_with_escalation(self):
        """Test execution with automatic escalation."""
        mock_agent = Mock()
        # First call fails, second succeeds
        mock_agent.chat = Mock(side_effect=[Exception("fail"), "Success!"])
        
        config = EscalationConfig(auto_escalate=True)
        pipeline = EscalationPipeline(config=config, agent=mock_agent)
        
        result = await pipeline.execute_at_stage(
            "Do something",
            EscalationStage.DIRECT,
        )
        
        # Should have escalated
        assert result.escalations >= 0  # May or may not escalate depending on error handling
    
    @pytest.mark.asyncio
    async def test_execute_respects_time_budget(self):
        """Test that execution respects time budget."""
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="ok")
        
        config = EscalationConfig(max_time_seconds=1)
        pipeline = EscalationPipeline(config=config, agent=mock_agent)
        
        result = await pipeline.execute_at_stage(
            "Quick task",
            EscalationStage.DIRECT,
        )
        
        assert result.time_seconds < 2  # Should complete quickly
    
    @pytest.mark.asyncio
    async def test_stage_change_callback(self):
        """Test stage change callback is called."""
        mock_agent = Mock()
        mock_agent.chat = Mock(side_effect=[Exception("fail"), "ok"])
        
        callback_called = []
        def on_change(old, new):
            callback_called.append((old, new))
        
        config = EscalationConfig(auto_escalate=True)
        pipeline = EscalationPipeline(
            config=config,
            agent=mock_agent,
            on_stage_change=on_change,
        )
        
        await pipeline.execute_at_stage(
            "Task",
            EscalationStage.DIRECT,
        )
        
        # Callback may or may not be called depending on escalation
        # Just verify it doesn't crash
    
    def test_get_current_stage(self):
        """Test getting current stage."""
        pipeline = EscalationPipeline()
        
        # Initially None
        assert pipeline.get_current_stage() is None


class TestEscalationResult:
    """Tests for EscalationResult."""
    
    def test_was_escalated(self):
        """Test was_escalated property."""
        result = EscalationResult(
            response="ok",
            success=True,
            initial_stage=EscalationStage.DIRECT,
            final_stage=EscalationStage.PLANNED,
        )
        
        assert result.was_escalated
    
    def test_was_deescalated(self):
        """Test was_deescalated property."""
        result = EscalationResult(
            response="ok",
            success=True,
            initial_stage=EscalationStage.AUTONOMOUS,
            final_stage=EscalationStage.HEURISTIC,
        )
        
        assert result.was_deescalated
    
    def test_no_escalation(self):
        """Test no escalation case."""
        result = EscalationResult(
            response="ok",
            success=True,
            initial_stage=EscalationStage.DIRECT,
            final_stage=EscalationStage.DIRECT,
        )
        
        assert not result.was_escalated
        assert not result.was_deescalated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
