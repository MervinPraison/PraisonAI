"""
Unit tests for SmartRetriever (Phase 4).
"""


class TestSmartRetriever:
    """Tests for SmartRetriever class."""
    
    def test_import_smart_retriever(self):
        """SmartRetriever should be importable."""
        from praisonaiagents.rag.retriever import SmartRetriever
        assert SmartRetriever is not None
    
    def test_retrieval_result_dataclass(self):
        """RetrievalResult should be a proper dataclass."""
        from praisonaiagents.rag.retriever import RetrievalResult
        
        result = RetrievalResult()
        assert result.chunks == []
        assert result.total_found == 0
        assert result.strategy_used == "basic"
        assert result.reranked is False
    
    def test_retriever_without_knowledge(self):
        """SmartRetriever should handle missing knowledge gracefully."""
        from praisonaiagents.rag.retriever import SmartRetriever
        
        retriever = SmartRetriever()
        result = retriever.retrieve("test query")
        
        assert result.chunks == []
        assert result.total_found == 0
    
    def test_normalize_results(self):
        """SmartRetriever should normalize various result formats."""
        from praisonaiagents.rag.retriever import SmartRetriever
        
        retriever = SmartRetriever()
        
        # Test dict with results key
        results = {"results": [{"text": "hello", "score": 0.9}]}
        normalized = retriever._normalize_results(results)
        assert len(normalized) == 1
        assert normalized[0]["text"] == "hello"
        
        # Test list
        results = [{"text": "world", "metadata": {"source": "test"}}]
        normalized = retriever._normalize_results(results)
        assert len(normalized) == 1
        assert normalized[0]["text"] == "world"
    
    def test_apply_filters_include(self):
        """SmartRetriever should filter by include patterns."""
        from praisonaiagents.rag.retriever import SmartRetriever
        
        retriever = SmartRetriever()
        chunks = [
            {"text": "Python code", "metadata": {"filename": "main.py"}},
            {"text": "JavaScript", "metadata": {"filename": "app.js"}},
        ]
        
        filtered = retriever._apply_filters(chunks, include_glob=["*.py"])
        assert len(filtered) == 1
        assert filtered[0]["metadata"]["filename"] == "main.py"
    
    def test_apply_filters_exclude(self):
        """SmartRetriever should filter by exclude patterns."""
        from praisonaiagents.rag.retriever import SmartRetriever
        
        retriever = SmartRetriever()
        chunks = [
            {"text": "Python code", "metadata": {"filename": "main.py"}},
            {"text": "Test code", "metadata": {"filename": "test_main.py"}},
        ]
        
        filtered = retriever._apply_filters(chunks, exclude_glob=["test_*.py"])
        assert len(filtered) == 1
        assert filtered[0]["metadata"]["filename"] == "main.py"


class TestSimpleReranker:
    """Tests for SimpleReranker class."""
    
    def test_import_simple_reranker(self):
        """SimpleReranker should be importable."""
        from praisonaiagents.rag.retriever import SimpleReranker
        assert SimpleReranker is not None
    
    def test_rerank_by_overlap(self):
        """SimpleReranker should rerank by keyword overlap."""
        from praisonaiagents.rag.retriever import SimpleReranker
        
        reranker = SimpleReranker()
        results = [
            {"text": "unrelated content", "score": 0.5},
            {"text": "python programming language", "score": 0.5},
        ]
        
        reranked = reranker.rerank("python programming", results)
        
        # The one with more overlap should be first (same base score, overlap decides)
        assert "python" in reranked[0]["text"].lower()
    
    def test_rerank_top_k(self):
        """SimpleReranker should respect top_k."""
        from praisonaiagents.rag.retriever import SimpleReranker
        
        reranker = SimpleReranker()
        results = [
            {"text": "a", "score": 0.1},
            {"text": "b", "score": 0.2},
            {"text": "c", "score": 0.3},
        ]
        
        reranked = reranker.rerank("test", results, top_k=2)
        assert len(reranked) == 2


class TestRetrieverProtocol:
    """Tests for RetrieverProtocol."""
    
    def test_protocol_exists(self):
        """RetrieverProtocol should be importable."""
        from praisonaiagents.rag.retriever import RetrieverProtocol
        assert RetrieverProtocol is not None
    
    def test_reranker_protocol_exists(self):
        """RerankerProtocol should be importable."""
        from praisonaiagents.rag.retriever import RerankerProtocol
        assert RerankerProtocol is not None
