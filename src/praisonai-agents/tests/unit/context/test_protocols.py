"""
Unit tests for context protocols module.

Tests:
- MessageMetadata dataclass
- ContextMessage creation and conversion
- Message schema validation
- get_effective_history filtering
- cleanup_orphaned_parents
"""

import pytest
from praisonaiagents.context.protocols import (
    MessageRole,
    MessageMetadata,
    ContextMessage,
    validate_message_schema,
    get_effective_history,
    cleanup_orphaned_parents,
    VALID_ROLES,
)


class TestMessageRole:
    """Tests for MessageRole enum."""
    
    def test_valid_roles(self):
        """Test all valid roles are defined."""
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"
    
    def test_role_string_conversion(self):
        """Test role can be used as string."""
        assert str(MessageRole.USER) == "MessageRole.USER"
        assert MessageRole.USER.value == "user"


class TestMessageMetadata:
    """Tests for MessageMetadata dataclass."""
    
    def test_default_values(self):
        """Test default metadata values."""
        meta = MessageMetadata()
        assert meta.agent_id == ""
        assert meta.turn_id == 0
        assert meta.token_count == 0
        assert meta.condense_parent is None
        assert meta.truncation_parent is None
        assert meta.is_summary is False
        assert meta.is_masked is False
    
    def test_custom_values(self):
        """Test custom metadata values."""
        meta = MessageMetadata(
            agent_id="agent1",
            turn_id=5,
            token_count=100,
            condense_parent="summary-123",
            is_summary=True,
        )
        assert meta.agent_id == "agent1"
        assert meta.turn_id == 5
        assert meta.token_count == 100
        assert meta.condense_parent == "summary-123"
        assert meta.is_summary is True
    
    def test_to_dict(self):
        """Test metadata serialization."""
        meta = MessageMetadata(agent_id="test", turn_id=1)
        d = meta.to_dict()
        assert d["agent_id"] == "test"
        assert d["turn_id"] == 1
        assert "timestamp" in d


class TestContextMessage:
    """Tests for ContextMessage dataclass."""
    
    def test_from_dict_basic(self):
        """Test creating message from dict."""
        msg_dict = {"role": "user", "content": "Hello"}
        msg = ContextMessage.from_dict(msg_dict)
        
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.metadata.agent_id == ""
    
    def test_from_dict_with_agent(self):
        """Test creating message with agent context."""
        msg_dict = {"role": "assistant", "content": "Hi there"}
        msg = ContextMessage.from_dict(msg_dict, agent_id="agent1", turn_id=3)
        
        assert msg.role == MessageRole.ASSISTANT
        assert msg.metadata.agent_id == "agent1"
        assert msg.metadata.turn_id == 3
    
    def test_from_dict_tool_message(self):
        """Test creating tool message."""
        msg_dict = {
            "role": "tool",
            "content": "Result: 42",
            "tool_call_id": "call_123",
            "name": "calculator",
        }
        msg = ContextMessage.from_dict(msg_dict)
        
        assert msg.role == MessageRole.TOOL
        assert msg.metadata.tool_call_id == "call_123"
        assert msg.metadata.tool_name == "calculator"
        assert msg.metadata.is_tool_output is True
    
    def test_from_dict_with_metadata(self):
        """Test restoring metadata from dict."""
        msg_dict = {
            "role": "assistant",
            "content": "Summary...",
            "_metadata": {
                "is_summary": True,
                "summary_id": "sum-456",
                "condense_parent": None,
            },
        }
        msg = ContextMessage.from_dict(msg_dict)
        
        assert msg.metadata.is_summary is True
        assert msg.metadata.summary_id == "sum-456"
    
    def test_to_dict_basic(self):
        """Test converting message to dict."""
        msg = ContextMessage(
            role=MessageRole.USER,
            content="Test message",
        )
        d = msg.to_dict()
        
        assert d["role"] == "user"
        assert d["content"] == "Test message"
        assert "_metadata" not in d
    
    def test_to_dict_with_metadata(self):
        """Test converting message with metadata."""
        msg = ContextMessage(
            role=MessageRole.USER,
            content="Test",
            metadata=MessageMetadata(agent_id="agent1"),
        )
        d = msg.to_dict(include_metadata=True)
        
        assert "_metadata" in d
        assert d["_metadata"]["agent_id"] == "agent1"
    
    def test_content_hash(self):
        """Test content hashing for caching."""
        msg1 = ContextMessage(role=MessageRole.USER, content="Hello")
        msg2 = ContextMessage(role=MessageRole.USER, content="Hello")
        msg3 = ContextMessage(role=MessageRole.USER, content="World")
        
        assert msg1.content_hash() == msg2.content_hash()
        assert msg1.content_hash() != msg3.content_hash()


class TestValidateMessageSchema:
    """Tests for message schema validation."""
    
    def test_valid_message(self):
        """Test valid message passes validation."""
        msg = {"role": "user", "content": "Hello"}
        is_valid, error = validate_message_schema(msg)
        assert is_valid is True
        assert error is None
    
    def test_missing_role(self):
        """Test missing role fails validation."""
        msg = {"content": "Hello"}
        is_valid, error = validate_message_schema(msg)
        assert is_valid is False
        assert "role" in error
    
    def test_missing_content(self):
        """Test missing content fails validation."""
        msg = {"role": "user"}
        is_valid, error = validate_message_schema(msg)
        assert is_valid is False
        assert "content" in error
    
    def test_invalid_role(self):
        """Test invalid role fails validation."""
        msg = {"role": "invalid", "content": "Hello"}
        is_valid, error = validate_message_schema(msg)
        assert is_valid is False
        assert "Invalid role" in error
    
    def test_tool_message_without_id_non_strict(self):
        """Test tool message without ID passes in non-strict mode."""
        msg = {"role": "tool", "content": "Result"}
        is_valid, error = validate_message_schema(msg, strict=False)
        assert is_valid is True
    
    def test_tool_message_without_id_strict(self):
        """Test tool message without ID fails in strict mode."""
        msg = {"role": "tool", "content": "Result"}
        is_valid, error = validate_message_schema(msg, strict=True)
        assert is_valid is False
        assert "tool_call_id" in error
    
    def test_all_valid_roles(self):
        """Test all valid roles pass validation."""
        for role in VALID_ROLES:
            msg = {"role": role, "content": "Test"}
            is_valid, _ = validate_message_schema(msg)
            assert is_valid is True


class TestGetEffectiveHistory:
    """Tests for get_effective_history filtering."""
    
    def test_no_condensed_messages(self):
        """Test history without condensation returns all."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = get_effective_history(messages)
        assert len(result) == 2
    
    def test_filters_condensed_messages(self):
        """Test condensed messages are filtered out."""
        messages = [
            {"role": "user", "content": "Old message", "_metadata": {"condense_parent": "sum-1"}},
            {"role": "assistant", "content": "Summary", "_metadata": {"is_summary": True, "summary_id": "sum-1"}},
            {"role": "user", "content": "New message"},
        ]
        result = get_effective_history(messages)
        
        # Should include summary and new message, not old message
        assert len(result) == 2
        assert result[0]["content"] == "Summary"
        assert result[1]["content"] == "New message"
    
    def test_filters_truncated_messages(self):
        """Test truncated messages are filtered out."""
        messages = [
            {"role": "user", "content": "Hidden", "_metadata": {"truncation_parent": "trunc-1"}},
            {"role": "user", "content": "Marker", "_metadata": {"is_truncation_marker": True, "truncation_id": "trunc-1"}},
            {"role": "user", "content": "Visible"},
        ]
        result = get_effective_history(messages)
        
        assert len(result) == 2
        assert result[0]["content"] == "Marker"
        assert result[1]["content"] == "Visible"
    
    def test_orphaned_parent_included(self):
        """Test messages with orphaned parents are included."""
        messages = [
            # Parent references non-existent summary
            {"role": "user", "content": "Should show", "_metadata": {"condense_parent": "deleted-sum"}},
            {"role": "user", "content": "Also show"},
        ]
        result = get_effective_history(messages)
        
        # Both should be included since summary doesn't exist
        assert len(result) == 2


class TestCleanupOrphanedParents:
    """Tests for cleanup_orphaned_parents."""
    
    def test_no_orphans(self):
        """Test cleanup with no orphaned parents."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = cleanup_orphaned_parents(messages)
        assert len(result) == 2
    
    def test_clears_orphaned_condense_parent(self):
        """Test orphaned condense_parent is cleared."""
        messages = [
            {"role": "user", "content": "Old", "_metadata": {"condense_parent": "deleted-sum"}},
            {"role": "user", "content": "New"},
        ]
        result = cleanup_orphaned_parents(messages)
        
        # First message should have condense_parent cleared
        assert "condense_parent" not in result[0].get("_metadata", {})
    
    def test_keeps_valid_condense_parent(self):
        """Test valid condense_parent is kept."""
        messages = [
            {"role": "user", "content": "Old", "_metadata": {"condense_parent": "sum-1"}},
            {"role": "assistant", "content": "Summary", "_metadata": {"is_summary": True, "summary_id": "sum-1"}},
        ]
        result = cleanup_orphaned_parents(messages)
        
        # First message should keep condense_parent
        assert result[0]["_metadata"]["condense_parent"] == "sum-1"
    
    def test_clears_orphaned_truncation_parent(self):
        """Test orphaned truncation_parent is cleared."""
        messages = [
            {"role": "user", "content": "Old", "_metadata": {"truncation_parent": "deleted-trunc"}},
        ]
        result = cleanup_orphaned_parents(messages)
        
        assert "truncation_parent" not in result[0].get("_metadata", {})
