"""
Tests for HandoffResult integration with AgentRunOutcome.

Verifies that the HandoffResult class correctly integrates the new typed
outcome system while maintaining backward compatibility.
"""

import pytest
from praisonaiagents.agent.handoff import HandoffResult
from praisonaiagents.run_outcome import AgentRunOutcome


class TestHandoffResultBackwardCompatibility:
    """Test backward compatibility of HandoffResult."""
    
    def test_legacy_success_result(self):
        """Test that legacy success results work correctly."""
        result = HandoffResult(
            success=True,
            response="Task completed successfully",
            target_agent="target",
            source_agent="source",
            duration_seconds=1.5
        )
        
        # Legacy fields should work
        assert result.success is True
        assert result.response == "Task completed successfully"
        assert result.target_agent == "target"
        assert result.source_agent == "source"
        assert result.duration_seconds == 1.5
        
        # New outcome should be auto-generated
        assert result.outcome is not None
        assert result.outcome.status == "success"
        assert result.outcome.output == "Task completed successfully"
        assert result.outcome.elapsed_s == 1.5
        assert result.outcome.agent_name == "target"
        assert result.outcome.is_success()
    
    def test_legacy_failure_result(self):
        """Test that legacy failure results work correctly."""
        result = HandoffResult(
            success=False,
            error="Handoff failed due to timeout",
            target_agent="target",
            duration_seconds=30.0
        )
        
        # Legacy fields should work
        assert result.success is False
        assert result.error == "Handoff failed due to timeout"
        
        # New outcome should be auto-generated with timeout status
        assert result.outcome is not None
        assert result.outcome.status == "timeout"  # Should detect timeout from error message
        assert result.outcome.error == "Handoff failed due to timeout"
        assert result.outcome.elapsed_s == 30.0
        assert not result.outcome.is_success()
        assert result.outcome.is_retryable()  # Timeouts are retryable
    
    def test_legacy_cycle_error(self):
        """Test that cycle errors are detected correctly."""
        result = HandoffResult(
            success=False,
            error="Circular handoff dependency detected",
            target_agent="target"
        )
        
        assert result.outcome.status == "failure"  # Cycle errors are not retryable
        assert not result.outcome.is_retryable()
    
    def test_legacy_depth_error(self):
        """Test that depth errors are detected correctly."""
        result = HandoffResult(
            success=False,
            error="Maximum handoff depth exceeded",
            target_agent="target"
        )
        
        assert result.outcome.status == "failure"  # Depth errors are not retryable
        assert not result.outcome.is_retryable()


class TestHandoffResultFromOutcome:
    """Test creating HandoffResult from AgentRunOutcome."""
    
    def test_from_success_outcome(self):
        """Test creating HandoffResult from success outcome."""
        outcome = AgentRunOutcome.success(
            output="Task completed",
            elapsed_s=2.0,
            agent_name="test_agent",
            run_id="test_run"
        )
        
        result = HandoffResult.from_outcome(
            outcome=outcome,
            target_agent="target",
            source_agent="source"
        )
        
        assert result.success is True
        assert result.response == "Task completed"
        assert result.target_agent == "target"
        assert result.source_agent == "source"
        assert result.duration_seconds == 2.0
        assert result.error is None
        assert result.outcome is outcome
    
    def test_from_timeout_outcome(self):
        """Test creating HandoffResult from timeout outcome."""
        outcome = AgentRunOutcome.timeout(
            error="Agent timed out after 30s",
            elapsed_s=30.0,
            agent_name="timeout_agent"
        )
        
        result = HandoffResult.from_outcome(
            outcome=outcome,
            target_agent="target"
        )
        
        assert result.success is False
        assert result.response is None  # No successful output
        assert result.target_agent == "target"
        assert result.duration_seconds == 30.0
        assert result.error == "Agent timed out after 30s"
        assert result.outcome is outcome
        assert result.outcome.is_retryable()
    
    def test_from_invalid_output_outcome(self):
        """Test creating HandoffResult from invalid output outcome."""
        outcome = AgentRunOutcome.invalid_output(
            error="Output validation failed",
            elapsed_s=1.0
        )
        
        result = HandoffResult.from_outcome(outcome=outcome)
        
        assert result.success is False
        assert result.error == "Output validation failed"
        assert result.outcome.status == "invalid_output"
        assert result.outcome.is_retryable()
    
    def test_from_cancelled_outcome(self):
        """Test creating HandoffResult from cancelled outcome."""
        outcome = AgentRunOutcome.cancelled(
            error="Operation was cancelled by user",
            elapsed_s=5.0
        )
        
        result = HandoffResult.from_outcome(outcome=outcome)
        
        assert result.success is False
        assert result.error == "Operation was cancelled by user"
        assert result.outcome.status == "cancelled"
        assert not result.outcome.is_retryable()


class TestExhaustiveHandoffHandling:
    """Test exhaustive handling of all handoff outcome types."""
    
    def test_exhaustive_outcome_handling(self):
        """Test that all outcome statuses can be handled in handoff context."""
        outcomes = [
            AgentRunOutcome.success("Success"),
            AgentRunOutcome.failure("General failure"),
            AgentRunOutcome.timeout("Timeout occurred"),
            AgentRunOutcome.cancelled("Cancelled by user"),
            AgentRunOutcome.invalid_output("Invalid output format"),
        ]
        
        for outcome in outcomes:
            result = HandoffResult.from_outcome(outcome)
            
            # Simulate exhaustive pattern matching for handoff decisions
            if result.outcome.status == "success":
                # Continue with the handoff result
                assert result.success is True
            elif result.outcome.status == "timeout":
                # Retry with longer timeout or escalate
                assert result.outcome.is_retryable()
            elif result.outcome.status == "invalid_output":
                # Retry with different validation or escalate
                assert result.outcome.is_retryable()
            elif result.outcome.status in ("failure", "cancelled"):
                # Log and return error to orchestrator
                assert not result.outcome.is_retryable()
            else:
                # This should never happen if we handle all cases
                pytest.fail(f"Unhandled outcome status: {result.outcome.status}")


class TestOutcomeContextData:
    """Test that context data is properly preserved in handoff outcomes."""
    
    def test_context_preservation(self):
        """Test that handoff context is preserved in outcomes."""
        result = HandoffResult(
            success=True,
            response="Done",
            target_agent="target",
            source_agent="source",
            handoff_depth=2
        )
        
        context = result.outcome.context
        assert context is not None
        assert context["source_agent"] == "source"
        assert context["handoff_depth"] == 2
    
    def test_outcome_with_custom_context(self):
        """Test creating outcome with custom context data."""
        custom_context = {
            "retry_count": 3,
            "validation_details": "Output format incorrect"
        }
        
        outcome = AgentRunOutcome.invalid_output(
            error="Validation failed",
            context=custom_context
        )
        
        result = HandoffResult.from_outcome(
            outcome=outcome,
            handoff_depth=1
        )
        
        # Original context should be preserved
        assert result.outcome.context["retry_count"] == 3
        assert result.outcome.context["validation_details"] == "Output format incorrect"


if __name__ == "__main__":
    pytest.main([__file__])