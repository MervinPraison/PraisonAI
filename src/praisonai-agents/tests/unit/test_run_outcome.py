"""
Tests for the AgentRunOutcome typed validation system.

Verifies that the new typed outcome system provides structured error handling
and backward compatibility with existing freeform string validation.
"""

import pytest
from praisonaiagents.run_outcome import AgentRunOutcome, RunStatus, validate_decision_string


class TestRunStatus:
    """Test the RunStatus type definition."""
    
    def test_valid_statuses(self):
        """Test that all expected status values are valid."""
        valid_statuses = ["success", "failure", "timeout", "cancelled", "invalid_output"]
        for status in valid_statuses:
            # Should not raise type error
            outcome = AgentRunOutcome(status=status)
            assert outcome.status == status


class TestAgentRunOutcome:
    """Test the AgentRunOutcome dataclass."""
    
    def test_basic_creation(self):
        """Test basic outcome creation."""
        outcome = AgentRunOutcome(status="success", output="Task completed")
        assert outcome.status == "success"
        assert outcome.output == "Task completed"
        assert outcome.error is None
    
    def test_success_helper(self):
        """Test the success class method."""
        outcome = AgentRunOutcome.success(
            output="Test output",
            elapsed_s=1.5,
            agent_name="test_agent"
        )
        assert outcome.status == "success"
        assert outcome.output == "Test output"
        assert outcome.elapsed_s == 1.5
        assert outcome.agent_name == "test_agent"
        assert outcome.is_success()
        assert not outcome.is_failure()
    
    def test_failure_helper(self):
        """Test the failure class method."""
        outcome = AgentRunOutcome.failure(
            error="Test error",
            error_category="validation"
        )
        assert outcome.status == "failure"
        assert outcome.error == "Test error"
        assert outcome.error_category == "validation"
        assert not outcome.is_success()
        assert outcome.is_failure()
        assert not outcome.is_retryable()
    
    def test_timeout_helper(self):
        """Test the timeout class method."""
        outcome = AgentRunOutcome.timeout(
            error="Operation timed out",
            elapsed_s=30.0
        )
        assert outcome.status == "timeout"
        assert outcome.error == "Operation timed out"
        assert outcome.error_category == "timeout"
        assert outcome.elapsed_s == 30.0
        assert outcome.is_retryable()
    
    def test_invalid_output_helper(self):
        """Test the invalid_output class method."""
        outcome = AgentRunOutcome.invalid_output(
            error="Invalid format"
        )
        assert outcome.status == "invalid_output"
        assert outcome.error == "Invalid format"
        assert outcome.error_category == "validation"
        assert outcome.is_retryable()
    
    def test_cancelled_helper(self):
        """Test the cancelled class method."""
        outcome = AgentRunOutcome.cancelled()
        assert outcome.status == "cancelled"
        assert outcome.error == "Operation was cancelled"
        assert outcome.error_category == "cancelled"
        assert not outcome.is_retryable()
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        outcome = AgentRunOutcome.success(
            output="test",
            elapsed_s=1.0,
            agent_name="test_agent",
            run_id="test_run"
        )
        result = outcome.to_dict()
        
        expected_keys = {
            "status", "output", "error", "error_category", 
            "elapsed_s", "agent_name", "run_id", "context"
        }
        assert set(result.keys()) == expected_keys
        assert result["status"] == "success"
        assert result["output"] == "test"
        assert result["agent_name"] == "test_agent"


class TestValidateDecisionString:
    """Test the legacy decision string validation."""
    
    def test_success_decisions(self):
        """Test that success strings map to success status."""
        success_strings = ["success", "successful", "valid", "approved", "accept", "complete"]
        for decision in success_strings:
            assert validate_decision_string(decision) == "success"
    
    def test_failure_decisions(self):
        """Test that legacy failure strings map to invalid_output status."""
        failure_strings = ["invalid", "retry", "failed", "error", "unsuccessful", "fail", "reject", "incomplete"]
        for decision in failure_strings:
            assert validate_decision_string(decision) == "invalid_output"
    
    def test_timeout_decisions(self):
        """Test that timeout strings map to timeout status."""
        timeout_strings = ["timeout", "timed out"]
        for decision in timeout_strings:
            assert validate_decision_string(decision) == "timeout"
    
    def test_cancelled_decisions(self):
        """Test that cancellation strings map to cancelled status."""
        cancelled_strings = ["cancelled", "canceled", "aborted"]
        for decision in cancelled_strings:
            assert validate_decision_string(decision) == "cancelled"
    
    def test_unknown_decisions(self):
        """Test that unknown strings map to general failure."""
        unknown_strings = ["unknown", "weird_status", ""]
        for decision in unknown_strings:
            assert validate_decision_string(decision) == "failure"
    
    def test_case_insensitive(self):
        """Test that decision string matching is case insensitive."""
        assert validate_decision_string("SUCCESS") == "success"
        assert validate_decision_string("Invalid") == "invalid_output"
        assert validate_decision_string("TIMEOUT") == "timeout"


class TestRetryableLogic:
    """Test the retry logic for different outcome types."""
    
    def test_retryable_outcomes(self):
        """Test which outcomes are considered retryable."""
        retryable_outcomes = [
            AgentRunOutcome(status="timeout"),
            AgentRunOutcome(status="invalid_output"),
        ]
        
        for outcome in retryable_outcomes:
            assert outcome.is_retryable(), f"{outcome.status} should be retryable"
    
    def test_non_retryable_outcomes(self):
        """Test which outcomes are not retryable."""
        non_retryable_outcomes = [
            AgentRunOutcome(status="success"),
            AgentRunOutcome(status="failure"),
            AgentRunOutcome(status="cancelled"),
        ]
        
        for outcome in non_retryable_outcomes:
            assert not outcome.is_retryable(), f"{outcome.status} should not be retryable"


class TestExhaustiveMatching:
    """Test that the outcome status enables exhaustive pattern matching."""
    
    def test_exhaustive_status_handling(self):
        """Test that all status values can be handled exhaustively."""
        test_outcomes = [
            AgentRunOutcome(status="success"),
            AgentRunOutcome(status="failure"),
            AgentRunOutcome(status="timeout"),
            AgentRunOutcome(status="cancelled"),
            AgentRunOutcome(status="invalid_output"),
        ]
        
        for outcome in test_outcomes:
            # Simulate exhaustive match (would be a match statement in Python 3.10+)
            handled = False
            
            if outcome.status == "success":
                handled = True
            elif outcome.status == "failure":
                handled = True
            elif outcome.status == "timeout":
                handled = True
            elif outcome.status == "cancelled":
                handled = True
            elif outcome.status == "invalid_output":
                handled = True
            
            assert handled, f"Status {outcome.status} was not handled"


if __name__ == "__main__":
    pytest.main([__file__])