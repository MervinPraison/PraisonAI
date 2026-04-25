"""
Test for task failure policies (Issue #1553 Gap 3)
"""
import pytest
import asyncio
from unittest.mock import AsyncMock
from praisonaiagents.task.task import Task
from praisonaiagents.main import TaskOutput


@pytest.mark.asyncio
async def test_task_failure_policies_configuration():
    """Test that failure policy parameters are properly configured"""
    # Test default values
    task_default = Task(description="Test task")
    assert hasattr(task_default, 'fail_on_callback_error')
    assert hasattr(task_default, 'fail_on_memory_error')
    assert task_default.fail_on_callback_error is False  # Safe default
    assert task_default.fail_on_memory_error is False   # Safe default
    
    # Test custom configuration
    task_custom = Task(
        description="Test task",
        fail_on_callback_error=True,
        fail_on_memory_error=True
    )
    assert task_custom.fail_on_callback_error is True
    assert task_custom.fail_on_memory_error is True


@pytest.mark.asyncio
async def test_non_fatal_errors_initialization():
    """Test that non_fatal_errors list is properly initialized"""
    task = Task(description="Test task")
    assert hasattr(task, 'non_fatal_errors')
    assert isinstance(task.non_fatal_errors, list)
    assert len(task.non_fatal_errors) == 0


@pytest.mark.asyncio
async def test_callback_failure_policy_enabled():
    """Test that callback errors are re-raised when fail_on_callback_error=True"""
    def failing_callback(task_output):
        raise RuntimeError("Test callback failure")
    
    task = Task(
        description="Test task",
        callback=failing_callback,
        fail_on_callback_error=True,
        quality_check=False
    )
    
    task_output = TaskOutput(description="Test", raw="test output", agent="test")
    
    # Should re-raise the exception when policy is enabled
    with pytest.raises(RuntimeError, match="Test callback failure"):
        await task.execute_callback(task_output)
    
    # Should still record in non_fatal_errors before re-raising
    assert len(task.non_fatal_errors) == 1
    assert "callback: Test callback failure" in task.non_fatal_errors[0]


@pytest.mark.asyncio
async def test_callback_failure_policy_disabled():
    """Test that callback errors are logged but not re-raised when fail_on_callback_error=False"""
    def failing_callback(task_output):
        raise RuntimeError("Test callback failure")
    
    task = Task(
        description="Test task",
        callback=failing_callback,
        fail_on_callback_error=False,  # Default behavior
        quality_check=False
    )
    
    task_output = TaskOutput(description="Test", raw="test output", agent="test")
    
    # Should not re-raise the exception when policy is disabled
    await task.execute_callback(task_output)  # Should not raise
    
    # Should record error in non_fatal_errors
    assert len(task.non_fatal_errors) == 1
    assert "callback: Test callback failure" in task.non_fatal_errors[0]
    assert task_output.callback_error == "Test callback failure"


@pytest.mark.asyncio
async def test_memory_failure_policy():
    """Test memory error handling respects fail_on_memory_error policy"""
    # This test verifies the policy exists and can be configured
    # Full integration testing would require memory setup
    
    task_fail_enabled = Task(
        description="Test task",
        fail_on_memory_error=True
    )
    
    task_fail_disabled = Task(
        description="Test task", 
        fail_on_memory_error=False
    )
    
    assert task_fail_enabled.fail_on_memory_error is True
    assert task_fail_disabled.fail_on_memory_error is False


@pytest.mark.asyncio
async def test_non_fatal_errors_attached_to_output():
    """Test that non_fatal_errors are properly attached to TaskOutput"""
    task = Task(description="Test task", quality_check=False)
    # Manually add some errors to test attachment
    task.non_fatal_errors.append("test error 1")
    task.non_fatal_errors.append("test error 2")
    
    task_output = TaskOutput(description="Test", raw="test output", agent="test")
    
    # Execute callback (which should attach errors)
    await task.execute_callback(task_output)
    
    # Verify errors were attached
    assert hasattr(task_output, 'non_fatal_errors')
    assert task_output.non_fatal_errors == ["test error 1", "test error 2"]