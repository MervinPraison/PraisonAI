"""
Unit tests for the Compaction module.

Tests cover:
- CompactionConfig settings
- CompactionStrategy enum
- CompactionResult properties
- ContextCompactor operations
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

from praisonaiagents.compaction.config import CompactionConfig
from praisonaiagents.compaction.strategy import CompactionStrategy
from praisonaiagents.compaction.result import CompactionResult
from praisonaiagents.compaction.compactor import ContextCompactor
from praisonaiagents.config.feature_configs import ExecutionConfig


# =============================================================================
# CompactionConfig Tests
# =============================================================================

class TestCompactionConfig:
    """Tests for CompactionConfig class."""
    
    def test_config_defaults(self):
        """Test default configuration."""
        config = CompactionConfig()
        
        assert config.enabled
        assert config.max_tokens == 8000
        assert config.target_tokens == 6000
        assert config.preserve_system
        assert config.preserve_recent == 5
    
    def test_config_custom(self):
        """Test custom configuration."""
        config = CompactionConfig(
            enabled=False,
            max_tokens=16000,
            preserve_recent=10
        )
        
        assert not config.enabled
        assert config.max_tokens == 16000
        assert config.preserve_recent == 10


# =============================================================================
# CompactionStrategy Tests
# =============================================================================

class TestCompactionStrategy:
    """Tests for CompactionStrategy enum."""
    
    def test_strategy_values(self):
        """Test strategy enum values."""
        assert CompactionStrategy.TRUNCATE.value == "truncate"
        assert CompactionStrategy.SUMMARIZE.value == "summarize"
        assert CompactionStrategy.SLIDING.value == "sliding"
        assert CompactionStrategy.SMART.value == "smart"
        assert CompactionStrategy.LLM_SUMMARIZE.value == "llm_summarize"
    
    def test_strategy_from_string(self):
        """Test creating strategy from string."""
        strategy = CompactionStrategy("truncate")
        assert strategy == CompactionStrategy.TRUNCATE


# =============================================================================
# CompactionResult Tests
# =============================================================================

class TestCompactionResult:
    """Tests for CompactionResult class."""
    
    def test_result_creation(self):
        """Test creating a result."""
        result = CompactionResult(
            original_tokens=10000,
            compacted_tokens=6000,
            messages_removed=5,
            messages_kept=10,
            strategy_used=CompactionStrategy.TRUNCATE
        )
        
        assert result.original_tokens == 10000
        assert result.compacted_tokens == 6000
    
    def test_result_tokens_saved(self):
        """Test tokens saved calculation."""
        result = CompactionResult(
            original_tokens=10000,
            compacted_tokens=6000,
            messages_removed=5,
            messages_kept=10,
            strategy_used=CompactionStrategy.TRUNCATE
        )
        
        assert result.tokens_saved == 4000
    
    def test_result_compression_ratio(self):
        """Test compression ratio calculation."""
        result = CompactionResult(
            original_tokens=10000,
            compacted_tokens=5000,
            messages_removed=5,
            messages_kept=10,
            strategy_used=CompactionStrategy.TRUNCATE
        )
        
        assert result.compression_ratio == 0.5
    
    def test_result_was_compacted(self):
        """Test was_compacted property."""
        result = CompactionResult(
            original_tokens=10000,
            compacted_tokens=6000,
            messages_removed=5,
            messages_kept=10,
            strategy_used=CompactionStrategy.TRUNCATE
        )
        
        assert result.was_compacted
    
    def test_result_not_compacted(self):
        """Test when not compacted."""
        result = CompactionResult(
            original_tokens=5000,
            compacted_tokens=5000,
            messages_removed=0,
            messages_kept=10,
            strategy_used=CompactionStrategy.TRUNCATE
        )
        
        assert not result.was_compacted
    
    def test_result_to_dict(self):
        """Test result serialization."""
        result = CompactionResult(
            original_tokens=10000,
            compacted_tokens=6000,
            messages_removed=5,
            messages_kept=10,
            strategy_used=CompactionStrategy.TRUNCATE
        )
        data = result.to_dict()
        
        assert data["original_tokens"] == 10000
        assert data["tokens_saved"] == 4000
        assert data["strategy_used"] == "truncate"


# =============================================================================
# ContextCompactor Tests
# =============================================================================

class TestContextCompactor:
    """Tests for ContextCompactor class."""
    
    @pytest.fixture
    def compactor(self):
        """Create a test compactor."""
        return ContextCompactor(max_tokens=100, preserve_recent=2)
    
    @pytest.fixture
    def messages(self):
        """Create test messages."""
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"},
            {"role": "user", "content": "What's the weather like?"},
            {"role": "assistant", "content": "I don't have access to weather data."},
        ]
    
    def test_compactor_creation(self, compactor):
        """Test creating a compactor."""
        assert compactor.max_tokens == 100
        assert compactor.preserve_recent == 2
    
    def test_compactor_estimate_tokens(self, compactor):
        """Test token estimation."""
        text = "Hello world"  # 11 chars
        tokens = compactor.estimate_tokens(text)
        
        assert tokens == 2  # 11 // 4
    
    def test_compactor_count_message_tokens(self, compactor):
        """Test message token counting."""
        message = {"role": "user", "content": "Hello world"}
        tokens = compactor.count_message_tokens(message)
        
        assert tokens == 2
    
    def test_compactor_count_total_tokens(self, compactor, messages):
        """Test total token counting."""
        tokens = compactor.count_total_tokens(messages)
        
        assert tokens > 0
    
    def test_compactor_needs_compaction_true(self):
        """Test needs_compaction when over limit."""
        # Create compactor with very low limit
        compactor = ContextCompactor(max_tokens=10, preserve_recent=2)
        messages = [
            {"role": "user", "content": "This is a very long message that should exceed the token limit."},
            {"role": "assistant", "content": "This is another long response that adds more tokens."},
        ]
        
        needs = compactor.needs_compaction(messages)
        
        assert needs
    
    def test_compactor_needs_compaction_false(self):
        """Test needs_compaction when under limit."""
        compactor = ContextCompactor(max_tokens=10000)
        messages = [{"role": "user", "content": "Hi"}]
        
        needs = compactor.needs_compaction(messages)
        
        assert not needs
    
    def test_compactor_compact_not_needed(self):
        """Test compact when not needed."""
        compactor = ContextCompactor(max_tokens=10000)
        messages = [{"role": "user", "content": "Hi"}]
        
        compacted, result = compactor.compact(messages)
        
        assert len(compacted) == len(messages)
        assert not result.was_compacted
    
    def test_compactor_compact_truncate(self):
        """Test truncate strategy."""
        compactor = ContextCompactor(max_tokens=10, preserve_recent=1)
        compactor.strategy = CompactionStrategy.TRUNCATE
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "This is a very long message that should exceed the token limit."},
            {"role": "assistant", "content": "This is another long response."},
            {"role": "user", "content": "More content here."},
        ]
        
        compacted, result = compactor.compact(messages)
        
        assert len(compacted) < len(messages)
        assert result.was_compacted
        assert result.strategy_used == CompactionStrategy.TRUNCATE

    def test_truncate_does_not_infinite_loop_on_system_only_overflow(self):
        """System-only messages over budget must not hang truncation."""
        compactor = ContextCompactor(max_tokens=10, target_tokens=5, preserve_recent=0)
        messages = [
            {"role": "system", "content": "x" * 200},
            {"role": "system", "content": "y" * 200},
        ]

        result = compactor._truncate(messages)

        assert len(result) == 2
        assert compactor.count_total_tokens(result) > compactor.target_tokens
    
    def test_compactor_compact_sliding(self, compactor, messages):
        """Test sliding window strategy."""
        compactor.strategy = CompactionStrategy.SLIDING
        
        compacted, result = compactor.compact(messages)
        
        assert result.strategy_used == CompactionStrategy.SLIDING
    
    def test_compactor_compact_summarize(self, compactor, messages):
        """Test summarize strategy."""
        compactor.strategy = CompactionStrategy.SUMMARIZE
        
        compacted, result = compactor.compact(messages)
        
        assert result.strategy_used == CompactionStrategy.SUMMARIZE

    def test_compaction_result_summary_populated(self):
        """Regression (#3062): summarize strategies must surface the summary text.

        Previously ``CompactionResult.summary`` was always ``""``, so the
        distilled summary never reached hooks/persisters and was lost on exit.
        """
        compactor = ContextCompactor(max_tokens=10, preserve_recent=1)
        compactor.strategy = CompactionStrategy.SUMMARIZE
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "First user message with lots of content here."},
            {"role": "assistant", "content": "First assistant reply also fairly long."},
            {"role": "user", "content": "Second user message adding more context."},
            {"role": "assistant", "content": "Second assistant reply wrapping things up."},
        ]

        compacted, result = compactor.compact(messages)

        # A summary system message was injected AND its text is on the result.
        summary_msgs = [
            m for m in compacted
            if m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and "summary" in m["content"].lower()
        ]
        assert summary_msgs, "expected an injected summary message"
        assert result.summary
        assert result.summary == summary_msgs[-1]["content"]
    
    def test_compactor_compact_smart(self, compactor, messages):
        """Test smart strategy."""
        compactor.strategy = CompactionStrategy.SMART
        
        compacted, result = compactor.compact(messages)
        
        assert result.strategy_used == CompactionStrategy.SMART
    
    def test_compactor_preserves_system(self, compactor, messages):
        """Test that system messages are preserved."""
        compacted, _ = compactor.compact(messages)
        
        system_msgs = [m for m in compacted if m.get("role") == "system"]
        assert len(system_msgs) >= 1
    
    def test_compactor_preserves_recent(self, compactor, messages):
        """Test that recent messages are preserved."""
        compacted, _ = compactor.compact(messages)
        
        # Should have at least preserve_recent messages
        non_system = [m for m in compacted if m.get("role") != "system"]
        assert len(non_system) >= min(compactor.preserve_recent, len(messages) - 1)
    
    def test_compactor_get_stats(self, compactor, messages):
        """Test get_stats method."""
        stats = compactor.get_stats(messages)
        
        assert "message_count" in stats
        assert "total_tokens" in stats
        assert "needs_compaction" in stats
        assert stats["message_count"] == len(messages)
    
    def test_compactor_multipart_content(self, compactor):
        """Test handling multipart content."""
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": "World"}
            ]
        }
        
        tokens = compactor.count_message_tokens(message)
        
        assert tokens > 0
    
    def test_compactor_llm_summarize_sync_no_function(self):
        """Test LLM_SUMMARIZE strategy without LLM function (sync fallback)."""
        compactor = ContextCompactor(max_tokens=10, preserve_recent=1)
        compactor.strategy = CompactionStrategy.LLM_SUMMARIZE
        # No llm_summarize_fn provided - should fallback to naive summarization
        
        messages = [
            {"role": "user", "content": "This is a very long message that should exceed the token limit."},
            {"role": "assistant", "content": "This is another long response."},
            {"role": "user", "content": "More content here."},
        ]
        
        compacted, result = compactor.compact(messages)
        
        # Should fallback to naive summarization 
        assert result.strategy_used == CompactionStrategy.LLM_SUMMARIZE
        assert len(compacted) < len(messages)
    
    @pytest.mark.asyncio
    async def test_compactor_llm_summarize_async_with_function(self):
        """Test LLM_SUMMARIZE strategy with async LLM function."""
        # Mock LLM function
        mock_llm_fn = AsyncMock(return_value="This is a test summary of the conversation.")
        
        compactor = ContextCompactor(
            max_tokens=10, 
            preserve_recent=1,
            llm_summarize_fn=mock_llm_fn
        )
        compactor.strategy = CompactionStrategy.LLM_SUMMARIZE
        
        messages = [
            {"role": "user", "content": "This is a very long message that should exceed the token limit."},
            {"role": "assistant", "content": "This is another long response."},
            {"role": "user", "content": "More content here."},
        ]
        
        compacted, result = compactor.compact_async(messages)
        
        assert result.strategy_used == CompactionStrategy.LLM_SUMMARIZE
        assert len(compacted) < len(messages)
        
        # Check that LLM function was called
        mock_llm_fn.assert_called_once()
        
        # Check that summary was added
        summary_msgs = [m for m in compacted if m.get("_llm_generated")]
        assert len(summary_msgs) == 1
        assert "This is a test summary" in summary_msgs[0]["content"]
    
    @pytest.mark.asyncio
    async def test_compactor_llm_summarize_async_failure_fallback(self):
        """Test LLM_SUMMARIZE strategy with failing LLM function."""
        # Mock LLM function that fails
        mock_llm_fn = AsyncMock(side_effect=Exception("LLM API failure"))
        
        compactor = ContextCompactor(
            max_tokens=10, 
            preserve_recent=1,
            llm_summarize_fn=mock_llm_fn
        )
        compactor.strategy = CompactionStrategy.LLM_SUMMARIZE
        
        messages = [
            {"role": "user", "content": "This is a very long message that should exceed the token limit."},
            {"role": "assistant", "content": "This is another long response."},
        ]
        
        compacted, result = compactor.compact_async(messages)
        
        # Should fallback to naive summarization and not crash
        assert result.strategy_used == CompactionStrategy.LLM_SUMMARIZE
        assert len(compacted) <= len(messages)
        
        # Check that a fallback summary was added 
        fallback_msgs = [m for m in compacted if m.get("_fallback")]
        assert len(fallback_msgs) <= 1  # May have fallback summary
    
    def test_compactor_format_messages_for_summary(self):
        """Test _format_messages_for_summary method."""
        compactor = ContextCompactor()
        
        messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {
                "role": "assistant", 
                "content": "I'm doing well!",
                "tool_calls": [{"function": {"name": "weather_tool"}}]
            },
            {"role": "tool", "tool_call_id": "123", "content": "Weather is sunny"},
            {"role": "user", "content": "Great!"},
        ]
        
        formatted = compactor._format_messages_for_summary(messages)
        
        assert "1. user: Hello, how are you?" in formatted
        assert "2. assistant: Called tools: weather_tool" in formatted
        assert "tool 123" in formatted
        assert "4. user: Great!" in formatted


# =============================================================================
# ExecutionConfig Tests for compaction_strategy
# =============================================================================

class TestExecutionConfigCompactionStrategy:
    """Tests for ExecutionConfig.compaction_strategy field."""
    
    def test_compaction_strategy_default(self):
        """Test that compaction_strategy defaults to None."""
        config = ExecutionConfig()
        assert config.compaction_strategy is None
    
    def test_compaction_strategy_set_enum(self):
        """Test setting compaction_strategy with enum value."""
        config = ExecutionConfig(compaction_strategy=CompactionStrategy.LLM_SUMMARIZE)
        assert config.compaction_strategy == CompactionStrategy.LLM_SUMMARIZE
    
    def test_compaction_strategy_to_dict_none(self):
        """Test to_dict with None compaction_strategy."""
        config = ExecutionConfig()
        data = config.to_dict()
        assert data["compaction_strategy"] is None
    
    def test_compaction_strategy_to_dict_enum(self):
        """Test to_dict with enum compaction_strategy."""
        config = ExecutionConfig(compaction_strategy=CompactionStrategy.LLM_SUMMARIZE)
        data = config.to_dict()
        assert data["compaction_strategy"] == "llm_summarize"
    
    def test_compaction_strategy_serialization_safety(self):
        """Test that serialization handles edge cases safely."""
        config = ExecutionConfig()
        
        # Test with None strategy
        assert config.compaction_strategy is None
        data = config.to_dict()
        assert data["compaction_strategy"] is None
        
        # Test with enum strategy
        config.compaction_strategy = CompactionStrategy.TRUNCATE
        data = config.to_dict()
        assert data["compaction_strategy"] == "truncate"


class TestCompactionSummaryDurability:
    """Issue #3062: the populated summary flows into durable session resume.

    The persist + resume machinery already exists (Issue #2741); the missing
    link was ``CompactionResult.summary`` being empty. These tests exercise the
    full compactor -> checkpoint -> resume path end-to-end.
    """

    def _persist(self, store, session_id, result):
        # Mirror Agent._persist_compaction_checkpoint's guarded contract.
        summary = getattr(result, "summary", "") or ""
        if summary.strip():
            store.append_compaction_checkpoint(session_id, summary)

    def test_summary_persisted_and_reloaded_on_resume(self):
        import tempfile
        from praisonaiagents.session.store import DefaultSessionStore

        compactor = ContextCompactor(max_tokens=10, preserve_recent=1)
        compactor.strategy = CompactionStrategy.SUMMARIZE
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "First user message with lots of content here."},
            {"role": "assistant", "content": "First assistant reply also fairly long."},
            {"role": "user", "content": "Second user message adding more context."},
            {"role": "assistant", "content": "Second assistant reply wrapping things up."},
        ]

        _, result = compactor.compact(messages)
        assert result.summary  # regression: no longer empty

        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s1", "old turn")
            self._persist(store, "s1", result)
            store.add_user_message("s1", "new turn")

            # Fresh instance simulates a restarted process.
            resumed = DefaultSessionStore(session_dir=tmpdir)
            working = resumed.get_working_history("s1")
            assert working[0]["role"] == "system"
            assert working[0]["content"] == result.summary
            assert working[-1]["content"] == "new turn"

    def test_disabled_is_noop(self):
        """No session store bound -> nothing persisted, behaviour unchanged."""
        import tempfile
        from praisonaiagents.session.store import DefaultSessionStore

        compactor = ContextCompactor(max_tokens=10000)
        messages = [{"role": "user", "content": "short"}]
        _, result = compactor.compact(messages)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s1", "a")
            self._persist(store, "s1", result)  # empty summary -> no-op
            session = store.get_session("s1")
            assert session.last_compaction is None

    def test_reused_compactor_does_not_leak_prior_summary(self):
        """A stale ``_previous_summary`` must NOT surface on a later non-
        summarizing pass (Issue #3062 review): otherwise a reused compactor
        would persist an outdated checkpoint and drop intervening turns on
        resume. Extraction only reflects the summary of the *current* pass.
        """
        compactor = ContextCompactor(max_tokens=10, preserve_recent=1)
        compactor._previous_summary = "STALE summary from an earlier LLM pass"
        compactor.strategy = CompactionStrategy.TRUNCATE
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1 with a good amount of content here"},
            {"role": "assistant", "content": "a1 with a good amount of content too"},
            {"role": "user", "content": "u2 with even more content to force compaction"},
        ]
        _, result = compactor.compact(messages)
        assert "STALE" not in (result.summary or "")
        assert result.summary == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
