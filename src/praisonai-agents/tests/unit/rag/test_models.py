"""Tests for RAG data models."""

import pytest


class TestCitation:
    """Tests for Citation dataclass."""
    
    def test_citation_defaults(self):
        """Test Citation with default values."""
        from praisonaiagents.rag.models import Citation
        
        citation = Citation(id="1", source="test.pdf", text="Sample text")
        
        assert citation.id == "1"
        assert citation.source == "test.pdf"
        assert citation.text == "Sample text"
        assert citation.score == 0.0
        assert citation.doc_id is None
        assert citation.chunk_id is None
        assert citation.offset is None
        assert citation.metadata == {}
    
    def test_citation_full(self):
        """Test Citation with all values."""
        from praisonaiagents.rag.models import Citation
        
        citation = Citation(
            id="1",
            source="doc.pdf",
            text="Important finding",
            score=0.95,
            doc_id="doc123",
            chunk_id="chunk456",
            offset=100,
            metadata={"page": 5}
        )
        
        assert citation.score == 0.95
        assert citation.doc_id == "doc123"
        assert citation.metadata["page"] == 5
    
    def test_citation_to_dict(self):
        """Test Citation serialization."""
        from praisonaiagents.rag.models import Citation
        
        citation = Citation(id="1", source="test.pdf", text="Sample")
        data = citation.to_dict()
        
        assert data["id"] == "1"
        assert data["source"] == "test.pdf"
        assert "metadata" in data
    
    def test_citation_from_dict(self):
        """Test Citation deserialization."""
        from praisonaiagents.rag.models import Citation
        
        data = {
            "id": "2",
            "source": "doc.pdf",
            "text": "Content",
            "score": 0.8,
            "metadata": {"key": "value"}
        }
        citation = Citation.from_dict(data)
        
        assert citation.id == "2"
        assert citation.score == 0.8
        assert citation.metadata["key"] == "value"
    
    def test_citation_str(self):
        """Test Citation string representation."""
        from praisonaiagents.rag.models import Citation
        
        citation = Citation(id="1", source="test.pdf", text="Short text")
        s = str(citation)
        
        assert "[1]" in s
        assert "test.pdf" in s


class TestRAGResult:
    """Tests for RAGResult dataclass."""
    
    def test_rag_result_defaults(self):
        """Test RAGResult with default values."""
        from praisonaiagents.rag.models import RAGResult
        
        result = RAGResult(answer="The answer is 42.")
        
        assert result.answer == "The answer is 42."
        assert result.citations == []
        assert result.context_used == ""
        assert result.query == ""
        assert result.metadata == {}
    
    def test_rag_result_with_citations(self):
        """Test RAGResult with citations."""
        from praisonaiagents.rag.models import RAGResult, Citation
        
        citations = [
            Citation(id="1", source="doc1.pdf", text="Evidence 1"),
            Citation(id="2", source="doc2.pdf", text="Evidence 2"),
        ]
        result = RAGResult(
            answer="Based on the evidence...",
            citations=citations,
            query="What is the answer?"
        )
        
        assert len(result.citations) == 2
        assert result.has_citations is True
    
    def test_rag_result_no_citations(self):
        """Test has_citations property."""
        from praisonaiagents.rag.models import RAGResult
        
        result = RAGResult(answer="No sources")
        assert result.has_citations is False
    
    def test_rag_result_to_dict(self):
        """Test RAGResult serialization."""
        from praisonaiagents.rag.models import RAGResult, Citation
        
        result = RAGResult(
            answer="Answer",
            citations=[Citation(id="1", source="s", text="t")],
            metadata={"elapsed": 0.5}
        )
        data = result.to_dict()
        
        assert data["answer"] == "Answer"
        assert len(data["citations"]) == 1
        assert data["metadata"]["elapsed"] == 0.5
    
    def test_rag_result_format_with_citations(self):
        """Test formatting answer with citations."""
        from praisonaiagents.rag.models import RAGResult, Citation
        
        result = RAGResult(
            answer="The main finding is X.",
            citations=[Citation(id="1", source="paper.pdf", text="X is important")]
        )
        formatted = result.format_answer_with_citations()
        
        assert "The main finding is X." in formatted
        assert "Sources:" in formatted
        assert "paper.pdf" in formatted


class TestRAGConfig:
    """Tests for RAGConfig dataclass."""
    
    def test_rag_config_defaults(self):
        """Test RAGConfig default values."""
        from praisonaiagents.rag.models import RAGConfig, RetrievalStrategy
        
        config = RAGConfig()
        
        assert config.top_k == 5
        assert config.min_score == 0.0
        assert config.max_context_tokens == 4000
        assert config.include_citations is True
        assert config.retrieval_strategy == RetrievalStrategy.BASIC
        assert config.rerank is False
        assert config.stream is False
        assert "{context}" in config.template
        assert "{question}" in config.template
    
    def test_rag_config_custom(self):
        """Test RAGConfig with custom values."""
        from praisonaiagents.rag.models import RAGConfig, RetrievalStrategy
        
        config = RAGConfig(
            top_k=10,
            min_score=0.5,
            retrieval_strategy=RetrievalStrategy.HYBRID,
            rerank=True,
            rerank_top_k=5
        )
        
        assert config.top_k == 10
        assert config.min_score == 0.5
        assert config.retrieval_strategy == RetrievalStrategy.HYBRID
        assert config.rerank is True
    
    def test_rag_config_to_dict(self):
        """Test RAGConfig serialization."""
        from praisonaiagents.rag.models import RAGConfig
        
        config = RAGConfig(top_k=3)
        data = config.to_dict()
        
        assert data["top_k"] == 3
        assert data["retrieval_strategy"] == "basic"
    
    def test_rag_config_from_dict(self):
        """Test RAGConfig deserialization."""
        from praisonaiagents.rag.models import RAGConfig, RetrievalStrategy
        
        data = {
            "top_k": 8,
            "retrieval_strategy": "fusion",
            "rerank": True
        }
        config = RAGConfig.from_dict(data)
        
        assert config.top_k == 8
        assert config.retrieval_strategy == RetrievalStrategy.FUSION
        assert config.rerank is True


class TestRetrievalStrategy:
    """Tests for RetrievalStrategy enum."""
    
    def test_strategy_values(self):
        """Test strategy enum values."""
        from praisonaiagents.rag.models import RetrievalStrategy
        
        assert RetrievalStrategy.BASIC.value == "basic"
        assert RetrievalStrategy.FUSION.value == "fusion"
        assert RetrievalStrategy.HYBRID.value == "hybrid"
    
    def test_strategy_from_string(self):
        """Test creating strategy from string."""
        from praisonaiagents.rag.models import RetrievalStrategy
        
        strategy = RetrievalStrategy("basic")
        assert strategy == RetrievalStrategy.BASIC
