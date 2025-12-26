"""
Reranker Implementations for PraisonAI.

Provides concrete implementations of RerankerProtocol:
- LLMReranker: Uses LLM to rerank documents
- CrossEncoderReranker: Uses sentence-transformers cross-encoder
- CohereReranker: Uses Cohere rerank API
"""

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Lazy import flags
_SENTENCE_TRANSFORMERS_AVAILABLE = None
_COHERE_AVAILABLE = None


def _check_sentence_transformers():
    """Check if sentence-transformers is available."""
    global _SENTENCE_TRANSFORMERS_AVAILABLE
    if _SENTENCE_TRANSFORMERS_AVAILABLE is None:
        import importlib.util
        _SENTENCE_TRANSFORMERS_AVAILABLE = importlib.util.find_spec("sentence_transformers") is not None
    return _SENTENCE_TRANSFORMERS_AVAILABLE


def _check_cohere():
    """Check if cohere is available."""
    global _COHERE_AVAILABLE
    if _COHERE_AVAILABLE is None:
        import importlib.util
        _COHERE_AVAILABLE = importlib.util.find_spec("cohere") is not None
    return _COHERE_AVAILABLE


class LLMReranker:
    """
    LLM-based reranker.
    
    Uses an LLM to score document relevance to a query.
    """
    
    name: str = "llm"
    
    def __init__(
        self,
        llm: Optional[Any] = None,
        model: Optional[str] = None,
        batch_size: int = 5,
        **kwargs
    ):
        self.llm = llm
        self.model = model or "gpt-4o-mini"
        self.batch_size = batch_size
        self._client = None
    
    def _get_client(self):
        """Get LLM client - returns self.llm if provided, otherwise None (use litellm)."""
        if self.llm:
            return self.llm
        return None  # Will use litellm directly
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[Any]:
        """Rerank documents using LLM scoring."""
        from praisonaiagents.knowledge.rerankers import RerankResult
        
        results = []
        
        # Process in batches
        for i in range(0, len(documents), self.batch_size):
            batch = documents[i:i + self.batch_size]
            batch_results = self._score_batch(query, batch, start_idx=i)
            results.extend(batch_results)
        
        # Sort by score
        results.sort(key=lambda x: x.score, reverse=True)
        
        if top_k is not None:
            results = results[:top_k]
        
        return results
    
    async def arerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[Any]:
        """Async version (just calls sync)."""
        return self.rerank(query, documents, top_k, **kwargs)
    
    def _score_batch(self, query: str, documents: List[str], start_idx: int = 0) -> List[Any]:
        """Score a batch of documents."""
        from praisonaiagents.knowledge.rerankers import RerankResult
        
        results = []
        
        for i, doc in enumerate(documents):
            score = self._score_document(query, doc)
            results.append(RerankResult(
                text=doc,
                score=score,
                original_index=start_idx + i
            ))
        
        return results
    
    def _score_document(self, query: str, document: str) -> float:
        """Score a single document's relevance to query using litellm."""
        try:
            client = self._get_client()
            
            prompt = f"""Rate the relevance of this document to the query on a scale of 0 to 10.
Return ONLY a number between 0 and 10.

Query: {query}

Document: {document[:1000]}

Relevance score (0-10):"""
            
            # Check if client has a callable 'chat' method (PraisonAI Agent)
            if client is not None and hasattr(client, 'chat') and callable(getattr(client, 'chat', None)):
                # PraisonAI Agent or similar with callable chat method
                response = client.chat(prompt)
            else:
                # Use litellm for unified multi-provider support
                import litellm
                
                # litellm handles model-specific quirks automatically
                completion = litellm.completion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10
                )
                response = completion.choices[0].message.content
            
            # Parse score
            if response:
                try:
                    score = float(response.strip().split()[0])
                    return min(max(score / 10.0, 0.0), 1.0)  # Normalize to 0-1
                except (ValueError, IndexError):
                    pass
        except Exception as e:
            logger.warning(f"LLM scoring failed: {e}")
        
        return 0.5  # Default score


class CrossEncoderReranker:
    """
    Cross-encoder reranker using sentence-transformers.
    
    Uses a cross-encoder model for accurate relevance scoring.
    """
    
    name: str = "cross_encoder"
    
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        **kwargs
    ):
        if not _check_sentence_transformers():
            raise ImportError(
                "sentence-transformers is required for CrossEncoderReranker. "
                "Install with: pip install sentence-transformers"
            )
        
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name)
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[Any]:
        """Rerank documents using cross-encoder."""
        from praisonaiagents.knowledge.rerankers import RerankResult
        
        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]
        
        # Get scores
        scores = self.model.predict(pairs)
        
        # Create results
        results = []
        for i, (doc, score) in enumerate(zip(documents, scores)):
            results.append(RerankResult(
                text=doc,
                score=float(score),
                original_index=i
            ))
        
        # Sort by score
        results.sort(key=lambda x: x.score, reverse=True)
        
        if top_k is not None:
            results = results[:top_k]
        
        return results
    
    async def arerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[Any]:
        """Async version (just calls sync)."""
        return self.rerank(query, documents, top_k, **kwargs)


class CohereReranker:
    """
    Cohere reranker using Cohere's rerank API.
    """
    
    name: str = "cohere"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "rerank-english-v3.0",
        **kwargs
    ):
        if not _check_cohere():
            raise ImportError(
                "cohere is required for CohereReranker. "
                "Install with: pip install cohere"
            )
        
        import os
        import cohere
        
        self.api_key = api_key or os.environ.get("COHERE_API_KEY")
        if not self.api_key:
            raise ValueError("COHERE_API_KEY environment variable or api_key parameter required")
        
        self.model = model
        self._client = cohere.Client(self.api_key)
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[Any]:
        """Rerank documents using Cohere API."""
        from praisonaiagents.knowledge.rerankers import RerankResult
        
        response = self._client.rerank(
            query=query,
            documents=documents,
            top_n=top_k or len(documents),
            model=self.model
        )
        
        results = []
        for r in response.results:
            results.append(RerankResult(
                text=documents[r.index],
                score=r.relevance_score,
                original_index=r.index
            ))
        
        return results
    
    async def arerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[Any]:
        """Async version (just calls sync)."""
        return self.rerank(query, documents, top_k, **kwargs)


def register_default_rerankers():
    """Register all default rerankers with the registry."""
    from praisonaiagents.knowledge.rerankers import get_reranker_registry
    
    registry = get_reranker_registry()
    
    # LLM reranker is always available
    registry.register("llm", LLMReranker)
    
    # Cross-encoder if available
    if _check_sentence_transformers():
        registry.register("cross_encoder", CrossEncoderReranker)
    
    # Cohere if available
    if _check_cohere():
        registry.register("cohere", CohereReranker)
    
    logger.debug("Registered default rerankers")


# Auto-register on import
register_default_rerankers()
