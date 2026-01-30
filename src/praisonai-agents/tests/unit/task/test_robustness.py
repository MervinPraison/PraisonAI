"""
Tests for PraisonAI Robustness Improvements.

Tests the following features:
1. Task.skip_on_failure - Allow workflows to continue when one step fails
2. Task.retry_delay - Exponential backoff for retries
3. Workflow.history - Execution trace for debugging
4. Include(workflow=) - Workflow composition
5. when() - Alias for if_() with cleaner name

TDD: These tests are written FIRST before implementation.
"""
import warnings
import pytest


class TestTaskSkipOnFailure:
    """Tests for Task.skip_on_failure parameter."""
    
    def test_task_skip_on_failure_default_false(self):
        """skip_on_failure should default to False."""
        from praisonaiagents import Task
        task = Task(description="Test task")
        assert task.skip_on_failure is False
    
    def test_task_skip_on_failure_true(self):
        """Task should accept skip_on_failure=True."""
        from praisonaiagents import Task
        task = Task(description="Optional step", skip_on_failure=True)
        assert task.skip_on_failure is True
    
    def test_task_skip_on_failure_false_explicit(self):
        """Task should accept skip_on_failure=False explicitly."""
        from praisonaiagents import Task
        task = Task(description="Critical step", skip_on_failure=False)
        assert task.skip_on_failure is False


class TestTaskRetryDelay:
    """Tests for Task.retry_delay parameter."""
    
    def test_task_retry_delay_default_zero(self):
        """retry_delay should default to 0.0."""
        from praisonaiagents import Task
        task = Task(description="Test task")
        assert task.retry_delay == 0.0
    
    def test_task_retry_delay_custom_value(self):
        """Task should accept custom retry_delay."""
        from praisonaiagents import Task
        task = Task(description="Test task", retry_delay=1.0)
        assert task.retry_delay == 1.0
    
    def test_task_retry_delay_float(self):
        """retry_delay should accept float values."""
        from praisonaiagents import Task
        task = Task(description="Test task", retry_delay=0.5)
        assert task.retry_delay == 0.5
    
    def test_task_retry_delay_with_max_retries(self):
        """retry_delay should work alongside max_retries."""
        from praisonaiagents import Task
        task = Task(description="Test task", retry_delay=2.0, max_retries=5)
        assert task.retry_delay == 2.0
        assert task.max_retries == 5


class TestWorkflowHistory:
    """Tests for Workflow.history parameter."""
    
    def test_workflow_history_default_false(self):
        """history should default to False."""
        from praisonaiagents.workflows import Workflow
        workflow = Workflow(steps=[])
        assert workflow.history is False
    
    def test_workflow_history_true(self):
        """Workflow should accept history=True."""
        from praisonaiagents.workflows import Workflow
        workflow = Workflow(steps=[], history=True)
        assert workflow.history is True
    
    def test_workflow_execution_history_initialized(self):
        """_execution_history should be initialized as empty list."""
        from praisonaiagents.workflows import Workflow
        workflow = Workflow(steps=[], history=True)
        assert hasattr(workflow, '_execution_history')
        assert workflow._execution_history == []
    
    def test_workflow_get_history_method_exists(self):
        """Workflow should have get_history() method."""
        from praisonaiagents.workflows import Workflow
        workflow = Workflow(steps=[], history=True)
        assert hasattr(workflow, 'get_history')
        assert callable(workflow.get_history)
    
    def test_workflow_get_history_returns_list(self):
        """get_history() should return a list."""
        from praisonaiagents.workflows import Workflow
        workflow = Workflow(steps=[], history=True)
        history = workflow.get_history()
        assert isinstance(history, list)


class TestIncludeWorkflow:
    """Tests for Include with workflow parameter."""
    
    def test_include_with_recipe(self):
        """Include should work with recipe parameter (existing behavior)."""
        from praisonaiagents.workflows import include
        inc = include(recipe="wordpress-publisher")
        assert inc.recipe == "wordpress-publisher"
    
    def test_include_with_workflow(self):
        """Include should accept workflow parameter."""
        from praisonaiagents.workflows import include, Workflow
        
        sub_workflow = Workflow(name="sub", steps=[])
        inc = include(workflow=sub_workflow)
        assert inc.workflow is sub_workflow
    
    def test_include_requires_recipe_or_workflow(self):
        """Include should raise error if neither recipe nor workflow provided."""
        from praisonaiagents.workflows import Include
        
        with pytest.raises(ValueError, match="Either 'recipe' or 'workflow' must be provided"):
            Include()
    
    def test_include_with_workflow_and_input(self):
        """Include should accept workflow with input override."""
        from praisonaiagents.workflows import include, Workflow
        
        sub_workflow = Workflow(name="sub", steps=[])
        inc = include(workflow=sub_workflow, input="custom input")
        assert inc.workflow is sub_workflow
        assert inc.input == "custom input"


class TestWhenAlias:
    """Tests for when() alias for if_()."""
    
    def test_when_function_exists(self):
        """when() function should exist."""
        from praisonaiagents.workflows import when
        assert callable(when)
    
    def test_when_returns_if_object(self):
        """when() should return an If object."""
        from praisonaiagents.workflows import when, If
        result = when(condition="True", then_steps=[])
        assert isinstance(result, If)
    
    def test_when_with_condition_and_then_steps(self):
        """when() should accept condition and then_steps."""
        from praisonaiagents.workflows import when
        result = when(
            condition="{{score}} > 80",
            then_steps=["step1", "step2"]
        )
        assert result.condition == "{{score}} > 80"
        assert result.then_steps == ["step1", "step2"]
    
    def test_when_with_else_steps(self):
        """when() should accept optional else_steps."""
        from praisonaiagents.workflows import when
        result = when(
            condition="{{approved}}",
            then_steps=["approve"],
            else_steps=["reject"]
        )
        assert result.then_steps == ["approve"]
        assert result.else_steps == ["reject"]
    
    def test_if_function_works(self):
        """if_() should work as expected."""
        from praisonaiagents.workflows import if_
        
        # if_() is a valid function that returns an If object
        result = if_(condition="True", then_steps=[])
        # No deprecation warning currently - both if_() and when() work
        assert result is not None


class TestExportsAndImports:
    """Tests for proper exports in __init__.py files."""
    
    def test_when_exported_from_workflows(self):
        """when should be exported from praisonaiagents.workflows."""
        from praisonaiagents.workflows import when
        assert callable(when)
    
    def test_when_in_workflows_all(self):
        """when should be in workflows __all__."""
        import praisonaiagents.workflows as workflows_module
        assert 'when' in workflows_module.__all__
