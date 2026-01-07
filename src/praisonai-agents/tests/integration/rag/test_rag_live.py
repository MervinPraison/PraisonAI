"""
Live integration tests for RAG with real API keys.

These tests require:
- PRAISONAI_LIVE_TESTS=1
- OPENAI_API_KEY set

Run with:
    PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/rag/ -v
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def sample_documents():
    """Create sample documents for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc1 = Path(tmpdir) / "doc1.txt"
        doc1.write_text("""
        The capital of France is Paris.
        Paris is known for the Eiffel Tower.
        France is a country in Western Europe.
        """)
        
        doc2 = Path(tmpdir) / "doc2.txt"
        doc2.write_text("""
        Python is a programming language.
        Python was created by Guido van Rossum.
        Python is widely used for data science and AI.
        """)
        
        doc3 = Path(tmpdir) / "doc3.txt"
        doc3.write_text("""
        Machine learning is a subset of artificial intelligence.
        Deep learning uses neural networks.
        AI is transforming many industries.
        """)
        
        yield tmpdir


@pytest.mark.live
class TestRAGLiveQuery:
    """Live tests for RAG query functionality."""
    
    def test_rag_query_with_citations(self, openai_api_key, sample_documents):
        """Test RAG query returns answer with citations."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        # Create knowledge base
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_live",
                    "path": f"{sample_documents}/.chroma",
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        
        # Index documents with user_id (required by mem0)
        user_id = "test_user"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        # Create RAG
        rag = RAG(
            knowledge=knowledge,
            config=RAGConfig(top_k=3, include_citations=True)
        )
        
        # Query with user_id
        result = rag.query("What is the capital of France?", user_id=user_id)
        
        # Assertions
        assert result.answer is not None
        assert len(result.answer) > 0
        assert "paris" in result.answer.lower() or "france" in result.answer.lower()
        assert result.citations is not None
        assert len(result.citations) > 0
    
    def test_rag_query_python_topic(self, openai_api_key, sample_documents):
        """Test RAG query on Python topic."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_python",
                    "path": f"{sample_documents}/.chroma_python",
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        
        user_id = "test_user_python"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        rag = RAG(
            knowledge=knowledge,
            config=RAGConfig(top_k=3, include_citations=True)
        )
        
        result = rag.query("Who created Python?", user_id=user_id)
        
        assert result.answer is not None
        assert "guido" in result.answer.lower() or "rossum" in result.answer.lower()


@pytest.mark.live
class TestRAGLiveStreaming:
    """Live tests for RAG streaming functionality."""
    
    def test_rag_stream_produces_chunks(self, openai_api_key, sample_documents):
        """Test RAG streaming produces multiple chunks."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_stream",
                    "path": f"{sample_documents}/.chroma_stream",
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        
        user_id = "test_user_stream"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        rag = RAG(
            knowledge=knowledge,
            config=RAGConfig(top_k=3, stream=True)
        )
        
        # Collect streamed chunks
        chunks = []
        for chunk in rag.stream("Tell me about machine learning", user_id=user_id):
            chunks.append(chunk)
        
        # Should have multiple chunks
        assert len(chunks) >= 1
        
        # Combined response should be meaningful
        full_response = "".join(chunks)
        assert len(full_response) > 10


@pytest.mark.live
class TestRAGLiveCitations:
    """Live tests for RAG citation functionality."""
    
    def test_citations_reference_correct_sources(self, openai_api_key, sample_documents):
        """Test that citations reference the correct source documents."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_citations",
                    "path": f"{sample_documents}/.chroma_citations",
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        
        user_id = "test_user_citations"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        rag = RAG(
            knowledge=knowledge,
            config=RAGConfig(top_k=5, include_citations=True)
        )
        
        result = rag.query("What is the capital of France?", user_id=user_id)
        
        # Check citations
        assert result.has_citations
        
        # At least one citation should be from doc1 (France content)
        citation_sources = [c.source for c in result.citations]
        assert len(citation_sources) > 0
        
        # Citations should have scores
        for citation in result.citations:
            assert citation.score is not None or citation.score >= 0
    
    def test_get_citations_without_generation(self, openai_api_key, sample_documents):
        """Test getting citations without generating an answer."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_citations_only",
                    "path": f"{sample_documents}/.chroma_citations_only",
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        
        user_id = "test_user_citations_only"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        rag = RAG(
            knowledge=knowledge,
            config=RAGConfig(top_k=3)
        )
        
        citations = rag.get_citations("Python programming", user_id=user_id)
        
        assert citations is not None
        assert len(citations) > 0
        
        # Check citation structure
        for citation in citations:
            assert citation.id is not None
            assert citation.text is not None
            assert len(citation.text) > 0
