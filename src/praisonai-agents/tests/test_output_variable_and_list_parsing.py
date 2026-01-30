"""
TDD tests for output_variable parsing and list parsing in loops.

Tests for:
1. output_variable parsing from YAML steps
2. JSON list parsing when loop iterates over string variable
3. Regex extraction of lists from agent text output
4. Dynamic parallel execution based on list size
"""

import pytest
import json


class TestOutputVariableParsing:
    """Tests for output_variable parsing from YAML."""
    
    def test_output_variable_parsed_from_yaml_step(self):
        """Test that output_variable is parsed from YAML step definition."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = '''
agents:
  topic_finder:
    role: Topic Finder
    goal: Find topics
    
steps:
  - name: find_topics
    agent: topic_finder
    action: "Find 5 topics"
    output_variable: my_topics
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # The agent should have _yaml_output_variable set
        assert workflow is not None
        assert len(workflow.steps) > 0
        
        # Check that the agent has the output_variable attribute
        step = workflow.steps[0]
        output_var = getattr(step, '_yaml_output_variable', None)
        assert output_var == 'my_topics', f"Expected 'my_topics', got {output_var}"
    
    def test_output_variable_used_in_workflow_execution(self):
        """Test that output_variable stores output in the specified variable name."""
        from praisonaiagents.workflows import Task
        
        # Create a simple workflow step with output_variable
        step = Task(
            name="test_step",
            action="Return a list",
            output={"variable": "custom_var"}
        )
        
        # Verify the output_variable is set
        assert step.output_variable == "custom_var"


class TestListParsingInLoop:
    """Tests for parsing lists from string variables in loops."""
    
    def test_json_array_string_parsed_as_list(self):
        """Test that a JSON array string is parsed into a Python list."""
        # Simulate what _execute_loop should do
        json_string = '["topic1", "topic2", "topic3"]'
        
        # Current behavior (wrong): wraps string as single item
        # Expected behavior: parse JSON and get list
        try:
            parsed = json.loads(json_string)
            assert isinstance(parsed, list)
            assert len(parsed) == 3
            assert parsed == ["topic1", "topic2", "topic3"]
        except json.JSONDecodeError:
            pytest.fail("Should parse valid JSON array")
    
    def test_extract_json_array_from_text(self):
        """Test extracting JSON array from text that contains other content."""
        import re
        
        text_with_list = '''
Here are the unique topics I found:
UNIQUE_TOPICS: ["AI Agents", "Machine Learning", "Neural Networks"]

These topics are trending this week.
'''
        # Extract JSON array using regex
        pattern = r'\[(?:[^\[\]]*(?:"[^"]*")?[^\[\]]*)*\]'
        matches = re.findall(pattern, text_with_list)
        
        assert len(matches) > 0, "Should find at least one array pattern"
        
        # Try to parse the first match as JSON
        for match in matches:
            try:
                parsed = json.loads(match)
                if isinstance(parsed, list) and len(parsed) > 0:
                    assert parsed == ["AI Agents", "Machine Learning", "Neural Networks"]
                    return
            except json.JSONDecodeError:
                continue
        
        pytest.fail("Should extract and parse the JSON array from text")
    
    def test_loop_over_variable_parses_json_list(self):
        """Test that loop over a string variable containing JSON list works."""
        from praisonaiagents.workflows import Loop
        
        # Create a loop that iterates over a variable
        def dummy_step(ctx):
            return {"output": "done"}
        
        loop_step = Loop(
            step=dummy_step,
            over="topics",
            parallel=True
        )
        
        # The variable contains a JSON string
        variables = {
            "topics": '["topic1", "topic2", "topic3"]'
        }
        
        # Get items - this is what _execute_loop does
        items = variables.get(loop_step.over, [])
        
        # Current behavior: if string, wrap as single item
        # We need to add JSON parsing
        if isinstance(items, str):
            try:
                parsed = json.loads(items)
                if isinstance(parsed, list):
                    items = parsed
            except json.JSONDecodeError:
                items = [items]
        
        assert isinstance(items, list)
        assert len(items) == 3
        assert items == ["topic1", "topic2", "topic3"]


class TestDynamicParallelism:
    """Tests for dynamic parallel execution based on list size."""
    
    def test_parallel_workers_match_list_size(self):
        """Test that parallel workers default to list size."""
        from praisonaiagents.workflows import Loop
        
        # Create a parallel loop without max_workers
        def dummy_step(ctx):
            return {"output": "done"}
        
        loop_step = Loop(
            step=dummy_step,
            over="items",
            parallel=True,
            max_workers=None  # Should default to num_items
        )
        
        # Simulate items
        items = ["a", "b", "c", "d", "e"]
        num_items = len(items)
        
        # Calculate max_workers as _execute_loop does
        max_workers = loop_step.max_workers or num_items
        
        assert max_workers == 5, "max_workers should equal list size when not specified"
    
    def test_max_workers_caps_parallelism(self):
        """Test that max_workers caps the number of parallel workers."""
        from praisonaiagents.workflows import Loop
        
        def dummy_step(ctx):
            return {"output": "done"}
        
        loop_step = Loop(
            step=dummy_step,
            over="items",
            parallel=True,
            max_workers=2  # Cap at 2
        )
        
        items = ["a", "b", "c", "d", "e"]
        num_items = len(items)
        
        max_workers = loop_step.max_workers or num_items
        
        assert max_workers == 2, "max_workers should be capped at specified value"


class TestParseListFromString:
    """Tests for the _parse_list_from_string method in Workflow."""
    
    def test_parse_pure_json_array(self):
        """Test parsing a pure JSON array string."""
        from praisonaiagents.workflows import Workflow
        
        workflow = Workflow(steps=[])
        result = workflow._parse_list_from_string('["topic1", "topic2", "topic3"]')
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result == ["topic1", "topic2", "topic3"]
    
    def test_parse_json_array_from_text(self):
        """Test extracting JSON array from text with other content."""
        from praisonaiagents.workflows import Workflow
        
        workflow = Workflow(steps=[])
        text = '''
Here are the unique topics I found:
UNIQUE_TOPICS: ["AI Agents", "Machine Learning", "Neural Networks"]

These topics are trending this week.
'''
        result = workflow._parse_list_from_string(text)
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result == ["AI Agents", "Machine Learning", "Neural Networks"]
    
    def test_parse_empty_string_returns_empty_list(self):
        """Test that empty string returns empty list."""
        from praisonaiagents.workflows import Workflow
        
        workflow = Workflow(steps=[])
        result = workflow._parse_list_from_string('')
        
        assert result == []
    
    def test_parse_non_list_string_wraps_as_single_item(self):
        """Test that non-list string is wrapped as single item."""
        from praisonaiagents.workflows import Workflow
        
        workflow = Workflow(steps=[])
        result = workflow._parse_list_from_string('just a plain string')
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result == ['just a plain string']


class TestBeginnerFriendlyYAML:
    """Tests for beginner-friendly YAML syntax."""
    
    def test_simple_parallel_loop_syntax(self):
        """Test that simple parallel loop syntax works."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Loop
        
        yaml_content = '''
agents:
  researcher:
    role: Researcher
    goal: Research topics
    
steps:
  # Step 1: Find topics (output stored in topics variable)
  - name: find_topics
    agent: researcher
    action: "Find 3 topics and return as JSON array"
    output_variable: topics
    
  # Step 2: Process each topic in parallel
  - loop:
      over: topics
      parallel: true
    agent: researcher
    action: "Research this topic: {{item}}"
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) >= 2
        
        # Second step should be a Loop
        loop_found = False
        for step in workflow.steps:
            if isinstance(step, Loop):
                assert step.parallel is True
                assert step.over == "topics"
                loop_found = True
                break
        
        assert loop_found, "Should have a parallel loop step"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
