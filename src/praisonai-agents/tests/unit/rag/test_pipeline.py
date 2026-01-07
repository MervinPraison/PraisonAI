"""Tests for RAG pipeline."""

from unittest.mock import MagicMock, patch


class TestDefaultCitationFormatter:
    """Tests for DefaultCitationFormatter."""
    
    def test_format_empty(self):
        """Test formatting empty results."""
        from praisonaiagents.rag.pipeline import DefaultCitationFormatter
        
        formatter = DefaultCitationFormatter()
        citations = formatter.format([])
        assert citations == []
    
    def test_format_single_result(self):
        """Test formatting single result."""
        from praisonaiagents.rag.pipeline import DefaultCitationFormatter
        
        formatter = DefaultCitationFormatter()
        results = [
            {
                "text": "Important finding",
                "score": 0.95,
                "metadata": {"filename": "paper.pdf", "source": "/docs/paper.pdf"}
            }
        ]
        citations = formatter.format(results)
        
        assert len(citations) == 1
        assert citations[0].id == "1"
        assert citations[0].source == "paper.pdf"
        assert citations[0].score == 0.95
    
    def test_format_multiple_results(self):
        """Test formatting multiple results."""
        from praisonaiagents.rag.pipeline import DefaultCitationFormatter
        
        formatter = DefaultCitationFormatter()
        results = [
            {"text": "A", "metadata": {"filename": "a.pdf"}},
            {"text": "B", "metadata": {"filename": "b.pdf"}},
            {"text": "C", "metadata": {"filename": "c.pdf"}},
        ]
        citations = formatter.format(results)
        
        assert len(citations) == 3
        assert citations[0].id == "1"
        assert citations[1].id == "2"
        assert citations[2].id == "3"
    
    def test_format_with_start_id(self):
        """Test formatting with custom start ID."""
        from praisonaiagents.rag.pipeline import DefaultCitationFormatter
        
        formatter = DefaultCitationFormatter()
        results = [{"text": "Content", "metadata": {}}]
        citations = formatter.format(results, start_id=5)
        
        assert citations[0].id == "5"
    
    def test_format_memory_key(self):
        """Test formatting with 'memory' key instead of 'text'."""
        from praisonaiagents.rag.pipeline import DefaultCitationFormatter
        
        formatter = DefaultCitationFormatter()
        results = [{"memory": "Memory content", "metadata": {}}]
        citations = formatter.format(results)
        
        assert citations[0].text == "Memory content"


class TestRAGPipeline:
    """Tests for RAG pipeline class."""
    
    def test_rag_init_defaults(self):
        """Test RAG initialization with defaults."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        rag = RAG(knowledge=mock_knowledge)
        
        assert rag.knowledge == mock_knowledge
        assert isinstance(rag.config, RAGConfig)
        assert rag.reranker is None
    
    def test_rag_init_custom_config(self):
        """Test RAG initialization with custom config."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        config = RAGConfig(top_k=10, rerank=True)
        rag = RAG(knowledge=mock_knowledge, config=config)
        
        assert rag.config.top_k == 10
        assert rag.config.rerank is True
    
    def test_rag_retrieve(self):
        """Test RAG retrieval."""
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": "Result 1", "score": 0.9, "metadata": {}},
            {"text": "Result 2", "score": 0.8, "metadata": {}},
        ]
        
        rag = RAG(knowledge=mock_knowledge)
        results = rag._retrieve("test query")
        
        mock_knowledge.search.assert_called_once()
        assert len(results) == 2
    
    def test_rag_retrieve_with_min_score(self):
        """Test RAG retrieval filters by min_score."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": "High", "score": 0.9, "metadata": {}},
            {"text": "Low", "score": 0.3, "metadata": {}},
        ]
        
        config = RAGConfig(min_score=0.5)
        rag = RAG(knowledge=mock_knowledge, config=config)
        results = rag._retrieve("test")
        
        assert len(results) == 1
        assert results[0]["text"] == "High"
    
    def test_rag_retrieve_respects_top_k(self):
        """Test RAG retrieval respects top_k limit."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": f"Result {i}", "score": 0.9, "metadata": {}}
            for i in range(10)
        ]
        
        config = RAGConfig(top_k=3)
        rag = RAG(knowledge=mock_knowledge, config=config)
        results = rag._retrieve("test")
        
        assert len(results) == 3
    
    def test_rag_build_prompt(self):
        """Test RAG prompt building."""
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        rag = RAG(knowledge=mock_knowledge)
        
        prompt = rag._build_prompt("What is X?", "Context about X")
        
        assert "What is X?" in prompt
        assert "Context about X" in prompt
    
    def test_rag_query_full_pipeline(self):
        """Test full RAG query pipeline."""
        from praisonaiagents.rag.pipeline import RAG
        
        # Mock knowledge
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": "The answer is 42", "score": 0.95, "metadata": {"filename": "guide.pdf"}}
        ]
        
        # Mock LLM
        mock_llm = MagicMock()
        mock_llm.get_response.return_value = "Based on the context, the answer is 42."
        
        rag = RAG(knowledge=mock_knowledge, llm=mock_llm)
        result = rag.query("What is the answer?")
        
        assert "42" in result.answer
        assert len(result.citations) == 1
        assert result.citations[0].source == "guide.pdf"
        assert result.query == "What is the answer?"
        assert "elapsed_seconds" in result.metadata
    
    def test_rag_query_no_results(self):
        """Test RAG query with no results."""
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = []
        
        mock_llm = MagicMock()
        mock_llm.get_response.return_value = "I don't have information about that."
        
        rag = RAG(knowledge=mock_knowledge, llm=mock_llm)
        result = rag.query("Unknown topic")
        
        assert result.citations == []
        assert result.context_used == ""
    
    def test_rag_query_with_reranker(self):
        """Test RAG query with reranker."""
        from praisonaiagents.rag.pipeline import RAG
        from praisonaiagents.rag.models import RAGConfig
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": "A", "score": 0.7, "metadata": {}},
            {"text": "B", "score": 0.8, "metadata": {}},
        ]
        
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [
            {"text": "B", "score": 0.95, "metadata": {}},
            {"text": "A", "score": 0.6, "metadata": {}},
        ]
        
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "Answer"
        
        config = RAGConfig(rerank=True)
        rag = RAG(knowledge=mock_knowledge, llm=mock_llm, config=config, reranker=mock_reranker)
        result = rag.query("Test")
        
        mock_reranker.rerank.assert_called_once()
        assert result.metadata["reranked"] is True
    
    def test_rag_get_citations(self):
        """Test getting citations without generating answer."""
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": "Content", "score": 0.9, "metadata": {"filename": "doc.pdf"}}
        ]
        
        rag = RAG(knowledge=mock_knowledge)
        citations = rag.get_citations("Query")
        
        assert len(citations) == 1
        assert citations[0].source == "doc.pdf"
    
    def test_rag_stream_fallback(self):
        """Test RAG streaming with fallback to non-streaming."""
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": "Context", "metadata": {}}
        ]
        
        mock_llm = MagicMock()
        mock_llm.get_response.return_value = "Word1 Word2 Word3"
        # No stream method, should fallback
        del mock_llm.stream
        
        rag = RAG(knowledge=mock_knowledge, llm=mock_llm)
        chunks = list(rag.stream("Question"))
        
        assert len(chunks) > 0
        assert "Word1" in "".join(chunks)


class TestRAGAsync:
    """Tests for RAG async methods."""
    
    def test_aquery(self):
        """Test async query."""
        import asyncio
        from praisonaiagents.rag.pipeline import RAG
        
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"text": "Async content", "metadata": {}}
        ]
        
        mock_llm = MagicMock()
        mock_llm.get_response.return_value = "Async answer"
        
        rag = RAG(knowledge=mock_knowledge, llm=mock_llm)
        
        async def run_test():
            result = await rag.aquery("Async question")
            return result
        
        result = asyncio.run(run_test())
        assert "Async answer" in result.answer


class TestRAGImports:
    """Tests for RAG module imports."""
    
    def test_lazy_import_rag(self):
        """Test that RAG can be imported from main package."""
        from praisonaiagents import RAG
        assert RAG is not None
    
    def test_lazy_import_rag_config(self):
        """Test that RAGConfig can be imported from main package."""
        from praisonaiagents import RAGConfig
        assert RAGConfig is not None
    
    def test_lazy_import_rag_result(self):
        """Test that RAGResult can be imported from main package."""
        from praisonaiagents import RAGResult
        assert RAGResult is not None
    
    def test_import_from_rag_module(self):
        """Test direct import from rag module."""
        from praisonaiagents.rag import RAG, RAGConfig, RAGResult, Citation
        
        assert RAG is not None
        assert RAGConfig is not None
        assert RAGResult is not None
        assert Citation is not None
