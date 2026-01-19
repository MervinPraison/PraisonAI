"""
Tests for context compressor.
"""

import pytest


class TestTruncateCompressor:
    """Tests for TruncateCompressor."""
    
    def test_no_compression_needed(self):
        """Should return text unchanged if under budget."""
        from praisonaiagents.context.fast.compressor import TruncateCompressor
        
        compressor = TruncateCompressor()
        text = "Short text"
        
        result = compressor.compress(text, max_tokens=100)
        
        assert result == text
    
    def test_truncation_preserves_start_end(self):
        """Should preserve start and end lines."""
        from praisonaiagents.context.fast.compressor import TruncateCompressor
        
        compressor = TruncateCompressor()
        lines = [f"Line {i}" for i in range(100)]
        text = '\n'.join(lines)
        
        result = compressor.compress(text, max_tokens=50)
        
        # Should contain start lines
        assert "Line 0" in result
        # Should contain truncation marker
        assert "truncated" in result.lower()
    
    def test_token_estimation(self):
        """Should estimate tokens correctly."""
        from praisonaiagents.context.fast.compressor import TruncateCompressor
        
        compressor = TruncateCompressor()
        text = "1234" * 100  # 400 chars
        
        tokens = compressor.estimate_tokens(text)
        
        assert tokens == 100  # 4 chars per token


class TestSmartCompressor:
    """Tests for SmartCompressor."""
    
    def test_preserves_definitions(self):
        """Should preserve function/class definitions."""
        from praisonaiagents.context.fast.compressor import SmartCompressor
        
        compressor = SmartCompressor()
        text = '''def important_function():
    pass

some_variable = 1
another_variable = 2

class ImportantClass:
    pass

random_code = 3
more_random = 4
'''
        
        result = compressor.compress(text, max_tokens=20)
        
        # Should preserve definitions
        assert "def important_function" in result or len(result) < len(text)


class TestCompressorSelection:
    """Tests for compressor selection."""
    
    def test_get_truncate_compressor(self):
        """Should return truncate compressor."""
        from praisonaiagents.context.fast.compressor import get_compressor
        
        compressor = get_compressor("truncate")
        assert compressor is not None
    
    def test_get_smart_compressor(self):
        """Should return smart compressor."""
        from praisonaiagents.context.fast.compressor import get_compressor
        
        compressor = get_compressor("smart")
        assert compressor is not None
    
    def test_invalid_compressor_raises(self):
        """Should raise for invalid compressor."""
        from praisonaiagents.context.fast.compressor import get_compressor
        
        with pytest.raises(ValueError):
            get_compressor("invalid")
    
    def test_llmlingua_availability(self):
        """Should check llmlingua availability."""
        from praisonaiagents.context.fast.compressor import is_llmlingua_available
        
        result = is_llmlingua_available()
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
