"""
Unit tests for RAG context builder normalization.

Tests that metadata=None from mem0 is handled correctly.
"""

from praisonaiagents.rag.context import (
    deduplicate_chunks,
    build_context,
)


class TestDeduplicateChunksNormalization:
    """Tests for deduplicate_chunks handling of None metadata."""
    
    def test_handles_metadata_none(self):
        """Test that metadata=None doesn't crash deduplicate_chunks."""
        results = [
            {"id": "1", "text": "content 1", "metadata": None},
            {"id": "2", "text": "content 2", "metadata": {"source": "test.txt"}},
        ]
        # Should not raise AttributeError
        deduped = deduplicate_chunks(results)
        assert len(deduped) == 2
    
    def test_handles_none_results(self):
        """Test that None items in list are filtered."""
        results = [
            {"id": "1", "text": "content 1", "metadata": None},
            None,
            {"id": "2", "text": "content 2", "metadata": {}},
        ]
        deduped = deduplicate_chunks(results)
        assert len(deduped) == 2
    
    def test_handles_mem0_format(self):
        """Test handling of mem0 'memory' field."""
        results = [
            {"id": "1", "memory": "mem0 content", "metadata": None},
        ]
        deduped = deduplicate_chunks(results)
        assert len(deduped) == 1


class TestBuildContextNormalization:
    """Tests for build_context handling of None metadata."""
    
    def test_handles_metadata_none(self):
        """Test that metadata=None doesn't crash build_context."""
        results = [
            {"id": "1", "text": "content 1", "metadata": None},
            {"id": "2", "text": "content 2", "metadata": {"source": "test.txt"}},
        ]
        # Should not raise AttributeError
        context, used = build_context(results)
        assert len(used) == 2
        assert "content 1" in context
        assert "content 2" in context
    
    def test_handles_none_results(self):
        """Test that None items in list are filtered."""
        results = [
            {"id": "1", "text": "content 1", "metadata": None},
            None,
            {"id": "2", "text": "content 2", "metadata": {}},
        ]
        context, used = build_context(results)
        assert len(used) == 2
    
    def test_handles_mem0_format(self):
        """Test handling of mem0 'memory' field."""
        results = [
            {"id": "1", "memory": "mem0 content", "metadata": None, "score": 0.9},
        ]
        context, used = build_context(results)
        assert len(used) == 1
        assert "mem0 content" in context
    
    def test_source_extraction_with_none_metadata(self):
        """Test source extraction when metadata is None."""
        results = [
            {"id": "1", "text": "content", "metadata": None},
        ]
        context, used = build_context(results, include_source=True)
        # Should use default source label
        assert "Source 1" in context or "content" in context
    
    def test_source_extraction_with_metadata(self):
        """Test source extraction when metadata has source."""
        results = [
            {"id": "1", "text": "content", "metadata": {"source": "doc.pdf"}},
        ]
        context, used = build_context(results, include_source=True)
        assert "doc.pdf" in context


class TestEdgeCases:
    """Test edge cases for robustness."""
    
    def test_empty_results(self):
        """Test empty results list."""
        context, used = build_context([])
        assert context == ""
        assert used == []
    
    def test_all_none_results(self):
        """Test list with all None items."""
        results = [None, None, None]
        deduped = deduplicate_chunks(results)
        assert deduped == []
        
        context, used = build_context(results)
        assert context == ""
        assert used == []
    
    def test_empty_text_filtered(self):
        """Test that empty text items are filtered in build_context."""
        results = [
            {"id": "1", "text": "", "metadata": None},
            {"id": "2", "text": "valid content", "metadata": None},
        ]
        context, used = build_context(results)
        assert len(used) == 1
        assert "valid content" in context
