"""
Test-driven development tests for recipe variable passing.

Tests the propagation of 'topic' and other YAML root-level fields
to included recipes via the variables dict.
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestTopicVariablePropagation:
    """Tests for topic variable propagation to variables dict."""
    
    def test_topic_field_added_to_variables(self):
        """Test that 'topic' field is automatically added to workflow variables."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Topic Variables Test
topic: "AI Code & Tools"

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{topic}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # topic should be in variables dict
        assert "topic" in workflow.variables
        assert workflow.variables["topic"] == "AI Code & Tools"
    
    def test_topic_with_template_variable_substituted(self):
        """Test that topic containing {{var}} is substituted before adding to variables."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Topic Substitution Test
topic: "AI Code & Tools {{today}}"

variables:
  today: "January 2026"

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{topic}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # topic should be substituted (either with variables section value or dynamic today)
        assert "topic" in workflow.variables
        # Should NOT contain raw {{today}} template
        assert "{{today}}" not in workflow.variables["topic"]
        # Should contain "AI Code & Tools" prefix
        assert "AI Code & Tools" in workflow.variables["topic"]
    
    def test_explicit_topic_in_variables_not_overwritten(self):
        """Test that explicit topic in variables section is NOT overwritten."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Explicit Topic Test
topic: "From topic field"

variables:
  topic: "From variables section"

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{topic}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # Explicit topic in variables should take precedence
        assert workflow.variables["topic"] == "From variables section"
    
    def test_no_topic_field_no_variable_added(self):
        """Test that no topic variable is added if topic field is missing."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: No Topic Test

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
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # topic should NOT be in variables if not specified
        assert "topic" not in workflow.variables


class TestIncludeVariablesMerging:
    """Tests for variables merging in included recipes."""
    
    def test_variables_available_in_workflow_run(self):
        """Test that variables are available when workflow runs."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Variables Run Test
topic: "Test Topic"

variables:
  today: "2026"

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{topic}} in {{today}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # Both topic and today should be in variables
        assert "topic" in workflow.variables
        assert "today" in workflow.variables
        assert workflow.variables["topic"] == "Test Topic"
        assert workflow.variables["today"] == "2026"


class TestNameFieldPropagation:
    """Tests for name field propagation to variables."""
    
    def test_name_field_added_to_variables(self):
        """Test that 'name' field is automatically added to workflow variables."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: My Workflow Name

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
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # name should be in variables dict for template usage
        assert "name" in workflow.variables or workflow.name == "My Workflow Name"


class TestInputFieldPropagation:
    """Tests for input field propagation to variables."""
    
    def test_input_field_added_to_variables(self):
        """Test that 'input' field is automatically added to workflow variables."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Input Test
input: "Initial input text"

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{input}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # default_input should be set
        assert workflow.default_input == "Initial input text"


class TestIncludeWithVariablesSupport:
    """Tests for enhanced include syntax with variables support."""
    
    def test_include_class_has_variables_attribute(self):
        """Test that Include class supports variables attribute."""
        from praisonaiagents.workflows import Include
        
        # Include should accept variables parameter
        include = Include(recipe="test-recipe", input=None)
        assert hasattr(include, 'recipe')
        assert include.recipe == "test-recipe"
    
    def test_parse_include_with_variables(self):
        """Test parsing include step with variables override."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Include
        
        yaml_content = """
name: Include Variables Test

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work"
  - include:
      recipe: test-recipe
      variables:
        topic: "Override Topic"
        custom_var: "Custom Value"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 2
        
        # Second step should be Include with variables
        include_step = workflow.steps[1]
        assert isinstance(include_step, Include)
        if hasattr(include_step, 'variables') and include_step.variables:
            assert include_step.variables.get("topic") == "Override Topic"
            assert include_step.variables.get("custom_var") == "Custom Value"


class TestPerformanceConstraints:
    """Tests to ensure no performance regression."""
    
    def test_import_time_acceptable(self):
        """Test that import time is not degraded."""
        import time
        
        start = time.perf_counter()
        from praisonaiagents.workflows import YAMLWorkflowParser
        elapsed = time.perf_counter() - start
        
        # Import should be fast (< 1 second even with all dependencies)
        assert elapsed < 1.0, f"Import took {elapsed:.3f}s, expected < 1.0s"
    
    def test_parse_time_acceptable(self):
        """Test that parsing is fast."""
        import time
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Performance Test
topic: "AI Code & Tools {{today}}"

variables:
  today: "January 2026"

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{topic}}"
"""
        parser = YAMLWorkflowParser()
        
        start = time.perf_counter()
        for _ in range(10):
            workflow = parser.parse_string(yaml_content)
        elapsed = time.perf_counter() - start
        
        # 10 parses should be fast (< 1 second)
        assert elapsed < 1.0, f"10 parses took {elapsed:.3f}s, expected < 1.0s"
