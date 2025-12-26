"""
Unit tests for Reranker Protocol and Registry.
"""

from praisonaiagents.knowledge.rerankers import (
    RerankResult,
    get_reranker_registry,
    SimpleReranker,
)


class TestRerankResult:
    """Tests for RerankResult dataclass."""
    
    def test_result_creation(self):
        """Test basic result creation."""
        result = RerankResult(text="Hello world", score=0.95, original_index=0)
        assert result.text == "Hello world"
        assert result.score == 0.95
        assert result.original_index == 0
        assert result.metadata == {}
    
    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = RerankResult(
            text="Test content",
            score=0.8,
            original_index=1,
            metadata={"source": "test.txt"}
        )
        assert result.metadata["source"] == "test.txt"


class TestSimpleReranker:
    """Tests for SimpleReranker."""
    
    def test_rerank_basic(self):
        """Test basic reranking."""
        reranker = SimpleReranker()
        documents = [
            "The quick brown fox jumps over the lazy dog",
            "Python is a programming language",
            "Machine learning with neural networks"
        ]
        
        results = reranker.rerank("fox dog", documents)
        
        assert len(results) == 3
        # First document should score highest (contains fox and dog)
        assert results[0].text == documents[0]
    
    def test_rerank_with_top_k(self):
        """Test reranking with top_k limit."""
        reranker = SimpleReranker()
        documents = ["Doc A", "Doc B", "Doc C", "Doc D"]
        
        results = reranker.rerank("Doc", documents, top_k=2)
        
        assert len(results) == 2
    
    def test_rerank_preserves_original_index(self):
        """Test that original index is preserved."""
        reranker = SimpleReranker()
        documents = ["First", "Second", "Third"]
        
        results = reranker.rerank("Second", documents)
        
        # Find the result for "Second"
        second_result = [r for r in results if r.text == "Second"][0]
        assert second_result.original_index == 1
    
    def test_rerank_empty_documents(self):
        """Test reranking with empty documents."""
        reranker = SimpleReranker()
        results = reranker.rerank("query", [])
        assert results == []
    
    def test_rerank_empty_query(self):
        """Test reranking with empty query."""
        reranker = SimpleReranker()
        documents = ["Doc A", "Doc B"]
        
        results = reranker.rerank("", documents)
        
        assert len(results) == 2
        # All should have score 0 with empty query
        for r in results:
            assert r.score == 0.0
    
    def test_arerank_async(self):
        """Test async reranking."""
        import asyncio
        
        reranker = SimpleReranker()
        documents = ["Hello world", "Goodbye world"]
        
        async def run_test():
            results = await reranker.arerank("Hello", documents)
            return results
        
        results = asyncio.run(run_test())
        assert len(results) == 2


class TestRerankerRegistry:
    """Tests for RerankerRegistry."""
    
    def test_simple_reranker_registered(self):
        """Test that simple reranker is registered by default."""
        registry = get_reranker_registry()
        assert "simple" in registry.list_rerankers()
    
    def test_get_simple_reranker(self):
        """Test getting simple reranker."""
        registry = get_reranker_registry()
        reranker = registry.get("simple")
        assert reranker is not None
        assert reranker.name == "simple"
    
    def test_get_nonexistent_reranker(self):
        """Test getting non-existent reranker."""
        registry = get_reranker_registry()
        assert registry.get("nonexistent") is None
    
    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = get_reranker_registry()
        registry2 = get_reranker_registry()
        assert registry1 is registry2
