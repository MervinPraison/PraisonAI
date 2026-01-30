"""
Unit tests for shared task execution utilities.

Tests the DRY utilities in utils/task_execution.py.
"""
import json
from praisonaiagents.utils.task_execution import (
    build_task_prompt,
    parse_task_output,
    check_multimodal_dependencies,
    get_multimodal_error_message,
)


class TestBuildTaskPrompt:
    """Tests for build_task_prompt utility."""
    
    def test_basic_prompt(self):
        """Test basic prompt building."""
        prompt = build_task_prompt(
            description="Research AI trends",
            expected_output="A summary of trends"
        )
        
        assert "Research AI trends" in prompt
        assert "A summary of trends" in prompt
        assert "Please provide only the final result" in prompt
    
    def test_with_context(self):
        """Test prompt with context results."""
        prompt = build_task_prompt(
            description="Write article",
            expected_output="Article text",
            context_results=["Previous research: AI is growing", "Market data: 50% growth"]
        )
        
        assert "Context:" in prompt
        assert "Previous research: AI is growing" in prompt
        assert "Market data: 50% growth" in prompt
    
    def test_with_memory_context(self):
        """Test prompt with memory context."""
        prompt = build_task_prompt(
            description="Continue writing",
            expected_output="Next chapter",
            memory_context="Previously discussed: character development"
        )
        
        assert "Previously discussed: character development" in prompt
    
    def test_with_variables(self):
        """Test variable substitution in description."""
        prompt = build_task_prompt(
            description="Research {{topic}} for {{year}}",
            expected_output="Report",
            variables={"topic": "AI agents", "year": "2025"}
        )
        
        assert "Research AI agents for 2025" in prompt
        assert "{{topic}}" not in prompt
        assert "{{year}}" not in prompt
    
    def test_deduplicates_context(self):
        """Test that duplicate context items are removed."""
        prompt = build_task_prompt(
            description="Task",
            expected_output="Output",
            context_results=["Same context", "Same context", "Different context"]
        )
        
        # Should only appear once
        assert prompt.count("Same context") == 1
        assert "Different context" in prompt


class TestParseTaskOutput:
    """Tests for parse_task_output utility."""
    
    def test_raw_output(self):
        """Test parsing raw output without JSON/Pydantic."""
        result = parse_task_output(
            agent_output="Just some text output",
            task_id=1
        )
        
        assert result["output_format"] == "RAW"
        assert result["json_dict"] is None
        assert result["pydantic"] is None
    
    def test_json_output(self):
        """Test parsing JSON output."""
        def clean_json(s):
            return s
        
        result = parse_task_output(
            agent_output='{"key": "value", "count": 42}',
            output_json=True,
            task_id=1,
            clean_json_fn=clean_json
        )
        
        assert result["output_format"] == "JSON"
        assert result["json_dict"] == {"key": "value", "count": 42}
    
    def test_invalid_json_output(self):
        """Test handling invalid JSON gracefully."""
        def clean_json(s):
            return s
        
        result = parse_task_output(
            agent_output="not valid json",
            output_json=True,
            task_id=1,
            clean_json_fn=clean_json
        )
        
        # Should fall back to RAW
        assert result["output_format"] == "RAW"
        assert result["json_dict"] is None
    
    def test_pydantic_output(self):
        """Test parsing Pydantic output."""
        from pydantic import BaseModel
        
        class TestModel(BaseModel):
            name: str
            value: int
        
        def clean_json(s):
            return s
        
        result = parse_task_output(
            agent_output='{"name": "test", "value": 123}',
            output_pydantic=TestModel,
            task_id=1,
            clean_json_fn=clean_json
        )
        
        assert result["output_format"] == "Pydantic"
        assert result["pydantic"].name == "test"
        assert result["pydantic"].value == 123


class TestMultimodalHelpers:
    """Tests for multimodal dependency helpers."""
    
    def test_multimodal_error_message(self):
        """Test error message content."""
        msg = get_multimodal_error_message()
        
        assert "pip install" in msg
        assert "opencv-python" in msg
        assert "moviepy" in msg
    
    def test_check_multimodal_returns_bool(self):
        """Test that check returns boolean."""
        result = check_multimodal_dependencies()
        
        assert isinstance(result, bool)
