"""
Unit tests for Index Type Selection.
"""

from praisonaiagents.knowledge.index import (
    IndexType,
    IndexStats,
    get_index_registry,
    KeywordIndex,
)


class TestIndexType:
    """Tests for IndexType enum."""
    
    def test_index_type_values(self):
        """Test index type enum values."""
        assert IndexType.VECTOR == "vector"
        assert IndexType.KEYWORD == "keyword"
        assert IndexType.HYBRID == "hybrid"
        assert IndexType.GRAPH == "graph"
    
    def test_index_type_from_string(self):
        """Test creating index type from string."""
        assert IndexType("vector") == IndexType.VECTOR
        assert IndexType("keyword") == IndexType.KEYWORD


class TestIndexStats:
    """Tests for IndexStats dataclass."""
    
    def test_stats_creation(self):
        """Test basic stats creation."""
        stats = IndexStats(
            index_type=IndexType.VECTOR,
            document_count=100,
            chunk_count=500
        )
        assert stats.index_type == IndexType.VECTOR
        assert stats.document_count == 100
        assert stats.chunk_count == 500
        assert stats.total_tokens == 0
    
    def test_stats_with_metadata(self):
        """Test stats with metadata."""
        stats = IndexStats(
            index_type=IndexType.KEYWORD,
            document_count=50,
            chunk_count=200,
            total_tokens=10000,
            metadata={"unique_terms": 5000}
        )
        assert stats.total_tokens == 10000
        assert stats.metadata["unique_terms"] == 5000


class TestKeywordIndex:
    """Tests for KeywordIndex (BM25)."""
    
    def test_add_documents(self):
        """Test adding documents."""
        index = KeywordIndex()
        ids = index.add_documents(
            texts=["Hello world", "Goodbye world"],
        )
        assert len(ids) == 2
        
        stats = index.stats()
        assert stats.document_count == 2
    
    def test_add_with_metadata(self):
        """Test adding documents with metadata."""
        index = KeywordIndex()
        index.add_documents(
            texts=["Test document"],
            metadatas=[{"source": "test.txt"}]
        )
        
        results = index.query("Test")
        assert len(results) > 0
        assert results[0]["metadata"]["source"] == "test.txt"
    
    def test_query_basic(self):
        """Test basic querying."""
        index = KeywordIndex()
        index.add_documents(
            texts=[
                "The quick brown fox jumps over the lazy dog",
                "Python is a programming language",
                "Machine learning with neural networks"
            ]
        )
        
        results = index.query("fox dog")
        
        assert len(results) > 0
        # First result should be about fox and dog
        assert "fox" in results[0]["text"].lower() or "dog" in results[0]["text"].lower()
    
    def test_query_with_top_k(self):
        """Test querying with top_k limit."""
        index = KeywordIndex()
        index.add_documents(
            texts=["Doc A", "Doc B", "Doc C", "Doc D"]
        )
        
        results = index.query("Doc", top_k=2)
        assert len(results) == 2
    
    def test_query_with_filter(self):
        """Test querying with metadata filter."""
        index = KeywordIndex()
        index.add_documents(
            texts=["Doc A", "Doc B", "Doc C"],
            metadatas=[
                {"type": "a"},
                {"type": "b"},
                {"type": "a"}
            ]
        )
        
        results = index.query("Doc", filter={"type": "a"})
        
        assert len(results) == 2
        for r in results:
            assert r["metadata"]["type"] == "a"
    
    def test_delete_by_ids(self):
        """Test deleting by IDs."""
        index = KeywordIndex()
        ids = index.add_documents(
            texts=["A", "B", "C"]
        )
        
        deleted = index.delete(ids=[ids[0], ids[1]])
        assert deleted == 2
        
        stats = index.stats()
        assert stats.document_count == 1
    
    def test_delete_all(self):
        """Test deleting all documents."""
        index = KeywordIndex()
        index.add_documents(texts=["A", "B", "C"])
        
        deleted = index.delete(delete_all=True)
        assert deleted == 3
        
        stats = index.stats()
        assert stats.document_count == 0
    
    def test_delete_by_filter(self):
        """Test deleting by filter."""
        index = KeywordIndex()
        index.add_documents(
            texts=["A", "B", "C"],
            metadatas=[{"keep": True}, {"keep": False}, {"keep": True}]
        )
        
        deleted = index.delete(filter={"keep": False})
        assert deleted == 1
        
        stats = index.stats()
        assert stats.document_count == 2
    
    def test_stats(self):
        """Test getting index statistics."""
        index = KeywordIndex()
        index.add_documents(
            texts=["Hello world", "Test document"]
        )
        
        stats = index.stats()
        
        assert stats.index_type == IndexType.KEYWORD
        assert stats.document_count == 2
        assert stats.chunk_count == 2
        assert stats.total_tokens > 0
        assert "unique_terms" in stats.metadata
    
    def test_bm25_scoring(self):
        """Test BM25 scoring behavior."""
        index = KeywordIndex()
        index.add_documents(
            texts=[
                "apple apple apple",  # High TF for apple
                "apple banana",       # Lower TF for apple
                "banana banana"       # No apple
            ]
        )
        
        results = index.query("apple")
        
        # First result should have highest score (most apples)
        assert results[0]["text"] == "apple apple apple"
        # Last result should have lowest score (no apples)
        assert results[-1]["text"] == "banana banana"


class TestIndexRegistry:
    """Tests for IndexRegistry."""
    
    def test_keyword_index_registered(self):
        """Test that keyword index is registered by default."""
        registry = get_index_registry()
        assert "keyword" in registry.list_indices()
    
    def test_get_keyword_index(self):
        """Test getting keyword index."""
        registry = get_index_registry()
        index = registry.get("keyword")
        assert index is not None
        assert index.index_type == IndexType.KEYWORD
    
    def test_get_nonexistent_index(self):
        """Test getting non-existent index."""
        registry = get_index_registry()
        assert registry.get("nonexistent") is None
    
    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = get_index_registry()
        registry2 = get_index_registry()
        assert registry1 is registry2
