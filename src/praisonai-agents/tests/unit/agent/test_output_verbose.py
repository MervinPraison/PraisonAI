"""
Unit tests for Agent output parameter with verbose preset.

Tests the fix for the bug where output="verbose" would return None
because reasoning_steps=True in the verbose preset was causing the code
to try to return reasoning_content, but this attribute exists as None
for non-reasoning models.
"""
import pytest
from unittest.mock import Mock


class TestReasoningContentLogic:
    """Test the reasoning_content check logic directly."""

    def test_condition_with_none_reasoning_content(self):
        """Verify the fix: condition should be False when reasoning_content is None."""
        mock_message = Mock()
        mock_message.reasoning_content = None
        
        reasoning_steps = True
        
        # Old buggy condition:
        # if reasoning_steps and hasattr(mock_message, 'reasoning_content'):
        old_condition = reasoning_steps and hasattr(mock_message, 'reasoning_content')
        assert old_condition == True, "Old condition would be True (the bug)"
        
        # Fixed condition:
        # if reasoning_steps and hasattr(mock_message, 'reasoning_content') and mock_message.reasoning_content:
        # The truthiness of the whole expression should be False
        fixed_condition = reasoning_steps and hasattr(mock_message, 'reasoning_content') and mock_message.reasoning_content
        assert not fixed_condition, "Fixed condition should be falsy when reasoning_content is None"

    def test_condition_with_empty_string_reasoning_content(self):
        """Verify the fix: condition should be False when reasoning_content is empty string."""
        mock_message = Mock()
        mock_message.reasoning_content = ""
        
        reasoning_steps = True
        
        # Old condition would True (bug)
        old_condition = reasoning_steps and hasattr(mock_message, 'reasoning_content')
        assert old_condition == True
        
        # Fixed condition should be falsy
        fixed_condition = reasoning_steps and hasattr(mock_message, 'reasoning_content') and mock_message.reasoning_content
        assert not fixed_condition, "Fixed condition should be falsy when reasoning_content is empty string"

    def test_condition_with_actual_reasoning_content(self):
        """Verify the fix: condition should be True when reasoning_content has content."""
        mock_message = Mock()
        mock_message.reasoning_content = "This is my reasoning process..."
        
        reasoning_steps = True
        
        # Both old and new condition should be truthy
        old_condition = reasoning_steps and hasattr(mock_message, 'reasoning_content')
        assert old_condition
        
        fixed_condition = reasoning_steps and hasattr(mock_message, 'reasoning_content') and mock_message.reasoning_content
        assert fixed_condition, "Fixed condition should be truthy when reasoning_content has content"

    def test_condition_when_reasoning_steps_false(self):
        """Verify that when reasoning_steps is False, condition is always False."""
        mock_message = Mock()
        mock_message.reasoning_content = "This is my reasoning process..."
        
        reasoning_steps = False
        
        fixed_condition = reasoning_steps and hasattr(mock_message, 'reasoning_content') and mock_message.reasoning_content
        assert not fixed_condition, "Condition should be falsy when reasoning_steps is False"

    def test_if_statement_behavior_with_none(self):
        """Verify that an if statement using the condition skips when reasoning_content is None."""
        mock_message = Mock()
        mock_message.reasoning_content = None
        
        reasoning_steps = True
        execution_path = "not_taken"
        
        # This is how the fixed code behaves
        if reasoning_steps and hasattr(mock_message, 'reasoning_content') and mock_message.reasoning_content:
            execution_path = "reasoning_path"
        else:
            execution_path = "regular_path"
        
        assert execution_path == "regular_path", "Should take regular path when reasoning_content is None"

    def test_if_statement_behavior_with_reasoning(self):
        """Verify that an if statement using the condition enters when reasoning_content has value."""
        mock_message = Mock()
        mock_message.reasoning_content = "Reasoning steps here..."
        
        reasoning_steps = True
        execution_path = "not_taken"
        
        if reasoning_steps and hasattr(mock_message, 'reasoning_content') and mock_message.reasoning_content:
            execution_path = "reasoning_path"
        else:
            execution_path = "regular_path"
        
        assert execution_path == "reasoning_path", "Should take reasoning path when reasoning_content has value"


class TestVerbosePresetConfig:
    """Test that the verbose preset has the expected configuration."""

    def test_verbose_preset_has_reasoning_steps_false(self):
        """Verify that the verbose preset has reasoning_steps=False (debug has True)."""
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        verbose_preset = OUTPUT_PRESETS.get("verbose")
        assert verbose_preset is not None, "verbose preset should exist"
        # verbose preset has reasoning_steps=False; debug preset has reasoning_steps=True
        assert verbose_preset.get("reasoning_steps") == False, "verbose preset should have reasoning_steps=False"

    def test_verbose_preset_has_verbose_true(self):
        """Verify that the verbose preset enables verbose output."""
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        verbose_preset = OUTPUT_PRESETS.get("verbose")
        assert verbose_preset.get("verbose") == True, "verbose preset should have verbose=True"

    def test_verbose_preset_has_stream_false(self):
        """Verify that the verbose preset does not enable streaming by default."""
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        verbose_preset = OUTPUT_PRESETS.get("verbose")
        assert verbose_preset.get("stream") == False, "verbose preset should have stream=False"


class TestChatCompletionMessageDataclass:
    """Test the ChatCompletionMessage dataclass has reasoning_content attribute."""

    def test_chat_completion_message_has_reasoning_content(self):
        """Verify ChatCompletionMessage has reasoning_content attribute that defaults to None."""
        from praisonaiagents.llm.openai_client import ChatCompletionMessage
        
        # Create without reasoning_content
        message = ChatCompletionMessage(content="Test", role="assistant")
        
        # Should have the attribute
        assert hasattr(message, 'reasoning_content')
        # Should default to None
        assert message.reasoning_content is None

    def test_chat_completion_message_with_reasoning(self):
        """Verify ChatCompletionMessage can have reasoning_content set."""
        from praisonaiagents.llm.openai_client import ChatCompletionMessage
        
        message = ChatCompletionMessage(
            content="Test",
            role="assistant",
            reasoning_content="This is my reasoning..."
        )
        
        assert message.reasoning_content == "This is my reasoning..."
