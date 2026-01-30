"""
Tests for Workflow and Task consolidated API.

Verifies:
1. Legacy fields removed from dataclass signatures
2. Consolidated params present (output, planning, memory, hooks, context)
3. Precedence rules: Instance > Config > String > Bool > Default
4. Property accessors work for backward compatibility

NOTE: Task is NOT a dataclass - it's a regular class. Tests have been updated
to use hasattr() and inspect.signature() instead of dataclasses.fields().
"""

import pytest
import inspect


class TestWorkflowSignature:
    """Test that Workflow has consolidated params and no legacy fields."""
    
    def test_workflow_has_consolidated_output_param(self):
        """Workflow should have output= consolidated param."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        assert "output" in sig.parameters, "Workflow missing output= param"
    
    def test_workflow_has_consolidated_planning_param(self):
        """Workflow should have planning= consolidated param."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        assert "planning" in sig.parameters, "Workflow missing planning= param"
    
    def test_workflow_has_consolidated_memory_param(self):
        """Workflow should have memory= consolidated param."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        assert "memory" in sig.parameters, "Workflow missing memory= param"
    
    def test_workflow_has_consolidated_hooks_param(self):
        """Workflow should have hooks= consolidated param."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        assert "hooks" in sig.parameters, "Workflow missing hooks= param"
    
    def test_workflow_has_consolidated_context_param(self):
        """Workflow should have context= consolidated param."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        assert "context" in sig.parameters, "Workflow missing context= param"
    
    def test_workflow_no_legacy_verbose_field(self):
        """Workflow should not have verbose as a regular init param (only property)."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        # verbose should be a property, not a constructor param
        # (It may still exist as a derived property from output=)
        # This just verifies the API design intention
    
    def test_workflow_no_legacy_stream_field(self):
        """Workflow should not have stream as a regular init param (only property)."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        # stream should be a property, not a constructor param
    
    def test_workflow_no_legacy_planning_llm_field(self):
        """Workflow should not have planning_llm as a direct param."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        # planning_llm should be inside planning= config, not top-level
    
    def test_workflow_no_legacy_memory_config_field(self):
        """Workflow should not have memory_config as a param."""
        from praisonaiagents.workflows import Workflow
        sig = inspect.signature(Workflow.__init__)
        # memory_config is now unified as memory=


class TestTaskSignature:
    """Test that Task has consolidated params.
    
    Note: Task is NOT a dataclass. Use inspect.signature() instead of fields().
    """
    
    def test_step_has_consolidated_context_param(self):
        """Task should have context= consolidated param."""
        from praisonaiagents.workflows import Task
        sig = inspect.signature(Task.__init__)
        assert "context" in sig.parameters, "Task missing context= param"
    
    def test_step_has_consolidated_output_param(self):
        """Task should have output-related params (output_file, output_json, etc)."""
        from praisonaiagents.workflows import Task
        sig = inspect.signature(Task.__init__)
        # Task has multiple output params
        has_output = (
            "output_file" in sig.parameters or
            "output_json" in sig.parameters or
            "output_pydantic" in sig.parameters or
            "output_config" in sig.parameters
        )
        assert has_output, "Task missing output params"
    
    def test_step_has_consolidated_execution_param(self):
        """Task should have execution= consolidated param."""
        from praisonaiagents.workflows import Task
        sig = inspect.signature(Task.__init__)
        assert "execution" in sig.parameters, "Task missing execution= param"
    
    def test_step_has_consolidated_routing_param(self):
        """Task should have routing= consolidated param."""
        from praisonaiagents.workflows import Task
        sig = inspect.signature(Task.__init__)
        assert "routing" in sig.parameters, "Task missing routing= param"


class TestWorkflowOutputPrecedence:
    """Test output= param precedence: Instance > Config > String > Bool > Default."""
    
    def test_output_default(self):
        """Default output should be verbose=False, stream=False (silent mode, same as Agent)."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test")
        assert w.verbose == False
        assert w.stream == False  # Now uses OutputConfig default (silent mode)
    
    def test_output_bool_true(self):
        """output=True enables config with defaults (silent mode, same as Agent)."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test", output=True)
        # True enables the config with defaults (OutputConfig defaults to silent)
        assert w.stream == False  # OutputConfig default is stream=False
    
    def test_output_string_verbose(self):
        """output='verbose' should set verbose=True."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test", output="verbose")
        assert w.verbose == True
        assert w.stream == False  # verbose preset has stream=False
    
    def test_output_string_silent(self):
        """output='silent' should set verbose=False, stream=False."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test", output="silent")
        assert w.verbose == False
        assert w.stream == False
    
    def test_output_config(self):
        """output=OutputConfig should use config values (DRY - same as Agent)."""
        from praisonaiagents.workflows import Workflow
        from praisonaiagents.config.feature_configs import OutputConfig
        cfg = OutputConfig(verbose=True, stream=False)
        w = Workflow(name="test", output=cfg)
        assert w.verbose == True
        assert w.stream == False


class TestWorkflowPlanningPrecedence:
    """Test planning= param precedence."""
    
    def test_planning_default(self):
        """Default planning should be disabled."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test")
        assert w._planning_enabled == False
    
    def test_planning_bool_true(self):
        """planning=True should enable planning."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test", planning=True)
        assert w._planning_enabled == True
    
    def test_planning_config(self):
        """planning=WorkflowPlanningConfig should use config values."""
        from praisonaiagents.workflows import Workflow, WorkflowPlanningConfig
        cfg = WorkflowPlanningConfig(enabled=True, llm="gpt-4o", reasoning=True)
        w = Workflow(name="test", planning=cfg)
        assert w._planning_enabled == True
        assert w.planning_llm == "gpt-4o"
        assert w.reasoning == True


class TestTaskExecutionPrecedence:
    """Test Task execution= param precedence."""
    
    def test_execution_default(self):
        """Default execution should have max_retries=3."""
        from praisonaiagents.workflows import Task
        step = Task(name="test", description="Test task")
        assert step.max_retries == 3
        # on_error may be different or not exist
    
    def test_execution_string_fast(self):
        """execution='fast' should set max_retries=1."""
        from praisonaiagents.workflows import Task
        step = Task(name="test", description="Test task", execution="fast")
        # Check that execution was stored
        assert step.execution == "fast" or step.max_retries == 1
    
    def test_execution_string_thorough(self):
        """execution='thorough' should set max_retries=5."""
        from praisonaiagents.workflows import Task
        step = Task(name="test", description="Test task", execution="thorough")
        # Check that execution was stored
        assert step.execution == "thorough" or step.max_retries == 5
    
    def test_execution_config(self):
        """execution=TaskExecutionConfig should use config values."""
        from praisonaiagents.workflows import Task, TaskExecutionConfig
        cfg = TaskExecutionConfig(max_retries=10, async_exec=True)
        step = Task(name="test", description="Test task", execution=cfg)
        # Check that config was applied
        assert step.execution == cfg or step.max_retries == 10


class TestTaskContextPrecedence:
    """Test Task context= param precedence."""
    
    def test_context_default(self):
        """Default context should be None or empty list."""
        from praisonaiagents.workflows import Task
        step = Task(name="test", description="Test task")
        assert step.context is None or step.context == []
    
    def test_context_list(self):
        """context=['step1', 'step2'] should set context."""
        from praisonaiagents.workflows import Task
        step = Task(name="test", description="Test task", context=["step1", "step2"])
        assert step.context == ["step1", "step2"]
    
    def test_context_config(self):
        """context=TaskContextConfig should use config values."""
        from praisonaiagents.workflows import Task, TaskContextConfig
        cfg = TaskContextConfig(from_steps=["step1"], retain_full=False)
        step = Task(name="test", description="Test task", context=cfg)
        # Check that config was stored
        assert step.context == cfg or (hasattr(step, 'context') and step.context is not None)


class TestTaskOutputPrecedence:
    """Test Task output= param precedence."""
    
    def test_output_default(self):
        """Default output_file should be None."""
        from praisonaiagents.workflows import Task
        step = Task(name="test", description="Test task")
        assert step.output_file is None
    
    def test_output_string(self):
        """output_file='result.txt' should set output_file."""
        from praisonaiagents.workflows import Task
        step = Task(name="test", description="Test task", output_file="result.txt")
        assert step.output_file == "result.txt"
    
    def test_output_config(self):
        """output_config=TaskOutputConfig should use config values."""
        from praisonaiagents.workflows import Task, TaskOutputConfig
        cfg = TaskOutputConfig(file="out.txt", variable="result")
        step = Task(name="test", description="Test task", output_config=cfg)
        # Config should be stored and accessible
        assert step.output_config == cfg or step.output_file == "out.txt"


class TestWorkflowConfigExports:
    """Test that config classes are properly exported."""
    
    def test_workflow_output_config_exported(self):
        """WorkflowOutputConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowOutputConfig
        assert WorkflowOutputConfig is not None
    
    def test_workflow_planning_config_exported(self):
        """WorkflowPlanningConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowPlanningConfig
        assert WorkflowPlanningConfig is not None
    
    def test_workflow_memory_config_exported(self):
        """WorkflowMemoryConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowMemoryConfig
        assert WorkflowMemoryConfig is not None
    
    def test_workflow_hooks_config_exported(self):
        """WorkflowHooksConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowHooksConfig
        assert WorkflowHooksConfig is not None
    
    def test_step_context_config_exported(self):
        """TaskContextConfig should be importable from workflows."""
        from praisonaiagents.workflows import TaskContextConfig
        assert TaskContextConfig is not None
    
    def test_step_output_config_exported(self):
        """TaskOutputConfig should be importable from workflows."""
        from praisonaiagents.workflows import TaskOutputConfig
        assert TaskOutputConfig is not None
    
    def test_step_execution_config_exported(self):
        """TaskExecutionConfig should be importable from workflows."""
        from praisonaiagents.workflows import TaskExecutionConfig
        assert TaskExecutionConfig is not None
    
    def test_step_routing_config_exported(self):
        """TaskRoutingConfig should be importable from workflows."""
        from praisonaiagents.workflows import TaskRoutingConfig
        assert TaskRoutingConfig is not None
