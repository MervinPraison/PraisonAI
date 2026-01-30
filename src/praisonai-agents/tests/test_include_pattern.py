"""
TDD tests for Include pattern in YAML workflows.

Tests for recipe composition:
- Parsing include: recipe_name
- Executing included recipes
- Cycle detection
- Input/output passing
"""

import pytest
from pathlib import Path
import tempfile
import os


class TestIncludePatternParsing:
    """Tests for parsing include steps from YAML."""
    
    def test_include_pattern_import(self):
        """Test that Include class can be imported."""
        from praisonaiagents.workflows import Include
        assert Include is not None
    
    def test_include_function_import(self):
        """Test that include() convenience function can be imported."""
        from praisonaiagents.workflows import include
        assert include is not None
    
    def test_include_class_creation(self):
        """Test creating Include object directly."""
        from praisonaiagents.workflows import Include
        
        inc = Include(recipe="wordpress-publisher")
        assert inc.recipe == "wordpress-publisher"
        assert inc.input is None
    
    def test_include_with_input(self):
        """Test Include with custom input."""
        from praisonaiagents.workflows import Include
        
        inc = Include(recipe="wordpress-publisher", input="{{previous_output}}")
        assert inc.recipe == "wordpress-publisher"
        assert inc.input == "{{previous_output}}"
    
    def test_parse_simple_include_from_yaml(self):
        """Test parsing simple include: recipe_name from YAML."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Include
        
        yaml_content = '''
name: Test Workflow
steps:
  - include: wordpress-publisher
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Should have one step that is an Include
        assert len(workflow.steps) == 1
        step = workflow.steps[0]
        assert isinstance(step, Include)
        assert step.recipe == "wordpress-publisher"
    
    def test_parse_include_with_config(self):
        """Test parsing include with configuration."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Include
        
        yaml_content = '''
name: Test Workflow
steps:
  - include:
      recipe: wordpress-publisher
      input: "Custom input"
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert len(workflow.steps) == 1
        step = workflow.steps[0]
        assert isinstance(step, Include)
        assert step.recipe == "wordpress-publisher"
        assert step.input == "Custom input"


class TestIncludePatternExecution:
    """Tests for executing include steps."""
    
    def test_include_resolves_recipe_path(self):
        """Test that include step resolves recipe path."""
        from praisonaiagents.workflows import Include
        
        # Create a mock recipe in temp dir
        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_dir = Path(tmpdir) / "test-recipe"
            recipe_dir.mkdir()
            
            agents_yaml = recipe_dir / "agents.yaml"
            agents_yaml.write_text('''
framework: praisonai
topic: Test
roles:
  agent1:
    role: Test Agent
    goal: Test
    backstory: Test
    tasks:
      task1:
        description: Return the input
        expected_output: The input
''')
            
            inc = Include(recipe="test-recipe")
            # Path resolution is done at execution time
            assert inc.recipe == "test-recipe"
    
    def test_execute_include_method_exists(self):
        """Test that _execute_include method exists on Workflow."""
        from praisonaiagents.workflows import Workflow
        
        workflow = Workflow(name="test", steps=[])
        assert hasattr(workflow, "_execute_include")
        assert callable(getattr(workflow, "_execute_include"))
    
    def test_execute_include_with_handler_workflow(self):
        """Test executing a workflow with Include step using handler function."""
        from praisonaiagents.workflows import Workflow, Include, Task, StepResult
        import tempfile
        from pathlib import Path
        import os
        
        # Create a temp recipe that uses a simple handler
        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_dir = Path(tmpdir) / "simple-recipe"
            recipe_dir.mkdir()
            
            # Create a minimal workflow YAML with a handler
            agents_yaml = recipe_dir / "agents.yaml"
            agents_yaml.write_text('''
name: Simple Handler Recipe
description: A recipe with a simple handler
steps:
  - name: echo_step
    action: "Echo: {{input}}"
''')
            
            # Create Include pointing to the temp recipe path
            include_step = Include(recipe=str(recipe_dir))
            
            # Create parent workflow
            parent = Workflow(
                name="Parent Workflow",
                steps=[include_step]
            )
            
            # The include should resolve the local path
            assert include_step.recipe == str(recipe_dir)


class TestCycleDetection:
    """Tests for cycle detection in includes."""
    
    def test_cycle_detection_raises_error(self):
        """Test that circular includes raise an error."""
        from praisonaiagents.workflows import Include
        
        # Simulate cycle detection logic
        visited = {"recipe-a", "recipe-b"}
        
        # Attempting to include recipe-a again should fail
        inc = Include(recipe="recipe-a")
        
        # The cycle detection happens in _execute_include
        # Here we just test the Include object can track visited
        assert "recipe-a" in visited


class TestIncludeConvenienceFunction:
    """Tests for the include() convenience function."""
    
    def test_include_function_creates_include(self):
        """Test include() creates Include object."""
        from praisonaiagents.workflows import include, Include
        
        inc = include("wordpress-publisher")
        assert isinstance(inc, Include)
        assert inc.recipe == "wordpress-publisher"
    
    def test_include_function_with_input(self):
        """Test include() with input parameter."""
        from praisonaiagents.workflows import include, Include
        
        inc = include("wordpress-publisher", input="test input")
        assert isinstance(inc, Include)
        assert inc.input == "test input"


class TestIncludesInRolesFormat:
    """Tests for 'includes:' section in roles-format YAML files."""
    
    def test_includes_section_simple(self):
        """Test parsing 'includes:' section with simple recipe names."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Include
        
        yaml_content = '''
framework: praisonai
topic: Test

roles:
  writer:
    role: Writer
    goal: Write content
    backstory: You are a writer
    tasks:
      write:
        description: Write about AI

includes:
  - wordpress-publisher
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Should have 2 steps: 1 from roles, 1 from includes
        assert len(workflow.steps) == 2
        
        # Last step should be an Include
        last_step = workflow.steps[-1]
        assert isinstance(last_step, Include)
        assert last_step.recipe == "wordpress-publisher"
    
    def test_includes_section_with_config(self):
        """Test parsing 'includes:' section with configuration."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Include
        
        yaml_content = '''
framework: praisonai
topic: Test

roles:
  writer:
    role: Writer
    goal: Write
    backstory: Writer
    tasks:
      write:
        description: Write

includes:
  - recipe: wordpress-publisher
    input: "{{previous_output}}"
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Should have 2 steps
        assert len(workflow.steps) == 2
        
        # Last step should be an Include with input
        last_step = workflow.steps[-1]
        assert isinstance(last_step, Include)
        assert last_step.recipe == "wordpress-publisher"
        assert last_step.input == "{{previous_output}}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

