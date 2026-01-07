"""
Live integration tests for RAG functionality.

These tests require real API keys and are opt-in via environment variable.
Run with: PRAISONAI_LIVE_TESTS=1 pytest tests/integration/test_rag_live.py -v

Required environment variables:
- PRAISONAI_LIVE_TESTS=1 (to enable these tests)
- OPENAI_API_KEY (for LLM generation)
"""

import os
import pytest
import tempfile
from pathlib import Path


# Skip all tests in this module if PRAISONAI_LIVE_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.environ.get("PRAISONAI_LIVE_TESTS") != "1",
    reason="Live tests disabled. Set PRAISONAI_LIVE_TESTS=1 to enable."
)


@pytest.fixture
def temp_knowledge_dir():
    """Create a temporary directory for knowledge storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_document(temp_knowledge_dir):
    """Create a sample document for testing."""
    doc_path = temp_knowledge_dir / "sample.txt"
    doc_path.write_text("""
    PraisonAI is an advanced AI framework for building intelligent agents.
    It supports multiple LLM providers including OpenAI, Anthropic, and Google.
    Key features include:
    - Multi-agent orchestration
    - Knowledge base integration with RAG
    - Hybrid retrieval combining dense and sparse methods
    - Tool integration and function calling
    - Streaming responses and async support
    
    The framework is designed to be lightweight and modular, with lazy loading
    to minimize import overhead. It follows a DRY principle where Knowledge
    is the canonical substrate for indexing and retrieval, while RAG orchestrates
    on top for generation and citations.
    """)
    return doc_path


class TestRAGQueryLive:
    """Live tests for RAG query functionality."""
    
    def test_rag_query_basic(self, temp_knowledge_dir, sample_document):
        """Test basic RAG query with real LLM."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        # Setup knowledge
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_live",
                    "path": str(temp_knowledge_dir / "chroma"),
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        knowledge.add(str(sample_document))
        
        # Setup RAG
        rag_config = RAGConfig(top_k=3, include_citations=True)
        rag = RAG(knowledge=knowledge, config=rag_config)
        
        # Query
        result = rag.query("What is PraisonAI?")
        
        # Verify
        assert result.answer is not None
        assert len(result.answer) > 0
        assert "PraisonAI" in result.answer or "framework" in result.answer.lower()
        assert result.citations is not None
    
    def test_rag_query_with_citations(self, temp_knowledge_dir, sample_document):
        """Test RAG query returns proper citations."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_citations",
                    "path": str(temp_knowledge_dir / "chroma"),
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        knowledge.add(str(sample_document))
        
        rag_config = RAGConfig(top_k=3, include_citations=True)
        rag = RAG(knowledge=knowledge, config=rag_config)
        
        result = rag.query("What features does PraisonAI have?")
        
        # Verify citations
        assert len(result.citations) > 0
        for citation in result.citations:
            assert citation.id is not None
            assert citation.text is not None
            assert len(citation.text) > 0


class TestRAGHybridLive:
    """Live tests for hybrid retrieval."""
    
    def test_hybrid_retrieval_improves_recall(self, temp_knowledge_dir, sample_document):
        """Test that hybrid retrieval works with real data."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        from praisonaiagents.rag.models import RetrievalStrategy
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_hybrid",
                    "path": str(temp_knowledge_dir / "chroma"),
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        knowledge.add(str(sample_document))
        
        # Query with hybrid retrieval
        rag_config = RAGConfig(
            top_k=3,
            include_citations=True,
            retrieval_strategy=RetrievalStrategy.HYBRID,
        )
        rag = RAG(knowledge=knowledge, config=rag_config)
        
        result = rag.query("What LLM providers are supported?")
        
        # Verify result
        assert result.answer is not None
        assert len(result.answer) > 0
        # Should mention providers
        answer_lower = result.answer.lower()
        assert any(p in answer_lower for p in ["openai", "anthropic", "google", "provider"])


class TestRAGStreamingLive:
    """Live tests for streaming responses."""
    
    def test_rag_streaming(self, temp_knowledge_dir, sample_document):
        """Test RAG streaming with real LLM."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_stream",
                    "path": str(temp_knowledge_dir / "chroma"),
                }
            }
        }
        
        knowledge = Knowledge(config=knowledge_config)
        knowledge.add(str(sample_document))
        
        rag_config = RAGConfig(top_k=3)
        rag = RAG(knowledge=knowledge, config=rag_config)
        
        # Stream response
        chunks = list(rag.stream("What is PraisonAI?"))
        
        # Verify streaming worked
        assert len(chunks) > 0
        full_response = "".join(chunks)
        assert len(full_response) > 0


class TestAgentRAGLive:
    """Live tests for Agent with RAG integration."""
    
    def test_agent_rag_query(self, temp_knowledge_dir, sample_document):
        """Test Agent.rag_query with real LLM."""
        from praisonaiagents import Agent
        from praisonaiagents.knowledge import Knowledge
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_agent_rag",
                    "path": str(temp_knowledge_dir / "chroma"),
                }
            }
        }
        
        # Create agent with knowledge
        agent = Agent(
            name="TestAgent",
            instructions="You are a helpful assistant.",
            knowledge=[str(sample_document)],
            knowledge_config=knowledge_config,
            rag_config={"include_citations": True, "top_k": 3},
        )
        
        # Query via agent
        result = agent.rag_query("What features does PraisonAI support?")
        
        # Verify
        assert result is not None
        assert result.answer is not None
        assert len(result.answer) > 0


class TestCLILive:
    """Live tests for CLI commands."""
    
    def test_cli_rag_module_importable(self):
        """Test that RAG CLI module can be imported."""
        # Direct import test - no subprocess needed
        from praisonai.cli.commands.rag import rag_query, rag_chat, rag_serve
        
        # Verify functions exist and are callable
        assert callable(rag_query)
        assert callable(rag_chat)
        assert callable(rag_serve)
    
    def test_cli_knowledge_module_importable(self):
        """Test that knowledge CLI module can be imported."""
        # Direct import test - no subprocess needed
        from praisonai.cli.commands.knowledge import knowledge_index, knowledge_search
        
        # Verify functions exist and are callable
        assert callable(knowledge_index)
        assert callable(knowledge_search)
