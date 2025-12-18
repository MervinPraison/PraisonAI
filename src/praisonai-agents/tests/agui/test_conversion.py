"""
Test AG-UI Message Conversion - TDD Tests for Message Format Conversion

Phase 3: Message Conversion Tests
- Test converting AG-UI messages to PraisonAI format
- Test converting PraisonAI messages to AG-UI format
- Test handling of tool calls
- Test handling of tool results
- Test edge cases (empty messages, missing fields)
"""

class TestAGUIToPraisonAIConversion:
    """Test converting AG-UI messages to PraisonAI format."""
    
    def test_convert_user_message(self):
        """Test converting a user message."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        from praisonaiagents.ui.agui.types import Message
        
        agui_messages = [Message(role="user", content="Hello")]
        result = agui_messages_to_praisonai(agui_messages)
        
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"
    
    def test_convert_assistant_message(self):
        """Test converting an assistant message."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        from praisonaiagents.ui.agui.types import Message
        
        agui_messages = [Message(role="assistant", content="Hi there!")]
        result = agui_messages_to_praisonai(agui_messages)
        
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Hi there!"
    
    def test_convert_tool_message(self):
        """Test converting a tool result message."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        from praisonaiagents.ui.agui.types import Message
        
        agui_messages = [Message(role="tool", content="Search results", tool_call_id="tc-123")]
        result = agui_messages_to_praisonai(agui_messages)
        
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == "Search results"
        assert result[0]["tool_call_id"] == "tc-123"
    
    def test_convert_assistant_with_tool_calls(self):
        """Test converting assistant message with tool calls."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        from praisonaiagents.ui.agui.types import Message, ToolCall, FunctionCall
        
        agui_messages = [
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc-123",
                        function=FunctionCall(name="search", arguments='{"query": "test"}')
                    )
                ]
            )
        ]
        result = agui_messages_to_praisonai(agui_messages)
        
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert "tool_calls" in result[0]
        assert len(result[0]["tool_calls"]) == 1
        assert result[0]["tool_calls"][0]["function"]["name"] == "search"
    
    def test_convert_multiple_messages(self):
        """Test converting multiple messages."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        from praisonaiagents.ui.agui.types import Message
        
        agui_messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi!"),
            Message(role="user", content="How are you?"),
        ]
        result = agui_messages_to_praisonai(agui_messages)
        
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"
    
    def test_convert_empty_messages(self):
        """Test converting empty message list."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        
        result = agui_messages_to_praisonai([])
        assert result == []
    
    def test_skip_system_messages(self):
        """Test that system messages are skipped (agent builds its own)."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        from praisonaiagents.ui.agui.types import Message
        
        agui_messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ]
        result = agui_messages_to_praisonai(agui_messages)
        
        # System message should be skipped
        assert len(result) == 1
        assert result[0]["role"] == "user"


class TestPraisonAIToAGUIConversion:
    """Test converting PraisonAI messages to AG-UI format."""
    
    def test_convert_user_message(self):
        """Test converting a user message."""
        from praisonaiagents.ui.agui.conversion import praisonai_messages_to_agui
        
        praison_messages = [{"role": "user", "content": "Hello"}]
        result = praisonai_messages_to_agui(praison_messages)
        
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "Hello"
    
    def test_convert_assistant_message(self):
        """Test converting an assistant message."""
        from praisonaiagents.ui.agui.conversion import praisonai_messages_to_agui
        
        praison_messages = [{"role": "assistant", "content": "Hi there!"}]
        result = praisonai_messages_to_agui(praison_messages)
        
        assert len(result) == 1
        assert result[0].role == "assistant"
        assert result[0].content == "Hi there!"
    
    def test_convert_tool_result(self):
        """Test converting a tool result message."""
        from praisonaiagents.ui.agui.conversion import praisonai_messages_to_agui
        
        praison_messages = [
            {"role": "tool", "content": "Search results", "tool_call_id": "tc-123"}
        ]
        result = praisonai_messages_to_agui(praison_messages)
        
        assert len(result) == 1
        assert result[0].role == "tool"
        assert result[0].content == "Search results"
        assert result[0].tool_call_id == "tc-123"
    
    def test_convert_assistant_with_tool_calls(self):
        """Test converting assistant message with tool calls."""
        from praisonaiagents.ui.agui.conversion import praisonai_messages_to_agui
        
        praison_messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc-123",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "test"}'
                        }
                    }
                ]
            }
        ]
        result = praisonai_messages_to_agui(praison_messages)
        
        assert len(result) == 1
        assert result[0].role == "assistant"
        assert result[0].tool_calls is not None
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0].function.name == "search"
    
    def test_convert_empty_messages(self):
        """Test converting empty message list."""
        from praisonaiagents.ui.agui.conversion import praisonai_messages_to_agui
        
        result = praisonai_messages_to_agui([])
        assert result == []


class TestStateConversion:
    """Test state conversion utilities."""
    
    def test_validate_dict_state(self):
        """Test validating dict state."""
        from praisonaiagents.ui.agui.conversion import validate_state
        
        state = {"key": "value"}
        result = validate_state(state, "thread-123")
        
        assert result == {"key": "value"}
    
    def test_validate_none_state(self):
        """Test validating None state."""
        from praisonaiagents.ui.agui.conversion import validate_state
        
        result = validate_state(None, "thread-123")
        assert result is None
    
    def test_validate_pydantic_state(self):
        """Test validating Pydantic model state."""
        from praisonaiagents.ui.agui.conversion import validate_state
        from pydantic import BaseModel
        
        class TestState(BaseModel):
            key: str = "value"
        
        state = TestState()
        result = validate_state(state, "thread-123")
        
        assert result == {"key": "value"}
    
    def test_validate_invalid_state_returns_none(self):
        """Test that invalid state returns None."""
        from praisonaiagents.ui.agui.conversion import validate_state
        
        # A string is not a valid state
        result = validate_state("invalid", "thread-123")
        assert result is None


class TestToolCallDeduplication:
    """Test tool call deduplication logic."""
    
    def test_deduplicate_tool_results(self):
        """Test that duplicate tool results are deduplicated."""
        from praisonaiagents.ui.agui.conversion import agui_messages_to_praisonai
        from praisonaiagents.ui.agui.types import Message
        
        # Same tool_call_id appearing twice
        agui_messages = [
            Message(role="tool", content="Result 1", tool_call_id="tc-123"),
            Message(role="tool", content="Result 2", tool_call_id="tc-123"),  # Duplicate
        ]
        result = agui_messages_to_praisonai(agui_messages)
        
        # Should only have one result
        assert len(result) == 1
        assert result[0]["content"] == "Result 1"  # First one wins


class TestExtractUserInput:
    """Test extracting user input from messages."""
    
    def test_extract_last_user_message(self):
        """Test extracting the last user message."""
        from praisonaiagents.ui.agui.conversion import extract_user_input
        from praisonaiagents.ui.agui.types import Message
        
        messages = [
            Message(role="user", content="First message"),
            Message(role="assistant", content="Response"),
            Message(role="user", content="Last message"),
        ]
        result = extract_user_input(messages)
        
        assert result == "Last message"
    
    def test_extract_from_empty_messages(self):
        """Test extracting from empty messages."""
        from praisonaiagents.ui.agui.conversion import extract_user_input
        
        result = extract_user_input([])
        assert result == ""
    
    def test_extract_no_user_messages(self):
        """Test extracting when no user messages exist."""
        from praisonaiagents.ui.agui.conversion import extract_user_input
        from praisonaiagents.ui.agui.types import Message
        
        messages = [
            Message(role="assistant", content="Hello"),
        ]
        result = extract_user_input(messages)
        
        assert result == ""
