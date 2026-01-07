"""Tests for RAG context building utilities."""


class TestEstimateTokens:
    """Tests for token estimation."""
    
    def test_estimate_tokens_short(self):
        """Test token estimation for short text."""
        from praisonaiagents.rag.context import _estimate_tokens
        
        tokens = _estimate_tokens("Hello world")
        assert tokens >= 2  # At least 2 tokens for 2 words
    
    def test_estimate_tokens_empty(self):
        """Test token estimation for empty string."""
        from praisonaiagents.rag.context import _estimate_tokens
        
        tokens = _estimate_tokens("")
        assert tokens == 1  # Minimum 1


class TestChunkHash:
    """Tests for chunk hashing."""
    
    def test_chunk_hash_deterministic(self):
        """Test that hash is deterministic."""
        from praisonaiagents.rag.context import _chunk_hash
        
        hash1 = _chunk_hash("test content", "source.pdf")
        hash2 = _chunk_hash("test content", "source.pdf")
        assert hash1 == hash2
    
    def test_chunk_hash_different_content(self):
        """Test that different content produces different hash."""
        from praisonaiagents.rag.context import _chunk_hash
        
        hash1 = _chunk_hash("content A", "source.pdf")
        hash2 = _chunk_hash("content B", "source.pdf")
        assert hash1 != hash2
    
    def test_chunk_hash_different_source(self):
        """Test that different source produces different hash."""
        from praisonaiagents.rag.context import _chunk_hash
        
        hash1 = _chunk_hash("same content", "source1.pdf")
        hash2 = _chunk_hash("same content", "source2.pdf")
        assert hash1 != hash2


class TestDeduplicateChunks:
    """Tests for chunk deduplication."""
    
    def test_deduplicate_empty(self):
        """Test deduplication of empty list."""
        from praisonaiagents.rag.context import deduplicate_chunks
        
        result = deduplicate_chunks([])
        assert result == []
    
    def test_deduplicate_no_duplicates(self):
        """Test deduplication with no duplicates."""
        from praisonaiagents.rag.context import deduplicate_chunks
        
        results = [
            {"text": "Content A", "metadata": {"source": "a.pdf"}},
            {"text": "Content B", "metadata": {"source": "b.pdf"}},
        ]
        deduped = deduplicate_chunks(results)
        assert len(deduped) == 2
    
    def test_deduplicate_with_duplicates(self):
        """Test deduplication removes duplicates."""
        from praisonaiagents.rag.context import deduplicate_chunks
        
        results = [
            {"text": "Same content", "metadata": {"source": "a.pdf"}},
            {"text": "Same content", "metadata": {"source": "a.pdf"}},
            {"text": "Different", "metadata": {"source": "b.pdf"}},
        ]
        deduped = deduplicate_chunks(results)
        assert len(deduped) == 2
    
    def test_deduplicate_memory_format(self):
        """Test deduplication with 'memory' key instead of 'text'."""
        from praisonaiagents.rag.context import deduplicate_chunks
        
        results = [
            {"memory": "Content A", "metadata": {}},
            {"memory": "Content A", "metadata": {}},
        ]
        deduped = deduplicate_chunks(results)
        assert len(deduped) == 1


class TestTruncateContext:
    """Tests for context truncation."""
    
    def test_truncate_short_text(self):
        """Test that short text is not truncated."""
        from praisonaiagents.rag.context import truncate_context
        
        text = "Short text"
        result = truncate_context(text, max_tokens=100)
        assert result == text
    
    def test_truncate_long_text(self):
        """Test that long text is truncated."""
        from praisonaiagents.rag.context import truncate_context
        
        text = "A" * 10000  # Very long text
        result = truncate_context(text, max_tokens=100)
        assert len(result) < len(text)
        assert "[Context truncated...]" in result
    
    def test_truncate_custom_suffix(self):
        """Test truncation with custom suffix."""
        from praisonaiagents.rag.context import truncate_context
        
        text = "A" * 10000
        result = truncate_context(text, max_tokens=100, suffix="...")
        assert result.endswith("...")


class TestBuildContext:
    """Tests for context building."""
    
    def test_build_context_empty(self):
        """Test building context from empty results."""
        from praisonaiagents.rag.context import build_context
        
        context, used = build_context([])
        assert context == ""
        assert used == []
    
    def test_build_context_single(self):
        """Test building context from single result."""
        from praisonaiagents.rag.context import build_context
        
        results = [{"text": "Content here", "metadata": {"filename": "doc.pdf"}}]
        context, used = build_context(results)
        
        assert "Content here" in context
        assert "doc.pdf" in context
        assert len(used) == 1
    
    def test_build_context_multiple(self):
        """Test building context from multiple results."""
        from praisonaiagents.rag.context import build_context
        
        results = [
            {"text": "First chunk", "metadata": {"filename": "a.pdf"}},
            {"text": "Second chunk", "metadata": {"filename": "b.pdf"}},
        ]
        context, used = build_context(results, separator="\n---\n")
        
        assert "First chunk" in context
        assert "Second chunk" in context
        assert len(used) == 2
    
    def test_build_context_respects_token_limit(self):
        """Test that context respects token limit."""
        from praisonaiagents.rag.context import build_context
        
        # Create results that exceed token limit
        results = [
            {"text": "A" * 1000, "metadata": {}},
            {"text": "B" * 1000, "metadata": {}},
            {"text": "C" * 1000, "metadata": {}},
        ]
        context, used = build_context(results, max_tokens=500)
        
        # Should not include all results
        assert len(used) < 3
    
    def test_build_context_deduplicates(self):
        """Test that context deduplicates by default."""
        from praisonaiagents.rag.context import build_context
        
        results = [
            {"text": "Same content", "metadata": {"source": "a.pdf"}},
            {"text": "Same content", "metadata": {"source": "a.pdf"}},
        ]
        context, used = build_context(results, deduplicate=True)
        
        # Should only include once
        assert context.count("Same content") == 1
    
    def test_build_context_no_source(self):
        """Test building context without source info."""
        from praisonaiagents.rag.context import build_context
        
        results = [{"text": "Content", "metadata": {}}]
        context, used = build_context(results, include_source=False)
        
        assert "Content" in context
        assert "[" not in context  # No source label


class TestDefaultContextBuilder:
    """Tests for DefaultContextBuilder class."""
    
    def test_default_builder_build(self):
        """Test DefaultContextBuilder.build method."""
        from praisonaiagents.rag.context import DefaultContextBuilder
        
        builder = DefaultContextBuilder()
        results = [{"text": "Test content", "metadata": {"filename": "test.pdf"}}]
        
        context = builder.build(results, max_tokens=1000)
        
        assert "Test content" in context
        assert "test.pdf" in context
    
    def test_default_builder_custom_separator(self):
        """Test DefaultContextBuilder with custom separator."""
        from praisonaiagents.rag.context import DefaultContextBuilder
        
        builder = DefaultContextBuilder(separator="\n\n")
        results = [
            {"text": "A", "metadata": {}},
            {"text": "B", "metadata": {}},
        ]
        
        context = builder.build(results)
        assert "\n\n" in context
