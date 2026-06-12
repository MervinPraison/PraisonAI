"""
Unit tests for compaction anti-injection features.

Tests the anti-injection prefix, _compacted filtering, and structured templates
from the merged PR #1823 and follow-up implementation.
"""

import pytest
from praisonaiagents.compaction.config import CompactionConfig, COMPACTION_PREFIX, SUMMARY_TEMPLATE
from praisonaiagents.compaction.compactor import ContextCompactor


class TestAntiInjectionFeatures:
    """Tests for anti-injection and structured template features."""
    
    def test_compaction_prefix_constant(self):
        """Test that COMPACTION_PREFIX has anti-injection content."""
        assert "REFERENCE ONLY" in COMPACTION_PREFIX
        assert "Do NOT re-execute" in COMPACTION_PREFIX
        assert "latest message WINS" in COMPACTION_PREFIX
        
    def test_summary_template_constant(self):
        """Test that SUMMARY_TEMPLATE has structured sections."""
        assert "## Active Task" in SUMMARY_TEMPLATE
        assert "## Completed Actions" in SUMMARY_TEMPLATE
        assert "## In Progress" in SUMMARY_TEMPLATE
        assert "## Pending Questions" in SUMMARY_TEMPLATE
        assert "## Relevant Files / Paths" in SUMMARY_TEMPLATE
        assert "## Remaining Work" in SUMMARY_TEMPLATE
        
    def test_compaction_config_defaults(self):
        """Test CompactionConfig includes anti-injection fields."""
        config = CompactionConfig()
        assert config.compaction_prefix == COMPACTION_PREFIX
        assert config.structured_template is True
        assert config.iterative_update is True
        
    def test_compaction_config_custom(self):
        """Test custom anti-injection configuration."""
        custom_prefix = "[CUSTOM] This is custom framing"
        config = CompactionConfig(
            compaction_prefix=custom_prefix,
            structured_template=False,
            iterative_update=False
        )
        assert config.compaction_prefix == custom_prefix
        assert config.structured_template is False
        assert config.iterative_update is False
        
    def test_compactor_with_anti_injection_config(self):
        """Test ContextCompactor respects anti-injection config."""
        config = CompactionConfig(
            max_tokens=100,
            compaction_prefix="[CUSTOM PREFIX]",
            structured_template=True,
            iterative_update=True
        )
        compactor = ContextCompactor(config=config)
        
        assert compactor.config.compaction_prefix == "[CUSTOM PREFIX]"
        assert compactor.config.structured_template is True
        assert compactor.config.iterative_update is True
        
    def test_compacted_message_filtering(self):
        """Test that _compacted messages are filtered out during compaction."""
        compactor = ContextCompactor(max_tokens=50, preserve_recent=1)
        
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "system", "content": "Previous summary", "_compacted": True},  # Should be filtered
            {"role": "user", "content": "This is a very long message that exceeds token limit and should trigger compaction."},
            {"role": "assistant", "content": "This is another long response that adds more tokens."},
            {"role": "user", "content": "Recent message."},
        ]
        
        compacted, result = compactor.compact(messages)
        
        # Should not contain the old compacted message
        compacted_contents = [msg.get("content", "") for msg in compacted]
        assert "Previous summary" not in " ".join(compacted_contents)
        
        # Should have new compacted message with anti-injection prefix
        has_new_compacted = any(msg.get("_compacted") for msg in compacted)
        assert has_new_compacted
        
    def test_anti_injection_prefix_applied(self):
        """Test that anti-injection prefix is applied to compacted messages."""
        config = CompactionConfig(
            max_tokens=50,
            compaction_prefix="[CUSTOM ANTI-INJECTION]",
            structured_template=True
        )
        compactor = ContextCompactor(config=config)
        
        messages = [
            {"role": "user", "content": "This is a very long message that exceeds token limit and should trigger compaction to test anti-injection framing."},
            {"role": "assistant", "content": "This is another long response that adds more tokens and should be compacted."},
            {"role": "user", "content": "Recent message."},
        ]
        
        compacted, result = compactor.compact(messages)
        
        # Find the compacted system message
        compacted_msg = next((msg for msg in compacted if msg.get("_compacted")), None)
        assert compacted_msg is not None
        
        content = compacted_msg["content"]
        assert "[CUSTOM ANTI-INJECTION]" in content
        assert result.was_compacted
        
    def test_structured_template_generation(self):
        """Test structured template generation with categorized sections."""
        config = CompactionConfig(
            max_tokens=50,
            structured_template=True
        )
        compactor = ContextCompactor(config=config)
        
        messages = [
            {"role": "user", "content": "I need to implement a new feature for user authentication."},
            {"role": "assistant", "content": "I'll help you create the authentication system. Let me start by analyzing requirements."},
            {"role": "user", "content": "What files do I need to create?"},
            {"role": "assistant", "content": "You'll need auth.py, user_model.py, and tests/test_auth.py."},
            {"role": "user", "content": "Recent message."},
        ]
        
        compacted, result = compactor.compact(messages)
        
        # Find the compacted system message
        compacted_msg = next((msg for msg in compacted if msg.get("_compacted")), None)
        assert compacted_msg is not None
        
        content = compacted_msg["content"]
        
        # Should contain structured sections
        assert "## Active Task" in content
        assert "## Completed Actions" in content
        assert "## Remaining Work" in content
        
        # Should contain actual content categorization
        assert "authentication" in content.lower()
        assert "auth.py" in content or "user_model.py" in content
        
    def test_iterative_update_preserves_state(self):
        """Test that iterative_update preserves previous summary state."""
        config = CompactionConfig(
            max_tokens=50,
            iterative_update=True
        )
        compactor = ContextCompactor(config=config)
        
        # First compaction
        messages1 = [
            {"role": "user", "content": "First conversation with lots of text that exceeds the token limit."},
            {"role": "assistant", "content": "First response with detailed explanation."},
            {"role": "user", "content": "Recent message 1."},
        ]
        
        compacted1, result1 = compactor.compact(messages1)
        assert result1.was_compacted
        
        # Second compaction - should merge with previous
        messages2 = [
            {"role": "user", "content": "Second conversation with more text that also exceeds limits."},
            {"role": "assistant", "content": "Second response with more details."},
            {"role": "user", "content": "Recent message 2."},
        ]
        
        compacted2, result2 = compactor.compact(messages2)
        
        # Should have merged summaries
        compacted_msg = next((msg for msg in compacted2 if msg.get("_compacted")), None)
        assert compacted_msg is not None
        
        # Content should reference previous context
        content = compacted_msg["content"]
        assert "[Previous context]" in content or "previous" in content.lower()
        
    def test_iterative_update_disabled(self):
        """Test that iterative_update=False doesn't merge previous summaries."""
        config = CompactionConfig(
            max_tokens=50,
            iterative_update=False
        )
        compactor = ContextCompactor(config=config)
        
        # First compaction
        messages1 = [
            {"role": "user", "content": "First conversation with lots of text that exceeds the token limit."},
            {"role": "assistant", "content": "First response with detailed explanation."},
        ]
        
        compacted1, result1 = compactor.compact(messages1)
        assert result1.was_compacted
        
        # Second compaction - should not merge
        messages2 = [
            {"role": "user", "content": "Second conversation with more text that also exceeds limits."},
            {"role": "assistant", "content": "Second response with more details."},
        ]
        
        compacted2, result2 = compactor.compact(messages2)
        
        # Should not contain previous context references
        compacted_msg = next((msg for msg in compacted2 if msg.get("_compacted")), None)
        assert compacted_msg is not None
        
        content = compacted_msg["content"]
        assert "[Previous context]" not in content
        
    def test_compaction_with_no_structured_template(self):
        """Test compaction with structured_template=False."""
        config = CompactionConfig(
            max_tokens=50,
            structured_template=False
        )
        compactor = ContextCompactor(config=config)
        
        messages = [
            {"role": "user", "content": "This is a very long message that exceeds token limit."},
            {"role": "assistant", "content": "This is another long response."},
            {"role": "user", "content": "Recent message."},
        ]
        
        compacted, result = compactor.compact(messages)
        
        # Find the compacted system message
        compacted_msg = next((msg for msg in compacted if msg.get("_compacted")), None)
        assert compacted_msg is not None
        
        content = compacted_msg["content"]
        
        # Should not contain structured sections when disabled
        assert "## Active Task" not in content
        assert "## Completed Actions" not in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])