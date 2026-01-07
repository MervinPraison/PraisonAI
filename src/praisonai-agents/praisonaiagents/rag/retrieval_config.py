"""
RetrievalConfig - Unified configuration for Agent retrieval behavior.

This is the SINGLE configuration surface for all retrieval settings.
Replaces separate knowledge_config and rag_config parameters.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum


class RetrievalPolicy(str, Enum):
    """Policy for when to perform retrieval."""
    AUTO = "auto"      # Decide based on query heuristics
    ALWAYS = "always"  # Always retrieve
    NEVER = "never"    # Never retrieve (direct chat only)


class CitationsMode(str, Enum):
    """How to include citations in responses."""
    APPEND = "append"    # Append sources at end
    INLINE = "inline"    # Inline citation markers
    HIDDEN = "hidden"    # Include in metadata only, not in response text


@dataclass
class RetrievalConfig:
    """
    Unified configuration for Agent retrieval behavior.
    
    This is the SINGLE configuration surface that replaces:
    - knowledge_config
    - rag_config
    
    Attributes:
        enabled: Whether retrieval is enabled (default: True if knowledge provided)
        policy: When to retrieve (auto, always, never)
        top_k: Number of chunks to retrieve
        min_score: Minimum relevance score threshold (0.0-1.0)
        max_context_tokens: Maximum tokens for retrieved context
        rerank: Whether to rerank results for better relevance
        hybrid: Whether to use hybrid retrieval (dense + keyword)
        citations: Whether to include source citations
        citations_mode: How to include citations (append, inline, hidden)
        
        # Vector store configuration
        vector_store_provider: Vector store provider (chroma, mongodb, etc.)
        vector_store_config: Provider-specific configuration
        collection_name: Collection/index name
        persist_path: Path for persistent storage
        
        # Embedding configuration
        embedder_provider: Embedding provider
        embedder_model: Embedding model name
        
        # Advanced options
        auto_keywords: Keywords that trigger retrieval in auto mode
        auto_min_length: Minimum query length for auto retrieval
        context_template: Template for formatting retrieved context
        system_separation: Whether to use system prompt separation for safety
    """
    # Core retrieval settings
    enabled: bool = True
    policy: RetrievalPolicy = RetrievalPolicy.AUTO
    top_k: int = 5
    min_score: float = 0.0
    max_context_tokens: int = 4000
    rerank: bool = False
    hybrid: bool = False
    citations: bool = True
    citations_mode: CitationsMode = CitationsMode.APPEND
    
    # Vector store configuration
    vector_store_provider: str = "chroma"
    vector_store_config: Dict[str, Any] = field(default_factory=dict)
    collection_name: Optional[str] = None
    persist_path: str = ".praison"
    
    # Embedding configuration
    embedder_provider: Optional[str] = None
    embedder_model: Optional[str] = None
    
    # Auto mode heuristics
    auto_keywords: frozenset = field(default_factory=lambda: frozenset({
        "what", "how", "why", "when", "where", "who", "which",
        "explain", "describe", "summarize", "find", "search",
        "tell me", "show me", "according to", "based on",
        "cite", "source", "reference", "document", "paper",
    }))
    auto_min_length: int = 10
    
    # Context formatting
    context_template: str = """<retrieved_context>
{context}
</retrieved_context>"""
    system_separation: bool = True  # Use system prompt separation for safety
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "policy": self.policy.value if isinstance(self.policy, RetrievalPolicy) else self.policy,
            "top_k": self.top_k,
            "min_score": self.min_score,
            "max_context_tokens": self.max_context_tokens,
            "rerank": self.rerank,
            "hybrid": self.hybrid,
            "citations": self.citations,
            "citations_mode": self.citations_mode.value if isinstance(self.citations_mode, CitationsMode) else self.citations_mode,
            "vector_store_provider": self.vector_store_provider,
            "vector_store_config": self.vector_store_config,
            "collection_name": self.collection_name,
            "persist_path": self.persist_path,
            "embedder_provider": self.embedder_provider,
            "embedder_model": self.embedder_model,
            "auto_min_length": self.auto_min_length,
            "context_template": self.context_template,
            "system_separation": self.system_separation,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrievalConfig":
        """Create from dictionary."""
        policy = data.get("policy", "auto")
        if isinstance(policy, str):
            policy = RetrievalPolicy(policy)
        
        citations_mode = data.get("citations_mode", "append")
        if isinstance(citations_mode, str):
            citations_mode = CitationsMode(citations_mode)
        
        auto_keywords = data.get("auto_keywords")
        if auto_keywords is not None:
            if isinstance(auto_keywords, (list, set)):
                auto_keywords = frozenset(auto_keywords)
        else:
            auto_keywords = cls.__dataclass_fields__["auto_keywords"].default_factory()
        
        return cls(
            enabled=data.get("enabled", True),
            policy=policy,
            top_k=data.get("top_k", 5),
            min_score=data.get("min_score", 0.0),
            max_context_tokens=data.get("max_context_tokens", 4000),
            rerank=data.get("rerank", False),
            hybrid=data.get("hybrid", False),
            citations=data.get("citations", True),
            citations_mode=citations_mode,
            vector_store_provider=data.get("vector_store_provider", "chroma"),
            vector_store_config=data.get("vector_store_config", {}),
            collection_name=data.get("collection_name"),
            persist_path=data.get("persist_path", ".praison"),
            embedder_provider=data.get("embedder_provider"),
            embedder_model=data.get("embedder_model"),
            auto_keywords=auto_keywords,
            auto_min_length=data.get("auto_min_length", 10),
            context_template=data.get("context_template", cls.__dataclass_fields__["context_template"].default),
            system_separation=data.get("system_separation", True),
        )
    
    def to_knowledge_config(self) -> Dict[str, Any]:
        """Convert to Knowledge-compatible config."""
        config = {
            "vector_store": {
                "provider": self.vector_store_provider,
                "config": {
                    "path": self.persist_path,
                    **self.vector_store_config,
                }
            }
        }
        if self.collection_name:
            config["vector_store"]["config"]["collection_name"] = self.collection_name
        
        if self.embedder_provider or self.embedder_model:
            config["embedder"] = {}
            if self.embedder_provider:
                config["embedder"]["provider"] = self.embedder_provider
            if self.embedder_model:
                config["embedder"]["config"] = {"model": self.embedder_model}
        
        if self.rerank:
            config["reranker"] = {"enabled": True, "default_rerank": True}
        
        return config
    
    def to_rag_config(self) -> Dict[str, Any]:
        """Convert to RAG pipeline config."""
        from .models import RetrievalStrategy
        
        strategy = RetrievalStrategy.HYBRID if self.hybrid else RetrievalStrategy.BASIC
        
        return {
            "top_k": self.top_k,
            "min_score": self.min_score,
            "max_context_tokens": self.max_context_tokens,
            "include_citations": self.citations,
            "retrieval_strategy": strategy,
            "rerank": self.rerank,
        }
    
    def should_retrieve(self, query: str, force: bool = False, skip: bool = False) -> bool:
        """
        Determine if retrieval should be performed for a query.
        
        Args:
            query: The user query
            force: Force retrieval regardless of policy
            skip: Skip retrieval regardless of policy
            
        Returns:
            True if retrieval should be performed
        """
        if not self.enabled:
            return False
        if skip:
            return False
        if force:
            return True
        
        if self.policy == RetrievalPolicy.ALWAYS:
            return True
        elif self.policy == RetrievalPolicy.NEVER:
            return False
        else:  # AUTO
            return self._needs_retrieval(query)
    
    def _needs_retrieval(self, query: str) -> bool:
        """Check if query needs retrieval based on heuristics."""
        # Check minimum length
        if len(query.strip()) < self.auto_min_length:
            return False
        
        # Check for keywords
        query_lower = query.lower()
        for keyword in self.auto_keywords:
            if keyword in query_lower:
                return True
        
        # Check for question marks
        if "?" in query:
            return True
        
        return False


# Convenience function to create config from legacy parameters
def create_retrieval_config(
    knowledge_config: Optional[Dict[str, Any]] = None,
    rag_config: Optional[Dict[str, Any]] = None,
    retrieval_config: Optional[Dict[str, Any]] = None,
) -> Optional[RetrievalConfig]:
    """
    Create RetrievalConfig from various input formats.
    
    Supports:
    - New unified retrieval_config dict
    - Legacy knowledge_config + rag_config dicts
    - RetrievalConfig instance passthrough
    
    Args:
        knowledge_config: Legacy knowledge configuration
        rag_config: Legacy RAG configuration
        retrieval_config: New unified configuration
        
    Returns:
        RetrievalConfig instance or None
    """
    if retrieval_config is not None:
        if isinstance(retrieval_config, RetrievalConfig):
            return retrieval_config
        return RetrievalConfig.from_dict(retrieval_config)
    
    if knowledge_config is None and rag_config is None:
        return None
    
    # Merge legacy configs
    merged = {}
    
    if knowledge_config:
        # Extract vector store settings
        vs = knowledge_config.get("vector_store", {})
        if vs:
            merged["vector_store_provider"] = vs.get("provider", "chroma")
            merged["vector_store_config"] = vs.get("config", {})
            if "collection_name" in vs.get("config", {}):
                merged["collection_name"] = vs["config"]["collection_name"]
            if "path" in vs.get("config", {}):
                merged["persist_path"] = vs["config"]["path"]
        
        # Extract embedder settings
        emb = knowledge_config.get("embedder", {})
        if emb:
            merged["embedder_provider"] = emb.get("provider")
            if "config" in emb and "model" in emb["config"]:
                merged["embedder_model"] = emb["config"]["model"]
    
    if rag_config:
        # Map RAG config fields
        if "top_k" in rag_config:
            merged["top_k"] = rag_config["top_k"]
        if "min_score" in rag_config:
            merged["min_score"] = rag_config["min_score"]
        if "max_context_tokens" in rag_config:
            merged["max_context_tokens"] = rag_config["max_context_tokens"]
        if "include_citations" in rag_config:
            merged["citations"] = rag_config["include_citations"]
        if "rerank" in rag_config:
            merged["rerank"] = rag_config["rerank"]
        if "retrieval_strategy" in rag_config:
            strategy = rag_config["retrieval_strategy"]
            if strategy == "hybrid":
                merged["hybrid"] = True
    
    return RetrievalConfig.from_dict(merged) if merged else RetrievalConfig()
