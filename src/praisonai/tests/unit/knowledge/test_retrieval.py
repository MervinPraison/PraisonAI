"""
Unit tests for Retrieval Strategy Patterns.
"""

from praisonaiagents.knowledge.retrieval import (
    RetrievalResult,
    RetrievalStrategy,
    get_retriever_registry,
    reciprocal_rank_fusion,
    merge_adjacent_chunks,
)


class TestRetrievalResult:
    """Tests for RetrievalResult dataclass."""
    
    def test_result_creation(self):
        """Test basic result creation."""
        result = RetrievalResult(text="Hello world", score=0.95)
        assert result.text == "Hello world"
        assert result.score == 0.95
        assert result.metadata == {}
        assert result.doc_id is None
    
    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = RetrievalResult(
            text="Test content",
            score=0.8,
            metadata={"source": "test.txt"},
            doc_id="doc-1",
            chunk_index=2
        )
        assert result.metadata["source"] == "test.txt"
        assert result.doc_id == "doc-1"
        assert result.chunk_index == 2
    
    def test_result_to_dict(self):
        """Test result serialization."""
        result = RetrievalResult(
            text="Test",
            score=0.9,
            doc_id="doc-1"
        )
        d = result.to_dict()
        assert d["text"] == "Test"
        assert d["score"] == 0.9
        assert d["doc_id"] == "doc-1"


class TestRetrievalStrategy:
    """Tests for RetrievalStrategy enum."""
    
    def test_strategy_values(self):
        """Test strategy enum values."""
        assert RetrievalStrategy.BASIC == "basic"
        assert RetrievalStrategy.FUSION == "fusion"
        assert RetrievalStrategy.RECURSIVE == "recursive"
        assert RetrievalStrategy.AUTO_MERGE == "auto_merge"
        assert RetrievalStrategy.HYBRID == "hybrid"
    
    def test_strategy_from_string(self):
        """Test creating strategy from string."""
        assert RetrievalStrategy("basic") == RetrievalStrategy.BASIC
        assert RetrievalStrategy("fusion") == RetrievalStrategy.FUSION


class TestReciprocalRankFusion:
    """Tests for RRF algorithm."""
    
    def test_single_list(self):
        """Test RRF with single result list."""
        results = [
            RetrievalResult(text="A", score=0.9, doc_id="1"),
            RetrievalResult(text="B", score=0.8, doc_id="2"),
        ]
        
        fused = reciprocal_rank_fusion([results])
        assert len(fused) == 2
        assert fused[0].doc_id == "1"  # First in original list
    
    def test_multiple_lists(self):
        """Test RRF with multiple result lists."""
        list1 = [
            RetrievalResult(text="A", score=0.9, doc_id="1"),
            RetrievalResult(text="B", score=0.8, doc_id="2"),
        ]
        list2 = [
            RetrievalResult(text="B", score=0.95, doc_id="2"),
            RetrievalResult(text="C", score=0.7, doc_id="3"),
        ]
        
        fused = reciprocal_rank_fusion([list1, list2])
        
        # B appears in both lists, should rank higher
        assert len(fused) == 3
        doc_ids = [r.doc_id for r in fused]
        assert "2" in doc_ids  # B should be present
    
    def test_empty_lists(self):
        """Test RRF with empty lists."""
        fused = reciprocal_rank_fusion([])
        assert fused == []
        
        fused = reciprocal_rank_fusion([[]])
        assert fused == []
    
    def test_rrf_scores(self):
        """Test that RRF scores are calculated correctly."""
        list1 = [
            RetrievalResult(text="A", score=0.9, doc_id="1"),
        ]
        list2 = [
            RetrievalResult(text="A", score=0.8, doc_id="1"),
        ]
        
        fused = reciprocal_rank_fusion([list1, list2], k=60)
        
        # A appears first in both lists, RRF score = 2 * (1 / (60 + 1))
        expected_score = 2 * (1 / 61)
        assert len(fused) == 1
        assert abs(fused[0].score - expected_score) < 0.001


class TestMergeAdjacentChunks:
    """Tests for chunk merging."""
    
    def test_no_merge_needed(self):
        """Test when no merging is needed."""
        results = [
            RetrievalResult(text="A", score=0.9, doc_id="1", chunk_index=0),
            RetrievalResult(text="B", score=0.8, doc_id="2", chunk_index=0),
        ]
        
        merged = merge_adjacent_chunks(results)
        assert len(merged) == 2
    
    def test_merge_adjacent(self):
        """Test merging adjacent chunks from same document."""
        results = [
            RetrievalResult(text="Part 1", score=0.9, doc_id="1", chunk_index=0),
            RetrievalResult(text="Part 2", score=0.8, doc_id="1", chunk_index=1),
            RetrievalResult(text="Other", score=0.7, doc_id="2", chunk_index=0),
        ]
        
        merged = merge_adjacent_chunks(results, max_gap=1)
        
        # Should merge chunks 0 and 1 from doc 1
        assert len(merged) == 2
        
        # Find the merged result
        merged_doc1 = [r for r in merged if r.doc_id == "1"][0]
        assert "Part 1" in merged_doc1.text
        assert "Part 2" in merged_doc1.text
    
    def test_no_merge_with_gap(self):
        """Test no merging when gap is too large."""
        results = [
            RetrievalResult(text="Part 1", score=0.9, doc_id="1", chunk_index=0),
            RetrievalResult(text="Part 5", score=0.8, doc_id="1", chunk_index=5),
        ]
        
        merged = merge_adjacent_chunks(results, max_gap=1)
        assert len(merged) == 2  # Not merged due to gap
    
    def test_empty_results(self):
        """Test with empty results."""
        merged = merge_adjacent_chunks([])
        assert merged == []
    
    def test_no_chunk_index(self):
        """Test results without chunk index."""
        results = [
            RetrievalResult(text="A", score=0.9, doc_id="1"),
            RetrievalResult(text="B", score=0.8, doc_id="1"),
        ]
        
        merged = merge_adjacent_chunks(results)
        assert len(merged) == 2  # Can't merge without chunk index


class TestRetrieverRegistry:
    """Tests for RetrieverRegistry."""
    
    def test_list_retrievers(self):
        """Test listing retrievers."""
        registry = get_retriever_registry()
        retrievers = registry.list_retrievers()
        assert isinstance(retrievers, list)
    
    def test_get_nonexistent_retriever(self):
        """Test getting non-existent retriever."""
        registry = get_retriever_registry()
        assert registry.get("nonexistent") is None
    
    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = get_retriever_registry()
        registry2 = get_retriever_registry()
        assert registry1 is registry2
