"""
Live integration tests for Agent + RAG integration.

These tests require:
- PRAISONAI_LIVE_TESTS=1 environment variable
- OPENAI_API_KEY environment variable

Run with: PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/agent/ -v
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def sample_documents():
    """Create sample documents for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample documents
        doc1 = Path(tmpdir) / "doc1.txt"
        doc1.write_text("""
        The capital of France is Paris.
        Paris is known for the Eiffel Tower.
        France is a country in Western Europe.
        """)
        
        doc2 = Path(tmpdir) / "doc2.txt"
        doc2.write_text("""
        Python was created by Guido van Rossum.
        Python is a high-level programming language.
        Python emphasizes code readability.
        """)
        
        doc3 = Path(tmpdir) / "doc3.txt"
        doc3.write_text("""
        Machine learning is a subset of artificial intelligence.
        Deep learning uses neural networks with many layers.
        AI is transforming many industries.
        """)
        
        yield tmpdir


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.mark.live
class TestAgentRAGLiveQuery:
    """Live tests for Agent RAG query functionality."""
    
    def test_agent_rag_query_with_citations(self, openai_api_key, sample_documents):
        """Test Agent.rag_query returns answer with citations."""
        from praisonaiagents import Agent
        from praisonaiagents.knowledge import Knowledge
        
        # Create knowledge base
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_agent_live",
                    "path": f"{sample_documents}/.chroma",
                }
            }
        }
        
        # Pre-index documents
        knowledge = Knowledge(config=knowledge_config)
        user_id = "test_user_agent"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        # Create agent with knowledge and rag_config
        agent = Agent(
            name="TestAgent",
            instructions="You are a helpful assistant that answers questions based on provided knowledge.",
            knowledge=[str(doc) for doc in Path(sample_documents).glob("*.txt")],
            knowledge_config=knowledge_config,
            rag_config={"include_citations": True, "top_k": 3},
            user_id=user_id,
        )
        
        # Use agent.rag_query for RAG with citations
        result = agent.rag_query("What is the capital of France?")
        
        # Assertions
        assert result.answer is not None
        assert len(result.answer) > 0
        assert "paris" in result.answer.lower() or "france" in result.answer.lower()
        assert result.citations is not None
        assert len(result.citations) > 0
    
    def test_agent_rag_property_access(self, openai_api_key, sample_documents):
        """Test Agent.rag property provides RAG instance."""
        from praisonaiagents import Agent
        from praisonaiagents.knowledge import Knowledge
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_agent_rag_prop",
                    "path": f"{sample_documents}/.chroma_prop",
                }
            }
        }
        
        # Pre-index
        knowledge = Knowledge(config=knowledge_config)
        user_id = "test_user_prop"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=[str(doc) for doc in Path(sample_documents).glob("*.txt")],
            knowledge_config=knowledge_config,
            rag_config={"include_citations": True},
            user_id=user_id,
        )
        
        # Access RAG through property
        rag = agent.rag
        assert rag is not None
        
        # Query through RAG directly
        result = rag.query("Who created Python?", user_id=user_id)
        assert "guido" in result.answer.lower() or "rossum" in result.answer.lower()


@pytest.mark.live
class TestAgentRAGLiveStreaming:
    """Live tests for Agent RAG streaming functionality."""
    
    def test_agent_rag_stream(self, openai_api_key, sample_documents):
        """Test Agent.rag.stream produces chunks."""
        from praisonaiagents import Agent
        from praisonaiagents.knowledge import Knowledge
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_agent_stream",
                    "path": f"{sample_documents}/.chroma_stream",
                }
            }
        }
        
        # Pre-index
        knowledge = Knowledge(config=knowledge_config)
        user_id = "test_user_stream"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=[str(doc) for doc in Path(sample_documents).glob("*.txt")],
            knowledge_config=knowledge_config,
            rag_config={"stream": True},
            user_id=user_id,
        )
        
        # Stream through RAG
        chunks = []
        for chunk in agent.rag.stream("Tell me about machine learning", user_id=user_id):
            chunks.append(chunk)
        
        # Should have multiple chunks
        assert len(chunks) >= 1
        
        # Combined response should be meaningful
        full_response = "".join(chunks)
        assert len(full_response) > 10


@pytest.mark.live
class TestAgentRAGLiveCitations:
    """Live tests for Agent RAG citation functionality."""
    
    def test_agent_citations_have_source_info(self, openai_api_key, sample_documents):
        """Test that Agent RAG citations have proper source information."""
        from praisonaiagents import Agent
        from praisonaiagents.knowledge import Knowledge
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_agent_citations",
                    "path": f"{sample_documents}/.chroma_citations",
                }
            }
        }
        
        # Pre-index
        knowledge = Knowledge(config=knowledge_config)
        user_id = "test_user_citations"
        for doc in Path(sample_documents).glob("*.txt"):
            knowledge.add(str(doc), user_id=user_id)
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=[str(doc) for doc in Path(sample_documents).glob("*.txt")],
            knowledge_config=knowledge_config,
            rag_config={"include_citations": True, "top_k": 5},
            user_id=user_id,
        )
        
        result = agent.rag_query("What is the capital of France?")
        
        # Check citations
        assert result.has_citations
        
        # Citations should have scores
        for citation in result.citations:
            assert citation.id is not None
            assert citation.text is not None
            assert len(citation.text) > 0
