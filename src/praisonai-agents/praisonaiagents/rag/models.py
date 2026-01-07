"""
RAG Data Models for PraisonAI Agents.

Lightweight dataclasses for RAG results and configuration.
No heavy imports - only stdlib and typing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class RetrievalStrategy(str, Enum):
    """Available retrieval strategies for RAG."""
    BASIC = "basic"
    FUSION = "fusion"
    HYBRID = "hybrid"


@dataclass
class Citation:
    """
    Source citation for RAG answers.
    
    Attributes:
        id: Unique citation identifier (e.g., "[1]", "[2]")
        source: Source document path or URL
        text: Text snippet from the source
        score: Relevance score (0-1)
        doc_id: Optional document identifier
        chunk_id: Optional chunk identifier within document
        offset: Optional character offset in source
        metadata: Additional metadata
    """
    id: str
    source: str
    text: str
    score: float = 0.0
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    offset: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "source": self.source,
            "text": self.text,
            "score": self.score,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "offset": self.offset,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Citation":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            source=data.get("source", ""),
            text=data.get("text", ""),
            score=data.get("score", 0.0),
            doc_id=data.get("doc_id"),
            chunk_id=data.get("chunk_id"),
            offset=data.get("offset"),
            metadata=data.get("metadata", {}),
        )
    
    def __str__(self) -> str:
        """Human-readable string representation."""
        snippet = self.text[:100] + "..." if len(self.text) > 100 else self.text
        return f"[{self.id}] {self.source}: {snippet}"


@dataclass
class ContextPack:
    """
    Context pack for orchestrator pattern - retrieval without generation.
    
    Provides deterministic context that can be passed to Agent.chat_with_context().
    
    Attributes:
        context: The formatted context string ready for injection
        citations: List of source citations
        query: The original query
        metadata: Additional metadata (timing, retrieval stats, etc.)
    """
    context: str
    citations: List[Citation] = field(default_factory=list)
    query: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "context": self.context,
            "citations": [c.to_dict() for c in self.citations],
            "query": self.query,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextPack":
        """Create from dictionary."""
        return cls(
            context=data.get("context", ""),
            citations=[Citation.from_dict(c) for c in data.get("citations", [])],
            query=data.get("query", ""),
            metadata=data.get("metadata", {}),
        )
    
    @property
    def has_citations(self) -> bool:
        """Check if context pack has citations."""
        return len(self.citations) > 0
    
    def format_for_prompt(self, include_sources: bool = True) -> str:
        """Format context for injection into a prompt."""
        if not include_sources or not self.citations:
            return self.context
        
        sources = "\n\nSources:\n"
        for citation in self.citations:
            sources += f"  [{citation.id}] {citation.source}\n"
        return self.context + sources


@dataclass
class RAGResult:
    """
    Result from a RAG query.
    
    Attributes:
        answer: The generated answer text
        citations: List of source citations
        context_used: The context string passed to the LLM
        query: The original query
        metadata: Additional metadata (timing, model info, etc.)
    """
    answer: str
    citations: List[Citation] = field(default_factory=list)
    context_used: str = ""
    query: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "context_used": self.context_used,
            "query": self.query,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGResult":
        """Create from dictionary."""
        return cls(
            answer=data.get("answer", ""),
            citations=[Citation.from_dict(c) for c in data.get("citations", [])],
            context_used=data.get("context_used", ""),
            query=data.get("query", ""),
            metadata=data.get("metadata", {}),
        )
    
    @property
    def has_citations(self) -> bool:
        """Check if result has citations."""
        return len(self.citations) > 0
    
    def format_answer_with_citations(self) -> str:
        """Format answer with inline citation references."""
        if not self.citations:
            return self.answer
        
        # Build citation reference section
        refs = "\n\nSources:\n"
        for citation in self.citations:
            refs += f"  {citation}\n"
        
        return self.answer + refs


@dataclass
class RAGConfig:
    """
    Configuration for RAG pipeline.
    
    Attributes:
        top_k: Number of chunks to retrieve
        min_score: Minimum relevance score threshold
        max_context_tokens: Maximum tokens for context
        include_citations: Whether to include citations in result
        retrieval_strategy: Strategy for retrieval (basic, fusion, hybrid)
        rerank: Whether to rerank results
        rerank_top_k: Number of results after reranking
        template: Prompt template with {context} and {question} placeholders
        system_prompt: Optional system prompt for LLM
        stream: Whether to stream responses
    """
    top_k: int = 5
    min_score: float = 0.0
    max_context_tokens: int = 4000
    include_citations: bool = True
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.BASIC
    rerank: bool = False
    rerank_top_k: int = 3
    model: Optional[str] = None  # LLM model to use, defaults to gpt-4o-mini
    template: str = """Answer the question based on the context below.

Context:
{context}

Question: {question}

Answer:"""
    system_prompt: Optional[str] = None
    stream: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "top_k": self.top_k,
            "min_score": self.min_score,
            "max_context_tokens": self.max_context_tokens,
            "include_citations": self.include_citations,
            "retrieval_strategy": self.retrieval_strategy.value,
            "rerank": self.rerank,
            "rerank_top_k": self.rerank_top_k,
            "template": self.template,
            "system_prompt": self.system_prompt,
            "stream": self.stream,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGConfig":
        """Create from dictionary."""
        strategy = data.get("retrieval_strategy", "basic")
        if isinstance(strategy, str):
            strategy = RetrievalStrategy(strategy)
        
        return cls(
            top_k=data.get("top_k", 5),
            min_score=data.get("min_score", 0.0),
            max_context_tokens=data.get("max_context_tokens", 4000),
            include_citations=data.get("include_citations", True),
            retrieval_strategy=strategy,
            rerank=data.get("rerank", False),
            rerank_top_k=data.get("rerank_top_k", 3),
            template=data.get("template", cls.template),
            system_prompt=data.get("system_prompt"),
            stream=data.get("stream", False),
        )
