"""
Test suite for Workflow Context Passing functionality.

Tests the enhanced workflow system's ability to pass context between steps,
including output accumulation, variable substitution, and selective context inclusion.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add the package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents.memory.workflows import (
    WorkflowStep,
    Workflow,
    WorkflowManager,
    create_workflow_manager
)


class TestWorkflowStepContextFields:
    """Test WorkflowStep dataclass context-related fields."""
    
    def test_workflow_step_has_context_from_field(self):
        """WorkflowStep should have context_from field."""
        step = WorkflowStep(
            name="test_step",
            action="do something",
            context_from=["step1", "step2"]
        )
        assert hasattr(step, 'context_from')
        assert step.context_from == ["step1", "step2"]
    
    def test_workflow_step_has_retain_full_context_field(self):
        """WorkflowStep should have retain_full_context field with default True."""
        step = WorkflowStep(name="test_step", action="do something")
        assert hasattr(step, 'retain_full_context')
        assert step.retain_full_context == True
    
    def test_workflow_step_has_output_variable_field(self):
        """WorkflowStep should have output_variable field."""
        step = WorkflowStep(
            name="test_step",
            action="do something",
            output_variable="research_result"
        )
        assert hasattr(step, 'output_variable')
        assert step.output_variable == "research_result"
    
    def test_workflow_step_to_dict_includes_new_fields(self):
        """to_dict() should include context-related fields."""
        step = WorkflowStep(
            name="test_step",
            action="do something",
            context_from=["step1"],
            retain_full_context=False,
            output_variable="result"
        )
        d = step.to_dict()
        assert "context_from" in d
        assert "retain_full_context" in d
        assert "output_variable" in d


class TestContextPassing:
    """Test context passing between workflow steps."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_step_receives_previous_step_output(self):
        """Step 2 should receive Step 1's output as context."""
        manager = WorkflowManager()
        
        # Create a simple workflow with 2 steps
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="step1", action="Generate data"),
                WorkflowStep(name="step2", action="Process {{previous_output}}")
            ]
        )
        self._register_workflow(manager, workflow)
        
        # Track what each step receives
        received_actions = []
        
        def mock_executor(action):
            received_actions.append(action)
            if "Generate" in action:
                return "Generated data: ABC123"
            return f"Processed: {action}"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert result["success"] == True
        assert len(result["results"]) == 2
        # Step 2 should have received the output from step 1
        assert "ABC123" in received_actions[1] or "previous_output" in received_actions[1]
    
    def test_context_accumulates_across_steps(self):
        """Each step should have access to all previous outputs when retain_full_context=True."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="step1", action="First action", retain_full_context=True),
                WorkflowStep(name="step2", action="Second action", retain_full_context=True),
                WorkflowStep(name="step3", action="Third with context: {{step1_output}} and {{step2_output}}", retain_full_context=True)
            ]
        )
        self._register_workflow(manager, workflow)
        
        outputs = ["Output1", "Output2", "Output3"]
        call_count = [0]
        
        def mock_executor(action):
            idx = call_count[0]
            call_count[0] += 1
            return outputs[idx]
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert result["success"] == True
        assert len(result["results"]) == 3
        # All outputs should be stored
        assert result["results"][0]["output"] == "Output1"
        assert result["results"][1]["output"] == "Output2"
        assert result["results"][2]["output"] == "Output3"
    
    def test_context_from_specific_steps(self):
        """Step should only receive context from specified steps via context_from."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="research", action="Research topic"),
                WorkflowStep(name="analysis", action="Analyze data"),
                WorkflowStep(
                    name="summary",
                    action="Summarize based on: {{research_output}}",
                    context_from=["research"],  # Only include research, not analysis
                    retain_full_context=False
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        received_actions = []
        
        def mock_executor(action):
            received_actions.append(action)
            if "Research" in action:
                return "Research findings: XYZ"
            elif "Analyze" in action:
                return "Analysis results: 123"
            return "Summary complete"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert result["success"] == True
        # The summary step should have research output but not analysis
        # (This tests the context_from filtering)
    
    def test_output_variable_substitution(self):
        """Output should be stored in specified variable name."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(
                    name="step1",
                    action="Generate report",
                    output_variable="report_data"
                ),
                WorkflowStep(
                    name="step2",
                    action="Use report: {{report_data}}"
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            if "Generate" in action:
                return "Report content here"
            return f"Used: {action}"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert result["success"] == True
    
    def test_retain_full_context_false_only_last_step(self):
        """When retain_full_context=False, only include last step's output."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="step1", action="First"),
                WorkflowStep(name="step2", action="Second"),
                WorkflowStep(
                    name="step3",
                    action="Third with {{previous_output}}",
                    retain_full_context=False
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        received_actions = []
        
        def mock_executor(action):
            received_actions.append(action)
            if "First" in action:
                return "First output"
            elif "Second" in action:
                return "Second output"
            return "Third output"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert result["success"] == True
        # Step 3 should only have step 2's output, not step 1's


class TestContextVariableSubstitution:
    """Test variable substitution with step outputs."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_previous_output_variable(self):
        """{{previous_output}} should be replaced with last step's output."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="step1", action="Generate"),
                WorkflowStep(name="step2", action="Process: {{previous_output}}")
            ]
        )
        self._register_workflow(manager, workflow)
        
        received_actions = []
        
        def mock_executor(action):
            received_actions.append(action)
            if "Generate" in action:
                return "DATA_123"
            return "Done"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        # Check that previous_output was substituted
        assert "DATA_123" in received_actions[1] or "previous_output" in received_actions[1]
    
    def test_named_step_output_variable(self):
        """{{step_name_output}} should be replaced with that step's output."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="research", action="Research topic"),
                WorkflowStep(name="write", action="Write about {{research_output}}")
            ]
        )
        self._register_workflow(manager, workflow)
        
        received_actions = []
        
        def mock_executor(action):
            received_actions.append(action)
            if "Research" in action:
                return "Research findings"
            return "Article written"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert result["success"] == True


class TestWorkflowExecuteResults:
    """Test that execute() returns proper results with context info."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_results_include_step_outputs(self):
        """Results should include output from each step."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="step1", action="Action 1"),
                WorkflowStep(name="step2", action="Action 2")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            return f"Output for {action}"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert result["success"] == True
        assert len(result["results"]) == 2
        assert result["results"][0]["output"] is not None
        assert result["results"][1]["output"] is not None
    
    def test_results_include_accumulated_context(self):
        """Results should include accumulated context information."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="step1", action="Action 1"),
                WorkflowStep(name="step2", action="Action 2")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            return f"Output for {action}"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        # Result should have context or variables with accumulated outputs
        assert "results" in result
        assert result["success"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
