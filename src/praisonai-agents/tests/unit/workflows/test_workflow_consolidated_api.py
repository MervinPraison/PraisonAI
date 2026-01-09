"""
Tests for Workflow and WorkflowStep consolidated API.

Verifies:
1. Legacy fields removed from dataclass signatures
2. Consolidated params present (output, planning, memory, hooks, context)
3. Precedence rules: Instance > Config > String > Bool > Default
4. Property accessors work for backward compatibility
"""

import pytest
from dataclasses import fields


class TestWorkflowSignature:
    """Test that Workflow has consolidated params and no legacy fields."""
    
    def test_workflow_has_consolidated_output_param(self):
        """Workflow should have output= consolidated param."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "output" in field_names, "Workflow missing output= param"
    
    def test_workflow_has_consolidated_planning_param(self):
        """Workflow should have planning= consolidated param."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "planning" in field_names, "Workflow missing planning= param"
    
    def test_workflow_has_consolidated_memory_param(self):
        """Workflow should have memory= consolidated param."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "memory" in field_names, "Workflow missing memory= param"
    
    def test_workflow_has_consolidated_hooks_param(self):
        """Workflow should have hooks= consolidated param."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "hooks" in field_names, "Workflow missing hooks= param"
    
    def test_workflow_has_consolidated_context_param(self):
        """Workflow should have context= consolidated param."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "context" in field_names, "Workflow missing context= param"
    
    def test_workflow_no_legacy_verbose_field(self):
        """Workflow should not have verbose as a dataclass field (only property)."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        # verbose should be a property, not a field
        assert "verbose" not in field_names or field_names == [], \
            "Workflow should not have verbose as dataclass field"
    
    def test_workflow_no_legacy_stream_field(self):
        """Workflow should not have stream as a dataclass field (only property)."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "stream" not in field_names, \
            "Workflow should not have stream as dataclass field"
    
    def test_workflow_no_legacy_planning_llm_field(self):
        """Workflow should not have planning_llm as a dataclass field."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "planning_llm" not in field_names, \
            "Workflow should not have planning_llm as dataclass field"
    
    def test_workflow_no_legacy_memory_config_field(self):
        """Workflow should not have memory_config as a dataclass field."""
        from praisonaiagents.workflows import Workflow
        field_names = [f.name for f in fields(Workflow)]
        assert "memory_config" not in field_names, \
            "Workflow should not have memory_config as dataclass field"


class TestWorkflowStepSignature:
    """Test that WorkflowStep has consolidated params."""
    
    def test_step_has_consolidated_context_param(self):
        """WorkflowStep should have context= consolidated param."""
        from praisonaiagents.workflows import WorkflowStep
        field_names = [f.name for f in fields(WorkflowStep)]
        assert "context" in field_names, "WorkflowStep missing context= param"
    
    def test_step_has_consolidated_output_param(self):
        """WorkflowStep should have output= consolidated param."""
        from praisonaiagents.workflows import WorkflowStep
        field_names = [f.name for f in fields(WorkflowStep)]
        assert "output" in field_names, "WorkflowStep missing output= param"
    
    def test_step_has_consolidated_execution_param(self):
        """WorkflowStep should have execution= consolidated param."""
        from praisonaiagents.workflows import WorkflowStep
        field_names = [f.name for f in fields(WorkflowStep)]
        assert "execution" in field_names, "WorkflowStep missing execution= param"
    
    def test_step_has_consolidated_routing_param(self):
        """WorkflowStep should have routing= consolidated param."""
        from praisonaiagents.workflows import WorkflowStep
        field_names = [f.name for f in fields(WorkflowStep)]
        assert "routing" in field_names, "WorkflowStep missing routing= param"


class TestWorkflowOutputPrecedence:
    """Test output= param precedence: Instance > Config > String > Bool > Default."""
    
    def test_output_default(self):
        """Default output should be verbose=False, stream=True."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test")
        assert w.verbose == False
        assert w.stream == True
    
    def test_output_bool_true(self):
        """output=True should enable verbose with defaults."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test", output=True)
        # True enables the config with defaults
        assert w.stream == True
    
    def test_output_string_verbose(self):
        """output='verbose' should set verbose=True."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test", output="verbose")
        assert w.verbose == True
        assert w.stream == True
    
    def test_output_string_silent(self):
        """output='silent' should set verbose=False, stream=False."""
        from praisonaiagents.workflows import Workflow
        w = Workflow(name="test", output="silent")
        assert w.verbose == False
        assert w.stream == False
    
    def test_output_config(self):
        """output=WorkflowOutputConfig should use config values."""
        from praisonaiagents.workflows import Workflow, WorkflowOutputConfig
        cfg = WorkflowOutputConfig(verbose=True, stream=False)
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


class TestWorkflowStepExecutionPrecedence:
    """Test WorkflowStep execution= param precedence."""
    
    def test_execution_default(self):
        """Default execution should have max_retries=3."""
        from praisonaiagents.workflows import WorkflowStep
        step = WorkflowStep(name="test")
        assert step.max_retries == 3
        assert step.on_error == "stop"
    
    def test_execution_string_fast(self):
        """execution='fast' should set max_retries=1."""
        from praisonaiagents.workflows import WorkflowStep
        step = WorkflowStep(name="test", execution="fast")
        assert step.max_retries == 1
        assert step.quality_check == False
    
    def test_execution_string_thorough(self):
        """execution='thorough' should set max_retries=5."""
        from praisonaiagents.workflows import WorkflowStep
        step = WorkflowStep(name="test", execution="thorough")
        assert step.max_retries == 5
        assert step.quality_check == True
    
    def test_execution_config(self):
        """execution=WorkflowStepExecutionConfig should use config values."""
        from praisonaiagents.workflows import WorkflowStep, WorkflowStepExecutionConfig
        cfg = WorkflowStepExecutionConfig(max_retries=10, async_exec=True)
        step = WorkflowStep(name="test", execution=cfg)
        assert step.max_retries == 10
        assert step.async_execution == True


class TestWorkflowStepContextPrecedence:
    """Test WorkflowStep context= param precedence."""
    
    def test_context_default(self):
        """Default context should be None."""
        from praisonaiagents.workflows import WorkflowStep
        step = WorkflowStep(name="test")
        assert step.context_from == None
    
    def test_context_list(self):
        """context=['step1', 'step2'] should set from_steps."""
        from praisonaiagents.workflows import WorkflowStep
        step = WorkflowStep(name="test", context=["step1", "step2"])
        assert step.context_from == ["step1", "step2"]
    
    def test_context_config(self):
        """context=WorkflowStepContextConfig should use config values."""
        from praisonaiagents.workflows import WorkflowStep, WorkflowStepContextConfig
        cfg = WorkflowStepContextConfig(from_steps=["step1"], retain_full=False)
        step = WorkflowStep(name="test", context=cfg)
        assert step.context_from == ["step1"]
        assert step.retain_full_context == False


class TestWorkflowStepOutputPrecedence:
    """Test WorkflowStep output= param precedence."""
    
    def test_output_default(self):
        """Default output should be None."""
        from praisonaiagents.workflows import WorkflowStep
        step = WorkflowStep(name="test")
        assert step.output_file == None
    
    def test_output_string(self):
        """output='result.txt' should set output_file."""
        from praisonaiagents.workflows import WorkflowStep
        step = WorkflowStep(name="test", output="result.txt")
        assert step.output_file == "result.txt"
    
    def test_output_config(self):
        """output=WorkflowStepOutputConfig should use config values."""
        from praisonaiagents.workflows import WorkflowStep, WorkflowStepOutputConfig
        cfg = WorkflowStepOutputConfig(file="out.txt", variable="result")
        step = WorkflowStep(name="test", output=cfg)
        assert step.output_file == "out.txt"
        assert step.output_variable == "result"


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
        """WorkflowStepContextConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowStepContextConfig
        assert WorkflowStepContextConfig is not None
    
    def test_step_output_config_exported(self):
        """WorkflowStepOutputConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowStepOutputConfig
        assert WorkflowStepOutputConfig is not None
    
    def test_step_execution_config_exported(self):
        """WorkflowStepExecutionConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowStepExecutionConfig
        assert WorkflowStepExecutionConfig is not None
    
    def test_step_routing_config_exported(self):
        """WorkflowStepRoutingConfig should be importable from workflows."""
        from praisonaiagents.workflows import WorkflowStepRoutingConfig
        assert WorkflowStepRoutingConfig is not None
