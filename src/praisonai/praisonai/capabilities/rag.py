"""
RAG (Retrieval-Augmented Generation) Capabilities Module

Provides RAG functionality for document retrieval and generation.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class RAGResult:
    """Result from RAG operations."""
    answer: str
    sources: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def rag_query(
    query: str,
    documents: Optional[List[str]] = None,
    vector_store_id: Optional[str] = None,
    model: str = "gpt-4o-mini",
    max_results: int = 5,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> RAGResult:
    """
    Perform a RAG query.
    
    Args:
        query: Query string
        documents: Optional list of documents to search
        vector_store_id: Optional vector store ID to search
        model: Model to use for generation
        max_results: Maximum number of results to retrieve
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        RAGResult with answer and sources
        
    Example:
        >>> result = rag_query("What is AI?", documents=["AI is..."])
        >>> print(result.answer)
    """
    import litellm
    
    sources = []
    context = ""
    
    # If vector store provided, search it
    if vector_store_id:
        try:
            from .vector_stores import vector_store_search
            search_result = vector_store_search(
                vector_store_id=vector_store_id,
                query=query,
                max_num_results=max_results,
                api_key=api_key,
                api_base=api_base,
            )
            for r in search_result.results:
                if 'content' in r:
                    for c in r['content']:
                        text = c.get('text', '')
                        context += f"\n{text}"
                        sources.append({
                            'score': r.get('score', 0),
                            'text': text[:200],
                        })
        except Exception:
            pass
    
    # If documents provided, use them as context
    if documents:
        for i, doc in enumerate(documents[:max_results]):
            context += f"\n{doc}"
            sources.append({
                'index': i,
                'text': doc[:200],
            })
    
    # Generate answer
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Answer the question based on the provided context. If the context doesn't contain relevant information, say so."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
    ]
    
    response = litellm.completion(
        model=model,
        messages=messages,
        timeout=timeout,
        api_key=api_key,
        api_base=api_base,
        **kwargs
    )
    
    answer = response.choices[0].message.content if response.choices else ""
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    return RAGResult(
        answer=answer,
        sources=sources if sources else None,
        model=model,
        usage=usage,
        metadata=metadata or {},
    )


async def arag_query(
    query: str,
    documents: Optional[List[str]] = None,
    vector_store_id: Optional[str] = None,
    model: str = "gpt-4o-mini",
    max_results: int = 5,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> RAGResult:
    """
    Async: Perform a RAG query.
    
    See rag_query() for full documentation.
    """
    import litellm
    
    sources = []
    context = ""
    
    if vector_store_id:
        try:
            from .vector_stores import avector_store_search
            search_result = await avector_store_search(
                vector_store_id=vector_store_id,
                query=query,
                max_num_results=max_results,
                api_key=api_key,
                api_base=api_base,
            )
            for r in search_result.results:
                if 'content' in r:
                    for c in r['content']:
                        text = c.get('text', '')
                        context += f"\n{text}"
                        sources.append({
                            'score': r.get('score', 0),
                            'text': text[:200],
                        })
        except Exception:
            pass
    
    if documents:
        for i, doc in enumerate(documents[:max_results]):
            context += f"\n{doc}"
            sources.append({
                'index': i,
                'text': doc[:200],
            })
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Answer the question based on the provided context. If the context doesn't contain relevant information, say so."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
    ]
    
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        timeout=timeout,
        api_key=api_key,
        api_base=api_base,
        **kwargs
    )
    
    answer = response.choices[0].message.content if response.choices else ""
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    return RAGResult(
        answer=answer,
        sources=sources if sources else None,
        model=model,
        usage=usage,
        metadata=metadata or {},
    )
