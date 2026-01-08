"""
Unit tests for ContextCompressor (Phase 5).
"""


class TestContextCompressor:
    """Tests for ContextCompressor class."""
    
    def test_import_context_compressor(self):
        """ContextCompressor should be importable."""
        from praisonaiagents.rag.compressor import ContextCompressor
        assert ContextCompressor is not None
    
    def test_compression_result_dataclass(self):
        """CompressionResult should be a proper dataclass."""
        from praisonaiagents.rag.compressor import CompressionResult
        
        result = CompressionResult()
        assert result.chunks == []
        assert result.original_tokens == 0
        assert result.compressed_tokens == 0
        assert result.compression_ratio == 1.0
    
    def test_compress_empty_chunks(self):
        """ContextCompressor should handle empty chunks."""
        from praisonaiagents.rag.compressor import ContextCompressor
        
        compressor = ContextCompressor()
        result = compressor.compress([], "test query", 1000)
        
        assert result.chunks == []
        assert result.original_tokens == 0
    
    def test_deduplicate_chunks(self):
        """ContextCompressor should deduplicate similar chunks."""
        from praisonaiagents.rag.compressor import ContextCompressor
        
        compressor = ContextCompressor()
        chunks = [
            {"text": "This is duplicate content"},
            {"text": "This is duplicate content"},
            {"text": "This is unique content"},
        ]
        
        deduped = compressor._deduplicate(chunks)
        assert len(deduped) == 2
    
    def test_extract_relevant_sentences(self):
        """ContextCompressor should extract query-relevant sentences."""
        from praisonaiagents.rag.compressor import ContextCompressor
        
        compressor = ContextCompressor()
        chunks = [
            {"text": "Python is great. JavaScript is also good. Python has many libraries."},
        ]
        
        extracted = compressor._extract_relevant(chunks, "Python libraries")
        assert len(extracted) == 1
        assert "Python" in extracted[0]["text"]
    
    def test_truncate_to_budget(self):
        """ContextCompressor should truncate to fit budget."""
        from praisonaiagents.rag.compressor import ContextCompressor
        
        compressor = ContextCompressor()
        chunks = [
            {"text": "A" * 1000},  # ~250 tokens
            {"text": "B" * 1000},  # ~250 tokens
        ]
        
        truncated = compressor._truncate_to_budget(chunks, 300)
        
        # Should fit within budget
        total_tokens = sum(len(c["text"]) // 4 + 1 for c in truncated)
        assert total_tokens <= 350  # Some buffer for truncation
    
    def test_compress_full_pipeline(self):
        """ContextCompressor should run full compression pipeline."""
        from praisonaiagents.rag.compressor import ContextCompressor
        
        compressor = ContextCompressor()
        chunks = [
            {"text": "Python programming is powerful. It has many uses."},
            {"text": "Python programming is powerful. It has many uses."},  # Duplicate
            {"text": "JavaScript is for web development."},
        ]
        
        result = compressor.compress(chunks, "Python", 500)
        
        assert result.method_used == "dedupe+extract+truncate"
        assert result.original_tokens > 0
        assert len(result.chunks) <= 2  # Duplicate removed


class TestEstimateTokens:
    """Tests for token estimation."""
    
    def test_estimate_tokens_function(self):
        """estimate_tokens should estimate correctly."""
        from praisonaiagents.rag.compressor import estimate_tokens
        
        assert estimate_tokens("") == 0
        assert estimate_tokens("hello") == 2  # 5/4 + 1 = 2
        assert estimate_tokens("a" * 100) == 26  # 100/4 + 1 = 26
