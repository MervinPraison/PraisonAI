"""
Tests for RAG CLI command flags.

Tests that --hybrid, --rerank, and other flags are properly parsed and wired.
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock


runner = CliRunner()


class TestRagQueryFlags:
    """Tests for rag query command flags."""
    
    def test_rag_query_has_hybrid_flag(self):
        """Test that rag query command has --hybrid flag."""
        from praisonai.cli.commands.rag import rag_query
        import inspect
        
        sig = inspect.signature(rag_query)
        params = list(sig.parameters.keys())
        
        assert "hybrid" in params
    
    def test_rag_query_has_rerank_flag(self):
        """Test that rag query command has --rerank flag."""
        from praisonai.cli.commands.rag import rag_query
        import inspect
        
        sig = inspect.signature(rag_query)
        params = list(sig.parameters.keys())
        
        assert "rerank" in params
    
    def test_rag_query_has_profile_flags(self):
        """Test that rag query command has profile flags."""
        from praisonai.cli.commands.rag import rag_query
        import inspect
        
        sig = inspect.signature(rag_query)
        params = list(sig.parameters.keys())
        
        assert "profile" in params
        assert "profile_out" in params
        assert "profile_top" in params


class TestRagChatFlags:
    """Tests for rag chat command flags."""
    
    def test_rag_chat_has_hybrid_flag(self):
        """Test that rag chat command has --hybrid flag."""
        from praisonai.cli.commands.rag import rag_chat
        import inspect
        
        sig = inspect.signature(rag_chat)
        params = list(sig.parameters.keys())
        
        assert "hybrid" in params
    
    def test_rag_chat_has_rerank_flag(self):
        """Test that rag chat command has --rerank flag."""
        from praisonai.cli.commands.rag import rag_chat
        import inspect
        
        sig = inspect.signature(rag_chat)
        params = list(sig.parameters.keys())
        
        assert "rerank" in params


class TestRagServeFlags:
    """Tests for rag serve command flags."""
    
    def test_rag_serve_has_hybrid_flag(self):
        """Test that rag serve command has --hybrid flag."""
        from praisonai.cli.commands.rag import rag_serve
        import inspect
        
        sig = inspect.signature(rag_serve)
        params = list(sig.parameters.keys())
        
        assert "hybrid" in params
    
    def test_rag_serve_has_rerank_flag(self):
        """Test that rag serve command has --rerank flag."""
        from praisonai.cli.commands.rag import rag_serve
        import inspect
        
        sig = inspect.signature(rag_serve)
        params = list(sig.parameters.keys())
        
        assert "rerank" in params
    
    def test_rag_serve_has_openai_compat_flag(self):
        """Test that rag serve command has --openai-compat flag."""
        from praisonai.cli.commands.rag import rag_serve
        import inspect
        
        sig = inspect.signature(rag_serve)
        params = list(sig.parameters.keys())
        
        assert "openai_compat" in params
    
    def test_rag_serve_has_profile_flags(self):
        """Test that rag serve command has profile flags."""
        from praisonai.cli.commands.rag import rag_serve
        import inspect
        
        sig = inspect.signature(rag_serve)
        params = list(sig.parameters.keys())
        
        assert "profile" in params
        assert "profile_out" in params
        assert "profile_top" in params


class TestKnowledgeSearchFlags:
    """Tests for knowledge search command flags."""
    
    def test_knowledge_search_has_hybrid_flag(self):
        """Test that knowledge search command has --hybrid flag."""
        from praisonai.cli.commands.knowledge import knowledge_search
        import inspect
        
        sig = inspect.signature(knowledge_search)
        params = list(sig.parameters.keys())
        
        assert "hybrid" in params
    
    def test_knowledge_search_has_profile_flags(self):
        """Test that knowledge search command has profile flags."""
        from praisonai.cli.commands.knowledge import knowledge_search
        import inspect
        
        sig = inspect.signature(knowledge_search)
        params = list(sig.parameters.keys())
        
        assert "profile" in params
        assert "profile_out" in params
        assert "profile_top" in params


class TestRetrievalStrategyWiring:
    """Tests for retrieval strategy wiring in CLI commands."""
    
    def test_retrieval_strategy_enum_has_hybrid(self):
        """Test that RetrievalStrategy enum has HYBRID value."""
        from praisonaiagents.rag.models import RetrievalStrategy
        
        assert hasattr(RetrievalStrategy, "HYBRID")
        assert RetrievalStrategy.HYBRID.value == "hybrid"
    
    def test_rag_config_accepts_retrieval_strategy(self):
        """Test that RAGConfig accepts retrieval_strategy parameter."""
        from praisonaiagents.rag.models import RAGConfig, RetrievalStrategy
        
        config = RAGConfig(retrieval_strategy=RetrievalStrategy.HYBRID)
        
        assert config.retrieval_strategy == RetrievalStrategy.HYBRID
    
    def test_rag_config_accepts_rerank(self):
        """Test that RAGConfig accepts rerank parameter."""
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig(rerank=True)
        
        assert config.rerank is True
