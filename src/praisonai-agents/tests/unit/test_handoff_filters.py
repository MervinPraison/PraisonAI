"""
Unit tests for handoff filters including compress_history and filter chaining.

Tests:
1. compress_history filter - compresses messages into single summary
2. Filter list chaining - multiple filters applied in order
3. Existing filters (remove_all_tools, keep_last_n_messages, remove_system_messages)
"""

from praisonaiagents.agent.handoff import (
    HandoffInputData,
    handoff_filters,
)


class TestCompressHistoryFilter:
    """Tests for handoff_filters.compress_history"""
    
    def test_compress_history_basic(self):
        """Test basic compression of multiple messages into one."""
        data = HandoffInputData(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        result = handoff_filters.compress_history(data)
        
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "user"
        assert "Previous conversation summary:" in result.messages[0]["content"]
        assert "[user]: Hello" in result.messages[0]["content"]
        assert "[assistant]: Hi there!" in result.messages[0]["content"]
        assert "[user]: How are you?" in result.messages[0]["content"]
    
    def test_compress_history_empty(self):
        """Test compression with empty messages."""
        data = HandoffInputData(
            messages=[],
            context={},
            source_agent="test_agent",
        )
        
        result = handoff_filters.compress_history(data)
        
        assert len(result.messages) == 0
    
    def test_compress_history_single_message(self):
        """Test compression with single message."""
        data = HandoffInputData(
            messages=[{"role": "user", "content": "Single message"}],
            context={},
            source_agent="test_agent",
        )
        
        result = handoff_filters.compress_history(data)
        
        assert len(result.messages) == 1
        assert "[user]: Single message" in result.messages[0]["content"]
    
    def test_compress_history_preserves_context(self):
        """Test that compression preserves context and other fields."""
        data = HandoffInputData(
            messages=[{"role": "user", "content": "Test"}],
            context={"key": "value"},
            source_agent="test_agent",
            handoff_depth=2,
            handoff_chain=["agent1", "agent2"],
        )
        
        result = handoff_filters.compress_history(data)
        
        assert result.context == {"key": "value"}
        assert result.source_agent == "test_agent"
        assert result.handoff_depth == 2
        assert result.handoff_chain == ["agent1", "agent2"]
    
    def test_compress_history_skips_empty_content(self):
        """Test that messages with empty content are skipped."""
        data = HandoffInputData(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": ""},
                {"role": "user", "content": "Goodbye"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        result = handoff_filters.compress_history(data)
        
        assert "[assistant]:" not in result.messages[0]["content"]
        assert "[user]: Hello" in result.messages[0]["content"]
        assert "[user]: Goodbye" in result.messages[0]["content"]


class TestFilterChaining:
    """Tests for filter list chaining support."""
    
    def test_chaining_two_filters(self):
        """Test chaining two filters together."""
        data = HandoffInputData(
            messages=[
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi", "tool_calls": [{"id": "1"}]},
                {"role": "tool", "content": "Tool result"},
                {"role": "user", "content": "Thanks"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        # Chain: remove_all_tools -> remove_system_messages
        filters = [
            handoff_filters.remove_all_tools,
            handoff_filters.remove_system_messages,
        ]
        
        # Apply filters manually (simulating _prepare_context behavior)
        result = data
        for f in filters:
            result = f(result)
        
        # Should have removed tool calls and system messages
        assert len(result.messages) == 2
        assert all(m.get("role") != "system" for m in result.messages)
        assert all(m.get("role") != "tool" for m in result.messages)
        assert all("tool_calls" not in m for m in result.messages)
    
    def test_chaining_with_compress(self):
        """Test chaining filters ending with compress_history."""
        data = HandoffInputData(
            messages=[
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "Bye"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        # Chain: remove_system_messages -> compress_history
        filters = [
            handoff_filters.remove_system_messages,
            handoff_filters.compress_history,
        ]
        
        result = data
        for f in filters:
            result = f(result)
        
        # Should have one compressed message without system content
        assert len(result.messages) == 1
        assert "System prompt" not in result.messages[0]["content"]
        assert "[user]: Hello" in result.messages[0]["content"]
    
    def test_chaining_with_keep_last_n(self):
        """Test chaining with keep_last_n_messages."""
        data = HandoffInputData(
            messages=[
                {"role": "user", "content": "Message 1"},
                {"role": "assistant", "content": "Response 1"},
                {"role": "user", "content": "Message 2"},
                {"role": "assistant", "content": "Response 2"},
                {"role": "user", "content": "Message 3"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        # Chain: keep_last_n(2) -> compress_history
        filters = [
            handoff_filters.keep_last_n_messages(2),
            handoff_filters.compress_history,
        ]
        
        result = data
        for f in filters:
            result = f(result)
        
        # Should have compressed only last 2 messages
        assert len(result.messages) == 1
        assert "Message 1" not in result.messages[0]["content"]
        assert "Response 2" in result.messages[0]["content"]
        assert "Message 3" in result.messages[0]["content"]


class TestExistingFilters:
    """Tests for existing handoff filters."""
    
    def test_remove_all_tools(self):
        """Test remove_all_tools filter."""
        data = HandoffInputData(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Calling tool", "tool_calls": [{"id": "1"}]},
                {"role": "tool", "content": "Tool result"},
                {"role": "assistant", "content": "Done"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        result = handoff_filters.remove_all_tools(data)
        
        assert len(result.messages) == 2
        assert result.messages[0]["content"] == "Hello"
        assert result.messages[1]["content"] == "Done"
    
    def test_keep_last_n_messages(self):
        """Test keep_last_n_messages filter."""
        data = HandoffInputData(
            messages=[
                {"role": "user", "content": "1"},
                {"role": "user", "content": "2"},
                {"role": "user", "content": "3"},
                {"role": "user", "content": "4"},
                {"role": "user", "content": "5"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        result = handoff_filters.keep_last_n_messages(3)(data)
        
        assert len(result.messages) == 3
        assert result.messages[0]["content"] == "3"
        assert result.messages[1]["content"] == "4"
        assert result.messages[2]["content"] == "5"
    
    def test_remove_system_messages(self):
        """Test remove_system_messages filter."""
        data = HandoffInputData(
            messages=[
                {"role": "system", "content": "System 1"},
                {"role": "user", "content": "User"},
                {"role": "system", "content": "System 2"},
                {"role": "assistant", "content": "Assistant"},
            ],
            context={},
            source_agent="test_agent",
        )
        
        result = handoff_filters.remove_system_messages(data)
        
        assert len(result.messages) == 2
        assert result.messages[0]["content"] == "User"
        assert result.messages[1]["content"] == "Assistant"
