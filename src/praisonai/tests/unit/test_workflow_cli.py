"""
Unit tests for Workflow CLI commands.

Tests the WorkflowHandler CLI feature for YAML workflow management.
"""

import os
import tempfile


class TestWorkflowHandler:
    """Tests for WorkflowHandler CLI feature."""
    
    def test_workflow_handler_import(self):
        """Test that WorkflowHandler can be imported."""
        from praisonai.cli.features import WorkflowHandler
        assert WorkflowHandler is not None
    
    def test_workflow_handler_initialization(self):
        """Test WorkflowHandler initialization."""
        from praisonai.cli.features.workflow import WorkflowHandler
        handler = WorkflowHandler(verbose=True)
        assert handler.feature_name == "workflow"
    
    def test_workflow_get_actions(self):
        """Test getting available actions."""
        from praisonai.cli.features.workflow import WorkflowHandler
        handler = WorkflowHandler()
        actions = handler.get_actions()
        assert "run" in actions
        assert "validate" in actions
        assert "list" in actions
        assert "create" in actions
    
    def test_workflow_templates_exist(self):
        """Test that workflow templates are defined."""
        from praisonai.cli.features.workflow import WorkflowHandler
        handler = WorkflowHandler()
        assert "simple" in handler.TEMPLATES
        assert "routing" in handler.TEMPLATES
        assert "parallel" in handler.TEMPLATES
        assert "loop" in handler.TEMPLATES
        assert "evaluator-optimizer" in handler.TEMPLATES
    
    def test_workflow_create_template(self):
        """Test creating a workflow from template."""
        from praisonai.cli.features.workflow import WorkflowHandler
        handler = WorkflowHandler()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test_workflow.yaml")
            result = handler.action_create(
                ["--template", "simple", "--output", output_file]
            )
            
            assert result == output_file
            assert os.path.exists(output_file)
            
            # Check content
            with open(output_file, 'r') as f:
                content = f.read()
            assert "name: Simple Workflow" in content
            assert "agents:" in content
            assert "steps:" in content
    
    def test_workflow_validate(self):
        """Test validating a YAML workflow."""
        from praisonai.cli.features.workflow import WorkflowHandler
        handler = WorkflowHandler()
        
        yaml_content = """
name: Test Workflow
agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            result = handler.action_validate([temp_path])
            assert result == True
        finally:
            os.unlink(temp_path)
    
    def test_workflow_validate_invalid_file(self):
        """Test validating a non-existent file."""
        from praisonai.cli.features.workflow import WorkflowHandler
        handler = WorkflowHandler()
        
        result = handler.action_validate(["nonexistent.yaml"])
        assert result == False
    
    def test_workflow_help_text(self):
        """Test help text contains expected commands."""
        from praisonai.cli.features.workflow import WorkflowHandler
        handler = WorkflowHandler()
        help_text = handler.get_help_text()
        
        assert "run" in help_text
        assert "validate" in help_text
        assert "list" in help_text
        assert "create" in help_text
        assert "template" in help_text
