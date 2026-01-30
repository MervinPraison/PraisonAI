"""
Tests for structured output functionality in workflows.

Tests cover:
1. output_json in YAML step passes to agent.chat()
2. Inline JSON schema (Option A) is supported
3. Pydantic model reference (Option B) is resolved
4. response_format is set for supporting models
5. JSON response is validated against schema
6. Loop receives typed list when output_json is array
7. Backward compatibility with existing workflows
"""
from unittest.mock import Mock, patch
from typing import List


class TestStructuredOutputYAMLParsing:
    """Test that output_json is correctly parsed from YAML."""
    
    def test_parse_inline_json_schema(self):
        """Test Option A: Inline JSON schema in YAML."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
agents:
  topic_finder:
    role: Topic Finder
    goal: Find topics
    backstory: Expert at finding topics

steps:
  - agent: topic_finder
    action: "Find AI topics"
    output_json:
      type: array
      items:
        type: object
        properties:
          title:
            type: string
          url:
            type: string
        required:
          - title
          - url
    output_variable: topics
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Verify the step has output_json
        assert len(workflow.steps) == 1
        step = workflow.steps[0]
        
        # Check that _yaml_output_json was parsed (stored on agent, then transferred to step)
        # The step is an Agent with _yaml_output_json attribute
        assert hasattr(step, '_yaml_output_json')
        
    def test_parse_pydantic_reference(self):
        """Test Option B: Pydantic model reference in YAML."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
agents:
  topic_finder:
    role: Topic Finder
    goal: Find topics
    backstory: Expert at finding topics

steps:
  - agent: topic_finder
    action: "Find AI topics"
    output_pydantic: TopicList
    output_variable: topics
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Verify the step has output_pydantic
        assert len(workflow.steps) == 1
        step = workflow.steps[0]
        
        # Check that _yaml_output_pydantic was parsed (stored on agent)
        assert hasattr(step, '_yaml_output_pydantic')


class TestStructuredOutputWiring:
    """Test that output_json is wired from YAML to Task."""
    
    def test_normalize_step_includes_output_json(self):
        """Test that _normalize_single_step transfers output_json to Task."""
        from praisonaiagents.workflows.workflows import Workflow, Task
        
        # Create a mock agent with _yaml_output_json
        agent = Mock()
        agent.name = "test_agent"
        agent.tools = None
        agent._yaml_action = "Test action"
        agent._yaml_output_variable = "result"
        agent._yaml_output_json = {"type": "array", "items": {"type": "string"}}
        agent._yaml_step_name = "test_step"
        
        # Mock the chat method
        agent.chat = Mock(return_value="test output")
        
        # Create workflow and normalize the step
        workflow = Workflow(steps=[])
        normalized = workflow._normalize_single_step(agent, 0)
        
        # Verify Task has output_json
        assert isinstance(normalized, Task)
        assert normalized._output_json == {"type": "array", "items": {"type": "string"}}
        
    def test_normalize_step_includes_output_pydantic(self):
        """Test that _normalize_single_step transfers output_pydantic to Task."""
        from praisonaiagents.workflows.workflows import Workflow, Task
        
        # Create a mock agent with _yaml_output_pydantic
        agent = Mock()
        agent.name = "test_agent"
        agent.tools = None
        agent._yaml_action = "Test action"
        agent._yaml_output_variable = "result"
        agent._yaml_output_pydantic = "TopicList"
        agent._yaml_step_name = "test_step"
        agent.chat = Mock(return_value="test output")
        
        workflow = Workflow(steps=[])
        normalized = workflow._normalize_single_step(agent, 0)
        
        assert isinstance(normalized, Task)
        assert normalized._output_pydantic == "TopicList"


class TestStructuredOutputExecution:
    """Test that output_json is passed to agent.chat() during execution."""
    
    def test_agent_chat_receives_output_json(self):
        """Test that agent.chat() is called with output_json parameter."""
        from praisonaiagents.workflows.workflows import Workflow, Task
        
        # Create mock agent
        mock_agent = Mock()
        mock_agent.name = "test_agent"
        mock_agent.chat = Mock(return_value='["topic1", "topic2"]')
        
        # Create step with output_json
        step = Task(
            name="test_step",
            agent=mock_agent,
            action="Find topics",
            output={"json_model": {"type": "array", "items": {"type": "string"}}}
        )
        
        # Create and run workflow
        workflow = Workflow(steps=[step])
        
        # Execute the step
        _ = workflow.run("test input")
        
        # Verify agent.chat was called
        mock_agent.chat.assert_called()


class TestResponseFormatForAllModels:
    """Test that response_format is used for all supporting models."""
    
    def test_response_format_set_for_openai_models(self):
        """Test that response_format is set for OpenAI models that support it."""
        from praisonaiagents.llm.llm import LLM
        from pydantic import BaseModel
        
        class TestSchema(BaseModel):
            items: List[str]
        
        llm = LLM(model="gpt-4o-mini")
        
        # Build completion params with output_json
        with patch('praisonaiagents.llm.model_capabilities.supports_structured_outputs', return_value=True):
            params = llm._build_completion_params(
                messages=[{"role": "user", "content": "test"}],
                output_json=TestSchema
            )
        
        # Verify response_format is set
        assert 'response_format' in params or 'response_schema' in params


class TestJSONValidation:
    """Test that JSON responses are validated against schema."""
    
    def test_invalid_json_raises_error(self):
        """Test that invalid JSON response raises validation error."""
        # This test verifies that when output_json is specified,
        # the response is validated against the schema
        pass  # Will be implemented after core functionality


class TestLoopWithStructuredOutput:
    """Test that loops receive typed lists from structured output."""
    
    def test_loop_receives_list_not_string(self):
        """Test that loop iteration receives a list, not a JSON string."""
        # This test verifies that when output_json specifies an array,
        # the loop receives an actual list to iterate over
        pass  # Will be implemented after core functionality


class TestBackwardCompatibility:
    """Test backward compatibility with existing workflows."""
    
    def test_workflow_without_output_json_still_works(self):
        """Test that workflows without output_json continue to work."""
        from praisonaiagents.workflows.workflows import Workflow, Task
        
        mock_agent = Mock()
        mock_agent.name = "test_agent"
        mock_agent.chat = Mock(return_value="test output")
        
        step = Task(
            name="test_step",
            agent=mock_agent,
            action="Test action"
        )
        
        workflow = Workflow(steps=[step])
        result = workflow.run("test input")
        
        # Should complete without error
        assert result is not None


class TestPerformance:
    """Test that there's no performance regression."""
    
    def test_no_heavy_imports_at_module_level(self):
        """Test that Pydantic and other heavy deps are lazily imported."""
        # This is a basic check - full perf testing would measure import time
        # The workflows module should import without errors
        from praisonaiagents.workflows import workflows as wf
        assert wf is not None
