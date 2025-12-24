"""
Unit tests for the Compaction module.

Tests cover:
- CompactionConfig settings
- CompactionStrategy enum
- CompactionResult properties
- ContextCompactor operations
"""

import pytest

from praisonaiagents.compaction.config import CompactionConfig
from praisonaiagents.compaction.strategy import CompactionStrategy
from praisonaiagents.compaction.result import CompactionResult
from praisonaiagents.compaction.compactor import ContextCompactor


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
