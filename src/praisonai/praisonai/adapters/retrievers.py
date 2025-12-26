"""
Retriever Implementations for PraisonAI.

Provides concrete implementations of RetrieverProtocol:
- BasicRetriever: Simple vector similarity retrieval
- FusionRetriever: Multi-query with RRF fusion
- RecursiveRetriever: Depth-limited sub-retrieval
- AutoMergeRetriever: Merges adjacent chunks
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class BasicRetriever:
    """
    Basic vector similarity retriever.
    
    Simply queries the vector store and returns results.
    """
    
    name: str = "basic"
    
    def __init__(
        self,
        vector_store: Any,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 10,
        **kwargs
    ):
        self.vector_store = vector_store
        self.embedding_fn = embedding_fn
        self.top_k = top_k
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Retrieve documents by vector similarity."""
        from praisonaiagents.knowledge.retrieval import RetrievalResult
        
        k = top_k or self.top_k
        
        # Get query embedding
        if self.embedding_fn:
            query_embedding = self.embedding_fn(query)
        else:
            raise ValueError("embedding_fn is required for BasicRetriever")
        
        # Query vector store
        results = self.vector_store.query(
            embedding=query_embedding,
            top_k=k,
            filter=filter
        )
        
        # Convert to RetrievalResult
        retrieval_results = []
        for r in results:
            retrieval_results.append(RetrievalResult(
                text=r.text if hasattr(r, 'text') else str(r),
                score=r.score if hasattr(r, 'score') else 1.0,
                metadata=r.metadata if hasattr(r, 'metadata') else {},
                doc_id=r.id if hasattr(r, 'id') else None,
                chunk_index=r.metadata.get('chunk_index') if hasattr(r, 'metadata') else None
            ))
        
        return retrieval_results
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Async version (just calls sync)."""
        return self.retrieve(query, top_k, filter, **kwargs)


class FusionRetriever:
    """
    Fusion retriever using Reciprocal Rank Fusion.
    
    Generates multiple query variations and fuses results.
    """
    
    name: str = "fusion"
    
    def __init__(
        self,
        vector_store: Any,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        llm: Optional[Any] = None,
        num_queries: int = 3,
        top_k: int = 10,
        rrf_k: int = 60,
        **kwargs
    ):
        self.vector_store = vector_store
        self.embedding_fn = embedding_fn
        self.llm = llm
        self.num_queries = num_queries
        self.top_k = top_k
        self.rrf_k = rrf_k
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Retrieve with query fusion."""
        from praisonaiagents.knowledge.retrieval import RetrievalResult, reciprocal_rank_fusion
        
        k = top_k or self.top_k
        
        # Generate query variations
        queries = self._generate_query_variations(query)
        
        # Retrieve for each query
        all_results = []
        for q in queries:
            if self.embedding_fn:
                q_embedding = self.embedding_fn(q)
                results = self.vector_store.query(
                    embedding=q_embedding,
                    top_k=k,
                    filter=filter
                )
                
                # Convert to RetrievalResult
                query_results = []
                for r in results:
                    query_results.append(RetrievalResult(
                        text=r.text if hasattr(r, 'text') else str(r),
                        score=r.score if hasattr(r, 'score') else 1.0,
                        metadata=r.metadata if hasattr(r, 'metadata') else {},
                        doc_id=r.id if hasattr(r, 'id') else None
                    ))
                all_results.append(query_results)
        
        # Fuse results using RRF
        fused = reciprocal_rank_fusion(all_results, k=self.rrf_k)
        
        return fused[:k]
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Async version (just calls sync)."""
        return self.retrieve(query, top_k, filter, **kwargs)
    
    def _generate_query_variations(self, query: str) -> List[str]:
        """Generate query variations."""
        queries = [query]
        
        # Try LLM-based variation if available
        if self.llm and len(queries) < self.num_queries:
            try:
                prompt = f"""Generate {self.num_queries - 1} alternative phrasings of this search query.
Return only the queries, one per line.

Original query: {query}"""
                response = self.llm.chat(prompt)
                if response:
                    for line in response.strip().split("\n"):
                        line = line.strip()
                        if line and line != query:
                            queries.append(line)
                            if len(queries) >= self.num_queries:
                                break
            except Exception as e:
                logger.warning(f"LLM query variation failed: {e}")
        
        # Fallback: simple variations
        if len(queries) < self.num_queries:
            # Add question form
            if not query.endswith("?"):
                queries.append(f"What is {query}?")
            # Add keyword form
            keywords = " ".join(query.split()[:5])
            if keywords != query:
                queries.append(keywords)
        
        return queries[:self.num_queries]


class RecursiveRetriever:
    """
    Recursive retriever with depth-limited sub-retrieval.
    
    Retrieves, expands queries based on results, and retrieves again.
    """
    
    name: str = "recursive"
    
    def __init__(
        self,
        vector_store: Any,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        llm: Optional[Any] = None,
        max_depth: int = 2,
        top_k: int = 10,
        **kwargs
    ):
        self.vector_store = vector_store
        self.embedding_fn = embedding_fn
        self.llm = llm
        self.max_depth = max_depth
        self.top_k = top_k
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Retrieve with recursive expansion."""
        from praisonaiagents.knowledge.retrieval import RetrievalResult
        
        k = top_k or self.top_k
        seen_ids = set()
        all_results = []
        
        current_queries = [query]
        
        for depth in range(self.max_depth):
            next_queries = []
            
            for q in current_queries:
                if self.embedding_fn:
                    q_embedding = self.embedding_fn(q)
                    results = self.vector_store.query(
                        embedding=q_embedding,
                        top_k=k,
                        filter=filter
                    )
                    
                    for r in results:
                        r_id = r.id if hasattr(r, 'id') else r.text[:50]
                        if r_id not in seen_ids:
                            seen_ids.add(r_id)
                            all_results.append(RetrievalResult(
                                text=r.text if hasattr(r, 'text') else str(r),
                                score=r.score if hasattr(r, 'score') else 1.0,
                                metadata=r.metadata if hasattr(r, 'metadata') else {},
                                doc_id=r.id if hasattr(r, 'id') else None
                            ))
                            
                            # Generate follow-up query from result
                            if depth < self.max_depth - 1 and self.llm:
                                follow_up = self._generate_follow_up(query, r.text if hasattr(r, 'text') else str(r))
                                if follow_up:
                                    next_queries.append(follow_up)
            
            current_queries = next_queries[:3]  # Limit expansion
            if not current_queries:
                break
        
        # Sort by score
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:k]
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Async version (just calls sync)."""
        return self.retrieve(query, top_k, filter, **kwargs)
    
    def _generate_follow_up(self, original_query: str, context: str) -> Optional[str]:
        """Generate a follow-up query based on retrieved context."""
        if not self.llm:
            return None
        
        try:
            prompt = f"""Based on this search result, generate a follow-up query to find more relevant information.
Return only the query, nothing else.

Original query: {original_query}
Search result: {context[:500]}"""
            response = self.llm.chat(prompt)
            if response:
                return response.strip()
        except Exception as e:
            logger.warning(f"Follow-up query generation failed: {e}")
        
        return None


class AutoMergeRetriever:
    """
    Auto-merge retriever that combines adjacent chunks.
    
    Retrieves chunks and merges those from the same document.
    """
    
    name: str = "auto_merge"
    
    def __init__(
        self,
        vector_store: Any,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 10,
        max_gap: int = 1,
        **kwargs
    ):
        self.vector_store = vector_store
        self.embedding_fn = embedding_fn
        self.top_k = top_k
        self.max_gap = max_gap
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Retrieve and merge adjacent chunks."""
        from praisonaiagents.knowledge.retrieval import RetrievalResult, merge_adjacent_chunks
        
        k = top_k or self.top_k
        
        # Get more results than needed for merging
        fetch_k = k * 3
        
        if self.embedding_fn:
            q_embedding = self.embedding_fn(query)
            results = self.vector_store.query(
                embedding=q_embedding,
                top_k=fetch_k,
                filter=filter
            )
            
            # Convert to RetrievalResult
            retrieval_results = []
            for r in results:
                retrieval_results.append(RetrievalResult(
                    text=r.text if hasattr(r, 'text') else str(r),
                    score=r.score if hasattr(r, 'score') else 1.0,
                    metadata=r.metadata if hasattr(r, 'metadata') else {},
                    doc_id=r.metadata.get('doc_id') if hasattr(r, 'metadata') else None,
                    chunk_index=r.metadata.get('chunk_index') if hasattr(r, 'metadata') else None
                ))
            
            # Merge adjacent chunks
            merged = merge_adjacent_chunks(retrieval_results, max_gap=self.max_gap)
            return merged[:k]
        
        return []
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Any]:
        """Async version (just calls sync)."""
        return self.retrieve(query, top_k, filter, **kwargs)


def register_default_retrievers():
    """Register all default retrievers with the registry."""
    from praisonaiagents.knowledge.retrieval import get_retriever_registry
    
    registry = get_retriever_registry()
    
    registry.register("basic", BasicRetriever)
    registry.register("fusion", FusionRetriever)
    registry.register("recursive", RecursiveRetriever)
    registry.register("auto_merge", AutoMergeRetriever)
    
    logger.debug("Registered default retrievers")


# Auto-register on import
register_default_retrievers()
