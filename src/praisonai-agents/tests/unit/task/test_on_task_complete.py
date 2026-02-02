"""
Tests for Task.on_task_complete parameter (renamed from callback).

TDD: These tests are written FIRST before implementation.

The rename from `callback` to `on_task_complete` aligns with:
- WorkflowHooksConfig.on_step_complete
- WorkflowHooksConfig.on_workflow_complete  
- MultiAgentHooksConfig.on_task_complete

This ensures consistent naming across the SDK.
"""
import warnings
import pytest
import asyncio


class TestOnTaskCompleteParameter:
    """Test that on_task_complete parameter works correctly."""
    
    def test_on_task_complete_parameter_accepted(self):
        """Task should accept on_task_complete parameter."""
        from praisonaiagents import Task
        
        def my_callback(output):
            pass
        
        task = Task(
            description="Test task",
            on_task_complete=my_callback
        )
        
        # The callback should be stored (internally as self.callback for minimal diff)
        assert task.callback is my_callback
    
    def test_on_task_complete_default_none(self):
        """on_task_complete should default to None."""
        from praisonaiagents import Task
        
        task = Task(description="Test task")
        
        assert task.callback is None
    
    def test_on_task_complete_with_sync_function(self):
        """on_task_complete should work with sync functions."""
        from praisonaiagents import Task
        
        results = []
        
        def sync_callback(output):
            results.append(output)
        
        task = Task(
            description="Test task",
            on_task_complete=sync_callback
        )
        
        assert task.callback is sync_callback
        assert callable(task.callback)
    
    def test_on_task_complete_with_async_function(self):
        """on_task_complete should work with async functions."""
        from praisonaiagents import Task
        
        async def async_callback(output):
            pass
        
        task = Task(
            description="Test task",
            on_task_complete=async_callback
        )
        
        assert task.callback is async_callback
        assert asyncio.iscoroutinefunction(task.callback)


class TestCallbackDeprecation:
    """Test that callback parameter is deprecated but still works."""
    
    def test_callback_emits_deprecation_warning(self):
        """Using callback= should emit DeprecationWarning."""
        from praisonaiagents import Task
        
        def my_callback(output):
            pass
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            task = Task(
                description="Test task",
                callback=my_callback
            )
            
            # Should have exactly one deprecation warning about callback
            deprecation_warnings = [
                x for x in w 
                if issubclass(x.category, DeprecationWarning) 
                and 'callback' in str(x.message).lower()
            ]
            assert len(deprecation_warnings) == 1
            assert 'on_task_complete' in str(deprecation_warnings[0].message)
    
    def test_callback_still_works(self):
        """callback= should still work (backward compatibility)."""
        from praisonaiagents import Task
        
        def my_callback(output):
            pass
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            
            task = Task(
                description="Test task",
                callback=my_callback
            )
            
            # Should still be stored
            assert task.callback is my_callback
    
    def test_on_task_complete_no_deprecation_warning(self):
        """Using on_task_complete= should NOT emit deprecation warning."""
        from praisonaiagents import Task
        
        def my_callback(output):
            pass
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            task = Task(
                description="Test task",
                on_task_complete=my_callback
            )
            
            # Should have no deprecation warnings about callback
            deprecation_warnings = [
                x for x in w 
                if issubclass(x.category, DeprecationWarning) 
                and 'callback' in str(x.message).lower()
            ]
            assert len(deprecation_warnings) == 0


class TestBothParametersProvided:
    """Test behavior when both callback and on_task_complete are provided."""
    
    def test_both_parameters_raises_error(self):
        """Providing both callback and on_task_complete should raise ValueError."""
        from praisonaiagents import Task
        
        def callback1(output):
            pass
        
        def callback2(output):
            pass
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            
            with pytest.raises(ValueError) as exc_info:
                Task(
                    description="Test task",
                    callback=callback1,
                    on_task_complete=callback2
                )
            
            assert "callback" in str(exc_info.value).lower()
            assert "on_task_complete" in str(exc_info.value).lower()


class TestCallbackExecution:
    """Test that callbacks are executed correctly."""
    
    def test_sync_callback_receives_task_output(self):
        """Sync callback should receive TaskOutput."""
        from praisonaiagents import Task
        from praisonaiagents.main import TaskOutput
        
        received = []
        
        def my_callback(output):
            received.append(output)
        
        task = Task(
            description="Test task",
            on_task_complete=my_callback
        )
        
        # Create a mock TaskOutput
        task_output = TaskOutput(
            description="Test",
            raw="Test output",
            agent="TestAgent"
        )
        
        # Execute callback synchronously
        task.execute_callback_sync(task_output)
        
        # Give async task time to complete
        import time
        time.sleep(0.1)
        
        assert len(received) == 1
        assert received[0].raw == "Test output"
    
    @pytest.mark.asyncio
    async def test_async_callback_receives_task_output(self):
        """Async callback should receive TaskOutput."""
        from praisonaiagents import Task
        from praisonaiagents.main import TaskOutput
        
        received = []
        
        async def my_callback(output):
            received.append(output)
        
        task = Task(
            description="Test task",
            on_task_complete=my_callback
        )
        
        # Create a mock TaskOutput
        task_output = TaskOutput(
            description="Test",
            raw="Test output",
            agent="TestAgent"
        )
        
        # Execute callback
        await task.execute_callback(task_output)
        
        assert len(received) == 1
        assert received[0].raw == "Test output"


class TestNamingConsistency:
    """Test that naming is consistent with other hooks/callbacks in the SDK."""
    
    def test_matches_workflow_hooks_config_pattern(self):
        """on_task_complete follows the on_<entity>_complete pattern."""
        from praisonaiagents.workflows.workflow_configs import WorkflowHooksConfig
        
        # WorkflowHooksConfig has on_step_complete, on_workflow_complete
        config = WorkflowHooksConfig()
        
        assert hasattr(config, 'on_step_complete')
        assert hasattr(config, 'on_workflow_complete')
    
    def test_matches_multi_agent_hooks_config_pattern(self):
        """on_task_complete matches MultiAgentHooksConfig.on_task_complete."""
        from praisonaiagents.config.feature_configs import MultiAgentHooksConfig
        
        # MultiAgentHooksConfig already has on_task_complete
        config = MultiAgentHooksConfig()
        
        assert hasattr(config, 'on_task_complete')


class TestCallbackWithMetadata:
    """Test callback with metadata support (2-parameter callbacks)."""
    
    @pytest.mark.asyncio
    async def test_two_param_callback_receives_metadata(self):
        """Two-parameter callback should receive TaskOutput and metadata."""
        from praisonaiagents import Task
        from praisonaiagents.main import TaskOutput
        
        received_output = []
        received_metadata = []
        
        async def my_callback(output, metadata):
            received_output.append(output)
            received_metadata.append(metadata)
        
        task = Task(
            name="test_task",
            description="Test task",
            on_task_complete=my_callback
        )
        
        task_output = TaskOutput(
            description="Test",
            raw="Test output",
            agent="TestAgent"
        )
        
        await task.execute_callback(task_output)
        
        assert len(received_output) == 1
        assert len(received_metadata) == 1
        assert 'task_id' in received_metadata[0]
        assert 'task_name' in received_metadata[0]
        assert received_metadata[0]['task_name'] == "test_task"
