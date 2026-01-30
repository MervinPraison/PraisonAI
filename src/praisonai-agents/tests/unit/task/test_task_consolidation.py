"""
Tests for Task + Task Consolidation (Phase 4).

Tests the new parameters added to Task from Task:
- action (alias for description)
- handler (custom function instead of agent)
- should_run (condition function)
- loop_over / loop_var (iteration support)
- execution, routing, output (consolidated configs)
- autonomy, knowledge, web, reflection, planning, hooks, caching (feature configs)

TDD: These tests are written FIRST before implementation.
"""
import warnings


class TestTaskActionAlias:
    """Test that 'action' works as an alias for 'description'."""
    
    def test_action_as_description_alias(self):
        """When action is provided without description, action becomes description."""
        from praisonaiagents import Task
        
        task = Task(action="Write a blog post about AI")
        
        assert task.description == "Write a blog post about AI"
        assert task.action == "Write a blog post about AI"
    
    def test_description_takes_precedence(self):
        """When both action and description provided, description takes precedence."""
        from praisonaiagents import Task
        
        task = Task(
            description="Primary description",
            action="Secondary action"
        )
        
        assert task.description == "Primary description"
        assert task.action == "Secondary action"
    
    def test_action_attribute_always_set(self):
        """Task.action should always be set (from action or description)."""
        from praisonaiagents import Task
        
        task = Task(description="Research AI trends")
        
        assert task.action == "Research AI trends"


class TestTaskHandler:
    """Test that Task supports handler functions (from Task)."""
    
    def test_handler_param_exists(self):
        """Task should accept a handler parameter."""
        from praisonaiagents import Task
        
        def my_handler(context):
            return {"output": "processed"}
        
        task = Task(
            description="Process data",
            handler=my_handler
        )
        
        assert task.handler is my_handler
    
    def test_handler_default_none(self):
        """Handler should default to None."""
        from praisonaiagents import Task
        
        task = Task(description="Simple task")
        
        assert task.handler is None
    
    def test_handler_callable_check(self):
        """Handler must be callable if provided."""
        from praisonaiagents import Task
        
        def valid_handler(ctx):
            return "result"
        
        task = Task(description="Test", handler=valid_handler)
        assert callable(task.handler)


class TestTaskShouldRun:
    """Test that Task supports should_run condition (from Task)."""
    
    def test_should_run_param_exists(self):
        """Task should accept a should_run parameter."""
        from praisonaiagents import Task
        
        def check_condition(context):
            return context.get("enabled", False)
        
        task = Task(
            description="Conditional task",
            should_run=check_condition
        )
        
        assert task.should_run is check_condition
    
    def test_should_run_default_none(self):
        """should_run should default to None (always run)."""
        from praisonaiagents import Task
        
        task = Task(description="Always runs")
        
        assert task.should_run is None


class TestTaskLoopSupport:
    """Test that Task supports loop_over and loop_var (from Task)."""
    
    def test_loop_over_param_exists(self):
        """Task should accept loop_over parameter."""
        from praisonaiagents import Task
        
        task = Task(
            description="Process {{item}}",
            loop_over="items"
        )
        
        assert task.loop_over == "items"
    
    def test_loop_var_param_exists(self):
        """Task should accept loop_var parameter with default 'item'."""
        from praisonaiagents import Task
        
        task = Task(
            description="Process {{item}}",
            loop_over="items"
        )
        
        assert task.loop_var == "item"
    
    def test_loop_var_custom_value(self):
        """Task should accept custom loop_var value."""
        from praisonaiagents import Task
        
        task = Task(
            description="Process {{doc}}",
            loop_over="documents",
            loop_var="doc"
        )
        
        assert task.loop_var == "doc"
    
    def test_loop_defaults_none(self):
        """loop_over should default to None."""
        from praisonaiagents import Task
        
        task = Task(description="No loop")
        
        assert task.loop_over is None


class TestTaskConsolidatedConfigs:
    """Test that Task supports consolidated config objects (from Task)."""
    
    def test_execution_config_dict(self):
        """Task should accept execution config as dict."""
        from praisonaiagents import Task
        
        task = Task(
            description="Execute task",
            execution={"max_retries": 5, "async_exec": True}
        )
        
        assert task.execution is not None
    
    def test_routing_config_dict(self):
        """Task should accept routing config as dict."""
        from praisonaiagents import Task
        
        task = Task(
            description="Route task",
            routing={"next": ["task_b"], "on_error": "stop"}
        )
        
        assert task.routing is not None
    
    def test_output_config_dict(self):
        """Task should accept output config as dict (alternative to output_file/json)."""
        from praisonaiagents import Task
        
        task = Task(
            description="Output task",
            output_config={"file": "result.txt", "variable": "result"}
        )
        
        assert task.output_config is not None


class TestTaskFeatureConfigs:
    """Test that Task supports feature configs (from Task)."""
    
    def test_autonomy_param(self):
        """Task should accept autonomy parameter."""
        from praisonaiagents import Task
        
        task = Task(description="Autonomous task", autonomy=True)
        
        assert task.autonomy is True
    
    def test_knowledge_param(self):
        """Task should accept knowledge parameter."""
        from praisonaiagents import Task
        
        task = Task(description="Knowledge task", knowledge=["docs/"])
        
        assert task.knowledge == ["docs/"]
    
    def test_web_param(self):
        """Task should accept web parameter."""
        from praisonaiagents import Task
        
        task = Task(description="Web task", web=True)
        
        assert task.web is True
    
    def test_reflection_param(self):
        """Task should accept reflection parameter."""
        from praisonaiagents import Task
        
        task = Task(description="Reflective task", reflection=True)
        
        assert task.reflection is True
    
    def test_planning_param(self):
        """Task should accept planning parameter."""
        from praisonaiagents import Task
        
        task = Task(description="Planning task", planning=True)
        
        assert task.planning is True
    
    def test_hooks_param(self):
        """Task should accept hooks parameter."""
        from praisonaiagents import Task
        
        def my_hook(ctx):
            pass
        
        task = Task(description="Hooked task", hooks=[my_hook])
        
        assert task.hooks == [my_hook]
    
    def test_caching_param(self):
        """Task should accept caching parameter."""
        from praisonaiagents import Task
        
        task = Task(description="Cached task", caching=True)
        
        assert task.caching is True


class TestTaskBackwardCompatibility:
    """Ensure existing Task API still works unchanged."""
    
    def test_basic_task_creation(self):
        """Basic Task creation should work as before."""
        from praisonaiagents import Task
        
        task = Task(description="Simple task")
        
        assert task.description == "Simple task"
        assert task.status == "not started"
    
    def test_task_with_expected_output(self):
        """Task with expected_output should work."""
        from praisonaiagents import Task
        
        task = Task(
            description="Research task",
            expected_output="A detailed report"
        )
        
        assert task.expected_output == "A detailed report"
    
    def test_task_with_tools(self):
        """Task with tools should work."""
        from praisonaiagents import Task
        
        def my_tool():
            pass
        
        task = Task(description="Tool task", tools=[my_tool])
        
        assert my_tool in task.tools
    
    def test_task_with_output_file(self):
        """Task with output_file should still work."""
        from praisonaiagents import Task
        
        task = Task(
            description="File output task",
            output_file="output.txt"
        )
        
        assert task.output_file == "output.txt"
    
    def test_task_with_guardrails(self):
        """Task with guardrails should still work."""
        from praisonaiagents import Task
        
        def my_guardrail(output):
            return (True, output)
        
        task = Task(
            description="Guarded task",
            guardrails=my_guardrail
        )
        
        assert task.guardrail is my_guardrail


class TestTaskDeprecation:
    """Test v4 behavior: WorkflowStep was removed, Task is primary.
    
    In v4.0.0:
    - WorkflowStep was REMOVED entirely (raises ImportError)
    - Task is the primary class (no deprecation warning)
    """
    
    def test_workflowstep_removed_in_v4(self):
        """WorkflowStep was removed in v4 - should raise ImportError."""
        import pytest
        with pytest.raises(ImportError):
            from praisonaiagents.workflows import WorkflowStep
    
    def test_task_is_primary(self):
        """Task should be importable without deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonaiagents import Task
            
            # Task is the primary class - no deprecation warning expected
            task_warnings = [x for x in w if 'Task' in str(x.message) and issubclass(x.category, DeprecationWarning)]
            assert len(task_warnings) == 0, f"Task should not emit deprecation warning: {task_warnings}"
    
    def test_task_creates_task_instance(self):
        """Task(...) should create a Task instance."""
        from praisonaiagents import Task
        
        step = Task(
            name="writer",
            action="Write content"
        )
        
        # Should be a Task instance
        assert isinstance(step, Task)
    
    def test_task_params_work(self):
        """Task params should work correctly."""
        from praisonaiagents import Task
        
        def my_handler(ctx):
            return "result"
        
        step = Task(
            name="processor",
            action="Process data",
            handler=my_handler,
            loop_over="items"
        )
        
        assert step.name == "processor"
        assert step.action == "Process data"
        assert step.handler is my_handler
        assert step.loop_over == "items"


class TestWorkflowWithTask:
    """Test that Workflow works with Task instances."""
    
    def test_workflow_accepts_task_in_steps(self):
        """Workflow should accept Task instances in steps parameter."""
        from praisonaiagents import Task
        from praisonaiagents.workflows import Workflow
        
        task1 = Task(name="step1", action="First step")
        task2 = Task(name="step2", action="Second step")
        
        workflow = Workflow(steps=[task1, task2])
        
        assert len(workflow.steps) == 2
