"""
Tests for HybridRetriever - combines dense vector retrieval with BM25 keyword retrieval.

TDD: Write tests first, then implement.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any


class TestHybridRetrieverBasic:
    """Basic tests for HybridRetriever initialization and structure."""
    
    def test_hybrid_retriever_exists(self):
        """Test that HybridRetriever class exists."""
        from praisonai.adapters.retrievers import HybridRetriever
        assert HybridRetriever is not None
    
    def test_hybrid_retriever_has_name(self):
        """Test that HybridRetriever has correct name."""
        from praisonai.adapters.retrievers import HybridRetriever
        
        mock_vector_store = MagicMock()
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
        )
        
        assert retriever.name == "hybrid"
    
    def test_hybrid_retriever_accepts_keyword_index(self):
        """Test that HybridRetriever accepts a keyword index."""
        from praisonai.adapters.retrievers import HybridRetriever
        from praisonaiagents.knowledge.index import KeywordIndex
        
        mock_vector_store = MagicMock()
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        keyword_index = KeywordIndex()
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
            keyword_index=keyword_index,
        )
        
        assert retriever.keyword_index is keyword_index
    
    def test_hybrid_retriever_creates_keyword_index_if_not_provided(self):
        """Test that HybridRetriever creates KeywordIndex if not provided."""
        from praisonai.adapters.retrievers import HybridRetriever
        from praisonaiagents.knowledge.index import KeywordIndex
        
        mock_vector_store = MagicMock()
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
        )
        
        assert retriever.keyword_index is not None
        assert isinstance(retriever.keyword_index, KeywordIndex)


class TestHybridRetrieverRetrieval:
    """Tests for HybridRetriever.retrieve() method."""
    
    def test_retrieve_combines_dense_and_sparse_results(self):
        """Test that retrieve combines dense and sparse results."""
        from praisonai.adapters.retrievers import HybridRetriever
        from praisonaiagents.knowledge.index import KeywordIndex
        from praisonaiagents.knowledge.retrieval import RetrievalResult
        
        # Setup mock vector store
        mock_vector_store = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.text = "Dense result 1"
        mock_result1.score = 0.9
        mock_result1.metadata = {"source": "doc1.pdf"}
        mock_result1.id = "dense_1"
        
        mock_result2 = MagicMock()
        mock_result2.text = "Dense result 2"
        mock_result2.score = 0.8
        mock_result2.metadata = {"source": "doc2.pdf"}
        mock_result2.id = "dense_2"
        
        mock_vector_store.query.return_value = [mock_result1, mock_result2]
        
        # Setup keyword index with documents
        keyword_index = KeywordIndex()
        keyword_index.add_documents(
            texts=["Sparse result about Python programming", "Another sparse result about machine learning"],
            ids=["sparse_1", "sparse_2"],
            metadatas=[{"source": "doc3.pdf"}, {"source": "doc4.pdf"}]
        )
        
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
            keyword_index=keyword_index,
        )
        
        results = retriever.retrieve("Python programming", top_k=5)
        
        # Should have results from both dense and sparse
        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)
    
    def test_retrieve_uses_rrf_for_fusion(self):
        """Test that retrieve uses RRF for result fusion."""
        from praisonai.adapters.retrievers import HybridRetriever
        from praisonaiagents.knowledge.index import KeywordIndex
        
        # Setup mock vector store with overlapping result
        mock_vector_store = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.text = "Shared result about Python"
        mock_result1.score = 0.9
        mock_result1.metadata = {"source": "shared.pdf"}
        mock_result1.id = "shared_1"
        
        mock_vector_store.query.return_value = [mock_result1]
        
        # Setup keyword index with same document
        keyword_index = KeywordIndex()
        keyword_index.add_documents(
            texts=["Shared result about Python"],
            ids=["shared_1"],
            metadatas=[{"source": "shared.pdf"}]
        )
        
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
            keyword_index=keyword_index,
            rrf_k=60,
        )
        
        results = retriever.retrieve("Python", top_k=5)
        
        # Shared result should have boosted score from RRF
        assert len(results) >= 1
        # The shared result should appear (deduped)
        texts = [r.text for r in results]
        assert "Shared result about Python" in texts
    
    def test_retrieve_respects_top_k(self):
        """Test that retrieve respects top_k parameter."""
        from praisonai.adapters.retrievers import HybridRetriever
        from praisonaiagents.knowledge.index import KeywordIndex
        
        mock_vector_store = MagicMock()
        mock_results = []
        for i in range(10):
            mock_result = MagicMock()
            mock_result.text = f"Dense result {i}"
            mock_result.score = 0.9 - i * 0.05
            mock_result.metadata = {"source": f"doc{i}.pdf"}
            mock_result.id = f"dense_{i}"
            mock_results.append(mock_result)
        
        mock_vector_store.query.return_value = mock_results
        
        keyword_index = KeywordIndex()
        for i in range(10):
            keyword_index.add_documents(
                texts=[f"Sparse result {i}"],
                ids=[f"sparse_{i}"],
                metadatas=[{"source": f"sparse{i}.pdf"}]
            )
        
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
            keyword_index=keyword_index,
        )
        
        results = retriever.retrieve("test query", top_k=3)
        
        assert len(results) <= 3
    
    def test_retrieve_with_filter(self):
        """Test that retrieve passes filter to both retrievers."""
        from praisonai.adapters.retrievers import HybridRetriever
        from praisonaiagents.knowledge.index import KeywordIndex
        
        mock_vector_store = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Filtered result"
        mock_result.score = 0.9
        mock_result.metadata = {"source": "filtered.pdf", "category": "tech"}
        mock_result.id = "filtered_1"
        mock_vector_store.query.return_value = [mock_result]
        
        keyword_index = KeywordIndex()
        keyword_index.add_documents(
            texts=["Tech document", "Non-tech document"],
            ids=["tech_1", "nontech_1"],
            metadatas=[{"category": "tech"}, {"category": "other"}]
        )
        
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
            keyword_index=keyword_index,
        )
        
        results = retriever.retrieve(
            "document",
            top_k=5,
            filter={"category": "tech"}
        )
        
        # Vector store should be called with filter
        mock_vector_store.query.assert_called_once()
        call_kwargs = mock_vector_store.query.call_args
        assert call_kwargs[1].get("filter") == {"category": "tech"}


class TestHybridRetrieverWeights:
    """Tests for HybridRetriever weight configuration."""
    
    def test_default_weights(self):
        """Test default weights are 0.5/0.5."""
        from praisonai.adapters.retrievers import HybridRetriever
        
        mock_vector_store = MagicMock()
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
        )
        
        assert retriever.dense_weight == 0.5
        assert retriever.sparse_weight == 0.5
    
    def test_custom_weights(self):
        """Test custom weight configuration."""
        from praisonai.adapters.retrievers import HybridRetriever
        
        mock_vector_store = MagicMock()
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
            dense_weight=0.7,
            sparse_weight=0.3,
        )
        
        assert retriever.dense_weight == 0.7
        assert retriever.sparse_weight == 0.3


class TestHybridRetrieverIndexSync:
    """Tests for keeping keyword index in sync with vector store."""
    
    def test_add_to_keyword_index(self):
        """Test adding documents to keyword index."""
        from praisonai.adapters.retrievers import HybridRetriever
        
        mock_vector_store = MagicMock()
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
        )
        
        # Add documents to keyword index
        retriever.add_to_keyword_index(
            texts=["Document about Python", "Document about Java"],
            ids=["doc1", "doc2"],
            metadatas=[{"source": "python.pdf"}, {"source": "java.pdf"}]
        )
        
        # Verify documents are in keyword index
        results = retriever.keyword_index.query("Python", top_k=5)
        assert len(results) > 0
        assert any("Python" in r["text"] for r in results)


class TestHybridRetrieverAsync:
    """Tests for async retrieval."""
    
    @pytest.mark.asyncio
    async def test_aretrieve_exists(self):
        """Test that aretrieve method exists."""
        from praisonai.adapters.retrievers import HybridRetriever
        
        mock_vector_store = MagicMock()
        mock_embedding_fn = MagicMock(return_value=[0.1] * 384)
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            embedding_fn=mock_embedding_fn,
        )
        
        assert hasattr(retriever, 'aretrieve')
        assert callable(retriever.aretrieve)


class TestHybridRetrieverRegistration:
    """Tests for retriever registration."""
    
    def test_hybrid_retriever_registered(self):
        """Test that HybridRetriever is registered in the registry."""
        from praisonaiagents.knowledge.retrieval import get_retriever_registry
        
        # Import to trigger registration
        from praisonai.adapters.retrievers import register_default_retrievers
        register_default_retrievers()
        
        registry = get_retriever_registry()
        assert "hybrid" in registry.list_retrievers()
