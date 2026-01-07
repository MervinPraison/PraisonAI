"""
Tests for reranking functionality in RAG pipeline.

Verifies that reranking is properly wired through RAGConfig and RAG pipeline.
"""

from unittest.mock import MagicMock


class TestRAGConfigRerank:
    """Tests for rerank configuration in RAGConfig."""
    
    def test_rag_config_has_rerank_field(self):
        """Test that RAGConfig has rerank field."""
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig()
        
        assert hasattr(config, "rerank")
        assert config.rerank is False  # Default
    
    def test_rag_config_has_rerank_top_k_field(self):
        """Test that RAGConfig has rerank_top_k field."""
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig()
        
        assert hasattr(config, "rerank_top_k")
        assert config.rerank_top_k == 3  # Default
    
    def test_rag_config_rerank_enabled(self):
        """Test enabling rerank in RAGConfig."""
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig(rerank=True, rerank_top_k=5)
        
        assert config.rerank is True
        assert config.rerank_top_k == 5
    
    def test_rag_config_to_dict_includes_rerank(self):
        """Test that to_dict includes rerank fields."""
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig(rerank=True, rerank_top_k=10)
        config_dict = config.to_dict()
        
        assert config_dict["rerank"] is True
        assert config_dict["rerank_top_k"] == 10
    
    def test_rag_config_from_dict_includes_rerank(self):
        """Test that from_dict parses rerank fields."""
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig.from_dict({
            "rerank": True,
            "rerank_top_k": 7,
        })
        
        assert config.rerank is True
        assert config.rerank_top_k == 7


class TestRAGPipelineRerank:
    """Tests for reranking in RAG pipeline."""
    
    def test_rag_pipeline_accepts_reranker(self):
        """Test that RAG pipeline accepts reranker parameter."""
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        mock_reranker = MagicMock()
        
        rag = RAG(knowledge=mock_knowledge, reranker=mock_reranker)
        
        assert rag.reranker is mock_reranker
    
    def test_rag_pipeline_has_rerank_method(self):
        """Test that RAG pipeline has _rerank method."""
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        rag = RAG(knowledge=mock_knowledge)
        
        assert hasattr(rag, "_rerank")
        assert callable(rag._rerank)
    
    def test_rag_pipeline_rerank_skipped_when_disabled(self):
        """Test that reranking is skipped when config.rerank is False."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        mock_reranker = MagicMock()
        config = RAGConfig(rerank=False)
        
        rag = RAG(knowledge=mock_knowledge, config=config, reranker=mock_reranker)
        
        results = [{"text": "test", "score": 0.9}]
        reranked = rag._rerank("query", results)
        
        # Should return original results without calling reranker
        assert reranked == results
        mock_reranker.rerank.assert_not_called()
    
    def test_rag_pipeline_rerank_called_when_enabled(self):
        """Test that reranking is called when config.rerank is True."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [{"text": "reranked", "score": 0.95}]
        config = RAGConfig(rerank=True, rerank_top_k=3)
        
        rag = RAG(knowledge=mock_knowledge, config=config, reranker=mock_reranker)
        
        results = [{"text": "test", "score": 0.9}]
        reranked = rag._rerank("query", results)
        
        # Should call reranker
        mock_reranker.rerank.assert_called_once_with(
            query="query",
            results=results,
            top_k=3,
        )
        assert reranked == [{"text": "reranked", "score": 0.95}]
    
    def test_rag_pipeline_rerank_graceful_failure(self):
        """Test that reranking fails gracefully."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = Exception("Rerank failed")
        config = RAGConfig(rerank=True)
        
        rag = RAG(knowledge=mock_knowledge, config=config, reranker=mock_reranker)
        
        results = [{"text": "test", "score": 0.9}]
        reranked = rag._rerank("query", results)
        
        # Should return original results on failure
        assert reranked == results


class TestRerankerProtocol:
    """Tests for RerankerProtocol."""
    
    def test_reranker_protocol_exists(self):
        """Test that RerankerProtocol exists."""
        from praisonaiagents.rag.protocols import RerankerProtocol
        
        assert RerankerProtocol is not None
    
    def test_reranker_protocol_has_rerank_method(self):
        """Test that RerankerProtocol defines rerank method."""
        from praisonaiagents.rag.protocols import RerankerProtocol
        import inspect
        
        # Check that rerank is defined in the protocol
        assert hasattr(RerankerProtocol, "rerank")


class TestCLIRerankFlag:
    """Tests for --rerank CLI flag wiring."""
    
    def test_rag_query_rerank_flag_exists(self):
        """Test that rag query has --rerank flag."""
        from praisonai.cli.commands.rag import rag_query
        import inspect
        
        sig = inspect.signature(rag_query)
        assert "rerank" in sig.parameters
    
    def test_rag_chat_rerank_flag_exists(self):
        """Test that rag chat has --rerank flag."""
        from praisonai.cli.commands.rag import rag_chat
        import inspect
        
        sig = inspect.signature(rag_chat)
        assert "rerank" in sig.parameters
    
    def test_rag_serve_rerank_flag_exists(self):
        """Test that rag serve has --rerank flag."""
        from praisonai.cli.commands.rag import rag_serve
        import inspect
        
        sig = inspect.signature(rag_serve)
        assert "rerank" in sig.parameters
