"""
TDD Tests for TaskExecutionConfig Resolution in Task class.

These tests verify that TaskExecutionConfig fields are properly resolved
to Task properties when passed via the execution parameter.

Test Categories:
1. TaskExecutionConfig full resolution
2. Direct params precedence over config
3. Default values when neither provided
4. Backward compatibility with direct params
"""

import pytest
from praisonaiagents.task.task import Task
from praisonaiagents.workflows.workflow_configs import TaskExecutionConfig


class TestTaskExecutionConfigResolution:
    """Test that TaskExecutionConfig fields are resolved to Task properties."""
    
    def test_async_exec_resolved_from_config(self):
        """TaskExecutionConfig.async_exec should set Task.async_execution."""
        task = Task(
            name="test_task",
            action="Do something",
            execution=TaskExecutionConfig(async_exec=True)
        )
        assert task.async_execution == True
    
    def test_quality_check_resolved_from_config(self):
        """TaskExecutionConfig.quality_check should set Task.quality_check."""
        task = Task(
            name="test_task",
            action="Do something",
            execution=TaskExecutionConfig(quality_check=False)
        )
        assert task.quality_check == False
    
    def test_rerun_resolved_from_config(self):
        """TaskExecutionConfig.rerun should set Task.rerun."""
        task = Task(
            name="test_task",
            action="Do something",
            execution=TaskExecutionConfig(rerun=False)
        )
        assert task.rerun == False
    
    def test_max_retries_resolved_from_config(self):
        """TaskExecutionConfig.max_retries should set Task.max_retries."""
        task = Task(
            name="test_task",
            action="Do something",
            execution=TaskExecutionConfig(max_retries=10)
        )
        assert task.max_retries == 10
    
    def test_on_error_resolved_from_config(self):
        """TaskExecutionConfig.on_error should set Task.on_error (already implemented)."""
        task = Task(
            name="test_task",
            action="Do something",
            execution=TaskExecutionConfig(on_error="continue")
        )
        assert task.on_error == "continue"
    
    def test_all_fields_resolved_together(self):
        """All TaskExecutionConfig fields should be resolved together."""
        config = TaskExecutionConfig(
            async_exec=True,
            quality_check=False,
            rerun=False,
            max_retries=7,
            on_error="retry"
        )
        task = Task(
            name="test_task",
            action="Do something",
            execution=config
        )
        
        assert task.async_execution == True
        assert task.quality_check == False
        assert task.rerun == False
        assert task.max_retries == 7
        assert task.on_error == "retry"


class TestDirectParamsPrecedence:
    """Test that non-default direct params take precedence over TaskExecutionConfig.
    
    Note: Due to Python's inability to distinguish between f(x=False) and f() when
    default is False, we use this rule: direct params take precedence only when
    they differ from their default values. This means:
    - async_execution=True overrides config (default is False)
    - quality_check=False overrides config (default is True)  
    - max_retries=5 overrides config (default is 3)
    - rerun=True overrides config (default is False)
    """
    
    def test_direct_async_execution_true_takes_precedence(self):
        """Direct async_execution=True should override config's False."""
        task = Task(
            name="test_task",
            action="Do something",
            async_execution=True,
            execution=TaskExecutionConfig(async_exec=False)
        )
        # Direct param (True, non-default) should take precedence
        assert task.async_execution == True
    
    def test_direct_quality_check_false_takes_precedence(self):
        """Direct quality_check=False should override config's True."""
        task = Task(
            name="test_task",
            action="Do something",
            quality_check=False,
            execution=TaskExecutionConfig(quality_check=True)
        )
        # Direct param (False, non-default) should take precedence
        assert task.quality_check == False
    
    def test_direct_max_retries_takes_precedence(self):
        """Direct max_retries param should override config."""
        task = Task(
            name="test_task",
            action="Do something",
            max_retries=5,
            execution=TaskExecutionConfig(max_retries=10)
        )
        # Direct param (5, non-default) should take precedence
        assert task.max_retries == 5
    
    def test_direct_rerun_takes_precedence(self):
        """Direct rerun=True param should override config."""
        task = Task(
            name="test_task",
            action="Do something",
            rerun=True,
            execution=TaskExecutionConfig(rerun=False)
        )
        # Direct param (True, non-default) should take precedence
        assert task.rerun == True


class TestDefaultValues:
    """Test default values when neither direct param nor config provided."""
    
    def test_default_async_execution(self):
        """Default async_execution should be False."""
        task = Task(name="test_task", action="Do something")
        assert task.async_execution == False
    
    def test_default_quality_check(self):
        """Default quality_check should be True."""
        task = Task(name="test_task", action="Do something")
        assert task.quality_check == True
    
    def test_default_rerun(self):
        """Default rerun should be False."""
        task = Task(name="test_task", action="Do something")
        assert task.rerun == False
    
    def test_default_max_retries(self):
        """Default max_retries should be 3."""
        task = Task(name="test_task", action="Do something")
        assert task.max_retries == 3
    
    def test_default_on_error(self):
        """Default on_error should be 'stop'."""
        task = Task(name="test_task", action="Do something")
        assert task.on_error == "stop"


class TestBackwardCompatibility:
    """Test that direct params continue to work (backward compatibility)."""
    
    def test_direct_async_execution_works(self):
        """Direct async_execution param should work without config."""
        task = Task(
            name="test_task",
            action="Do something",
            async_execution=True
        )
        assert task.async_execution == True
    
    def test_direct_quality_check_works(self):
        """Direct quality_check param should work without config."""
        task = Task(
            name="test_task",
            action="Do something",
            quality_check=False
        )
        assert task.quality_check == False
    
    def test_direct_max_retries_works(self):
        """Direct max_retries param should work without config."""
        task = Task(
            name="test_task",
            action="Do something",
            max_retries=15
        )
        assert task.max_retries == 15
    
    def test_direct_rerun_works(self):
        """Direct rerun param should work without config."""
        task = Task(
            name="test_task",
            action="Do something",
            rerun=True
        )
        assert task.rerun == True
    
    def test_direct_on_error_works(self):
        """Direct on_error param should work without config."""
        task = Task(
            name="test_task",
            action="Do something",
            on_error="continue"
        )
        assert task.on_error == "continue"


class TestExecutionConfigStorage:
    """Test that execution config is properly stored."""
    
    def test_execution_config_stored(self):
        """TaskExecutionConfig should be stored in task.execution."""
        config = TaskExecutionConfig(async_exec=True)
        task = Task(
            name="test_task",
            action="Do something",
            execution=config
        )
        assert task.execution is config
    
    def test_execution_none_when_not_provided(self):
        """task.execution should be None when not provided."""
        task = Task(name="test_task", action="Do something")
        assert task.execution is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
