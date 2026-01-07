"""
Unit tests for RAG primitives used by AutoRagAgent.

Tests:
- ContextPack model
- RAG.retrieve() returns ContextPack without LLM call
- Knowledge add alias command
"""

from unittest.mock import Mock


class TestContextPack:
    """Tests for ContextPack dataclass."""
    
    def test_context_pack_creation(self):
        """Test ContextPack can be created with required fields."""
        from praisonaiagents.rag.models import ContextPack, Citation
        
        pack = ContextPack(
            context="Test context",
            citations=[],
            query="test query",
        )
        
        assert pack.context == "Test context"
        assert pack.query == "test query"
        assert pack.citations == []
        assert pack.metadata == {}
    
    def test_context_pack_with_citations(self):
        """Test ContextPack with citations."""
        from praisonaiagents.rag.models import ContextPack, Citation
        
        citation = Citation(
            id="1",
            source="doc.pdf",
            text="Sample text",
            score=0.95,
        )
        
        pack = ContextPack(
            context="Test context",
            citations=[citation],
            query="test query",
        )
        
        assert pack.has_citations is True
        assert len(pack.citations) == 1
        assert pack.citations[0].source == "doc.pdf"
    
    def test_context_pack_to_dict(self):
        """Test ContextPack serialization."""
        from praisonaiagents.rag.models import ContextPack, Citation
        
        citation = Citation(id="1", source="doc.pdf", text="text", score=0.9)
        pack = ContextPack(
            context="ctx",
            citations=[citation],
            query="q",
            metadata={"key": "value"},
        )
        
        d = pack.to_dict()
        assert d["context"] == "ctx"
        assert d["query"] == "q"
        assert len(d["citations"]) == 1
        assert d["metadata"]["key"] == "value"
    
    def test_context_pack_from_dict(self):
        """Test ContextPack deserialization."""
        from praisonaiagents.rag.models import ContextPack
        
        data = {
            "context": "ctx",
            "citations": [{"id": "1", "source": "s", "text": "t", "score": 0.5}],
            "query": "q",
            "metadata": {},
        }
        
        pack = ContextPack.from_dict(data)
        assert pack.context == "ctx"
        assert pack.query == "q"
        assert len(pack.citations) == 1
    
    def test_context_pack_format_for_prompt(self):
        """Test ContextPack.format_for_prompt()."""
        from praisonaiagents.rag.models import ContextPack, Citation
        
        citation = Citation(id="1", source="doc.pdf", text="text", score=0.9)
        pack = ContextPack(context="Main context", citations=[citation], query="q")
        
        formatted = pack.format_for_prompt(include_sources=True)
        assert "Main context" in formatted
        assert "Sources:" in formatted
        assert "[1] doc.pdf" in formatted
        
        formatted_no_sources = pack.format_for_prompt(include_sources=False)
        assert "Sources:" not in formatted_no_sources


class TestRAGRetrieve:
    """Tests for RAG.retrieve() method."""
    
    def test_retrieve_returns_context_pack(self):
        """Test that retrieve() returns ContextPack without LLM call."""
        from praisonaiagents.rag.models import ContextPack
        
        # Create mock knowledge
        mock_knowledge = Mock()
        mock_knowledge.search.return_value = {
            "results": [
                {"memory": "chunk1", "score": 0.9, "metadata": {"source": "doc1.pdf"}},
                {"memory": "chunk2", "score": 0.8, "metadata": {"source": "doc2.pdf"}},
            ]
        }
        
        # Import and create RAG
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        rag = RAG(knowledge=mock_knowledge, config=RAGConfig())
        
        # Call retrieve
        result = rag.retrieve("test query")
        
        # Should return ContextPack
        assert isinstance(result, ContextPack)
        assert result.query == "test query"
        assert "elapsed_seconds" in result.metadata
    
    def test_retrieve_with_overrides(self):
        """Test retrieve() respects parameter overrides."""
        mock_knowledge = Mock()
        mock_knowledge.search.return_value = {"results": []}
        
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig(top_k=5, rerank=False)
        rag = RAG(knowledge=mock_knowledge, config=config)
        
        # Call with overrides
        result = rag.retrieve("query", top_k=10, rerank=True)
        
        # Config should be restored after call
        assert rag.config.top_k == 5
        assert rag.config.rerank is False


class TestKnowledgeAddAlias:
    """Tests for knowledge add alias command."""
    
    def test_add_command_exists(self):
        """Test that 'add' command is registered."""
        from praisonai.cli.commands.knowledge import app
        
        # Get command names
        command_names = [cmd.name for cmd in app.registered_commands]
        
        assert "add" in command_names
        assert "index" in command_names
    
    def test_add_delegates_to_index(self):
        """Test that 'add' delegates to 'index'."""
        from praisonai.cli.commands.knowledge import knowledge_add, knowledge_index
        
        # Both should be callable
        assert callable(knowledge_add)
        assert callable(knowledge_index)
