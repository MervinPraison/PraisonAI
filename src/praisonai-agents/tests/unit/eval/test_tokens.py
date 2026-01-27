"""
Tests for token estimation and context length utilities.

TDD: These tests are written FIRST before implementation.
"""

import pytest


class TestEstimateTokens:
    """Tests for estimate_tokens() function."""
    
    def test_estimate_tokens_exists(self):
        """Test that estimate_tokens function exists."""
        from praisonaiagents.eval.tokens import estimate_tokens
        assert callable(estimate_tokens)
    
    def test_estimate_tokens_empty_string(self):
        """Test token estimation for empty string."""
        from praisonaiagents.eval.tokens import estimate_tokens
        assert estimate_tokens("") == 0
    
    def test_estimate_tokens_simple_text(self):
        """Test token estimation for simple text."""
        from praisonaiagents.eval.tokens import estimate_tokens
        # "Hello world" should be ~2-3 tokens
        result = estimate_tokens("Hello world")
        assert 2 <= result <= 5
    
    def test_estimate_tokens_longer_text(self):
        """Test token estimation for longer text."""
        from praisonaiagents.eval.tokens import estimate_tokens
        text = "The quick brown fox jumps over the lazy dog. " * 10
        result = estimate_tokens(text)
        # ~100 words, should be ~75-150 tokens
        assert 50 <= result <= 200
    
    def test_estimate_tokens_method_chars(self):
        """Test char-based estimation method."""
        from praisonaiagents.eval.tokens import estimate_tokens
        text = "Hello world, this is a test."  # 28 chars
        result = estimate_tokens(text, method="chars")
        # 28 / 4 = 7 tokens
        assert result == 7
    
    def test_estimate_tokens_method_words(self):
        """Test word-based estimation method."""
        from praisonaiagents.eval.tokens import estimate_tokens
        text = "Hello world this is a test"  # 6 words
        result = estimate_tokens(text, method="words")
        # 6 / 0.75 = 8 tokens
        assert result == 8
    
    def test_estimate_tokens_method_max(self):
        """Test max method (default) returns higher of word/char estimates."""
        from praisonaiagents.eval.tokens import estimate_tokens
        text = "Hello world"
        result_max = estimate_tokens(text, method="max")
        result_chars = estimate_tokens(text, method="chars")
        result_words = estimate_tokens(text, method="words")
        assert result_max == max(result_chars, result_words)
    
    def test_estimate_tokens_method_average(self):
        """Test average method returns average of word/char estimates."""
        from praisonaiagents.eval.tokens import estimate_tokens
        text = "Hello world"
        result_avg = estimate_tokens(text, method="average")
        result_chars = estimate_tokens(text, method="chars")
        result_words = estimate_tokens(text, method="words")
        expected = (result_chars + result_words) // 2
        assert result_avg == expected


class TestGetContextLength:
    """Tests for get_context_length() function."""
    
    def test_get_context_length_exists(self):
        """Test that get_context_length function exists."""
        from praisonaiagents.eval.tokens import get_context_length
        assert callable(get_context_length)
    
    def test_get_context_length_gpt4o_mini(self):
        """Test context length for gpt-4o-mini (without litellm for consistency)."""
        from praisonaiagents.eval.tokens import get_context_length
        # Use use_litellm=False for deterministic testing
        result = get_context_length("gpt-4o-mini", use_litellm=False)
        assert result == 128000
    
    def test_get_context_length_gpt4o(self):
        """Test context length for gpt-4o (without litellm for consistency)."""
        from praisonaiagents.eval.tokens import get_context_length
        result = get_context_length("gpt-4o", use_litellm=False)
        assert result == 128000
    
    def test_get_context_length_claude_sonnet(self):
        """Test context length for claude-3-5-sonnet (without litellm)."""
        from praisonaiagents.eval.tokens import get_context_length
        result = get_context_length("claude-3-5-sonnet-20241022", use_litellm=False)
        assert result == 200000
    
    def test_get_context_length_unknown_model(self):
        """Test context length for unknown model returns default."""
        from praisonaiagents.eval.tokens import get_context_length
        result = get_context_length("unknown-model-xyz", use_litellm=False)
        # Should return default of 128000
        assert result == 128000
    
    def test_get_context_length_gemini(self):
        """Test context length for Gemini models (without litellm)."""
        from praisonaiagents.eval.tokens import get_context_length
        result = get_context_length("gemini-1.5-flash", use_litellm=False)
        # Gemini has very large context
        assert result >= 128000


class TestNeedsChunking:
    """Tests for needs_chunking() function."""
    
    def test_needs_chunking_exists(self):
        """Test that needs_chunking function exists."""
        from praisonaiagents.eval.tokens import needs_chunking
        assert callable(needs_chunking)
    
    def test_needs_chunking_small_text(self):
        """Test that small text doesn't need chunking."""
        from praisonaiagents.eval.tokens import needs_chunking
        text = "Hello world, this is a small test."
        result = needs_chunking(text, model="gpt-4o-mini")
        assert result is False
    
    def test_needs_chunking_large_text(self):
        """Test that very large text needs chunking."""
        from praisonaiagents.eval.tokens import needs_chunking
        # Create text that exceeds context window (use smaller for speed)
        # 128K tokens * 4 chars = 512K chars, use 600K to exceed
        text = "a" * 600000
        result = needs_chunking(text, model="gpt-4o-mini")
        assert result is True
    
    def test_needs_chunking_with_safety_margin(self):
        """Test chunking decision respects safety margin."""
        from praisonaiagents.eval.tokens import needs_chunking
        # Create text at ~90% of context window
        # 128K tokens * 0.9 = 115K tokens * 4 chars = 460K chars
        text = "a" * 460000
        # With 80% safety margin (102K tokens), 115K tokens should need chunking
        result = needs_chunking(text, model="gpt-4o-mini", safety_margin=0.8)
        assert result is True
    
    def test_needs_chunking_returns_info_dict(self):
        """Test that needs_chunking can return detailed info."""
        from praisonaiagents.eval.tokens import needs_chunking
        text = "Hello world"
        result = needs_chunking(text, model="gpt-4o-mini", return_info=True)
        assert isinstance(result, dict)
        assert "needs_chunking" in result
        assert "estimated_tokens" in result
        assert "context_length" in result
        assert "utilization" in result


class TestCountTokens:
    """Tests for count_tokens() function with litellm integration."""
    
    def test_count_tokens_exists(self):
        """Test that count_tokens function exists."""
        from praisonaiagents.eval.tokens import count_tokens
        assert callable(count_tokens)
    
    def test_count_tokens_fallback_without_litellm(self):
        """Test that count_tokens falls back to estimation without litellm."""
        from praisonaiagents.eval.tokens import count_tokens
        text = "Hello world"
        result = count_tokens(text, model="gpt-4o-mini")
        # Should return an integer
        assert isinstance(result, int)
        assert result > 0


class TestTokenUtilsIntegration:
    """Integration tests for token utilities."""
    
    def test_auto_chunk_decision_workflow(self):
        """Test the full auto-chunking decision workflow."""
        from praisonaiagents.eval.tokens import (
            estimate_tokens,
            get_context_length,
            needs_chunking,
        )
        
        # Small text
        small_text = "Hello world"
        assert not needs_chunking(small_text, "gpt-4o-mini")
        
        # Large text
        large_text = "word " * 100000
        assert needs_chunking(large_text, "gpt-4o-mini")
    
    def test_chunk_size_recommendation(self):
        """Test getting recommended chunk size for a model."""
        from praisonaiagents.eval.tokens import get_recommended_chunk_size
        
        # For 128K context model, chunk size should be reasonable
        chunk_size = get_recommended_chunk_size("gpt-4o-mini")
        assert 4000 <= chunk_size <= 16000
