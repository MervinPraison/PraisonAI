"""
PraisonAI Knowledge - Advanced knowledge management system with configurable features.

This module provides:
- Document readers (ReaderProtocol, ReaderRegistry)
- Vector stores (VectorStoreProtocol, VectorStoreRegistry)
- Retrieval strategies (RetrieverProtocol, RetrievalStrategy)
- Rerankers (RerankerProtocol, RerankerRegistry)
- Index types (IndexProtocol, IndexType)
- Query engines (QueryEngineProtocol, QueryMode)
"""

# Core Knowledge class (always available)
from praisonaiagents.knowledge.knowledge import Knowledge
from praisonaiagents.knowledge.chunking import Chunking

# Lazy loading for protocols and registries to avoid import overhead
_LAZY_IMPORTS = {
    # Models and Protocols (new)
    "SearchResultItem": ("praisonaiagents.knowledge.models", "SearchResultItem"),
    "SearchResult": ("praisonaiagents.knowledge.models", "SearchResult"),
    "AddResult": ("praisonaiagents.knowledge.models", "AddResult"),
    "normalize_search_item": ("praisonaiagents.knowledge.models", "normalize_search_item"),
    "normalize_search_result": ("praisonaiagents.knowledge.models", "normalize_search_result"),
    "normalize_to_dict": ("praisonaiagents.knowledge.models", "normalize_to_dict"),
    "KnowledgeStoreProtocol": ("praisonaiagents.knowledge.protocols", "KnowledgeStoreProtocol"),
    "KnowledgeBackendError": ("praisonaiagents.knowledge.protocols", "KnowledgeBackendError"),
    "ScopeRequiredError": ("praisonaiagents.knowledge.protocols", "ScopeRequiredError"),
    "BackendNotAvailableError": ("praisonaiagents.knowledge.protocols", "BackendNotAvailableError"),
    
    # Readers
    "Document": ("praisonaiagents.knowledge.readers", "Document"),
    "ReaderProtocol": ("praisonaiagents.knowledge.readers", "ReaderProtocol"),
    "ReaderRegistry": ("praisonaiagents.knowledge.readers", "ReaderRegistry"),
    "get_reader_registry": ("praisonaiagents.knowledge.readers", "get_reader_registry"),
    "detect_source_kind": ("praisonaiagents.knowledge.readers", "detect_source_kind"),
    
    # Vector stores
    "VectorRecord": ("praisonaiagents.knowledge.vector_store", "VectorRecord"),
    "VectorStoreProtocol": ("praisonaiagents.knowledge.vector_store", "VectorStoreProtocol"),
    "VectorStoreRegistry": ("praisonaiagents.knowledge.vector_store", "VectorStoreRegistry"),
    "get_vector_store_registry": ("praisonaiagents.knowledge.vector_store", "get_vector_store_registry"),
    "InMemoryVectorStore": ("praisonaiagents.knowledge.vector_store", "InMemoryVectorStore"),
    
    # Retrieval
    "RetrievalResult": ("praisonaiagents.knowledge.retrieval", "RetrievalResult"),
    "RetrievalStrategy": ("praisonaiagents.knowledge.retrieval", "RetrievalStrategy"),
    "RetrieverProtocol": ("praisonaiagents.knowledge.retrieval", "RetrieverProtocol"),
    "RetrieverRegistry": ("praisonaiagents.knowledge.retrieval", "RetrieverRegistry"),
    "get_retriever_registry": ("praisonaiagents.knowledge.retrieval", "get_retriever_registry"),
    "reciprocal_rank_fusion": ("praisonaiagents.knowledge.retrieval", "reciprocal_rank_fusion"),
    "merge_adjacent_chunks": ("praisonaiagents.knowledge.retrieval", "merge_adjacent_chunks"),
    
    # Rerankers
    "RerankResult": ("praisonaiagents.knowledge.rerankers", "RerankResult"),
    "RerankerProtocol": ("praisonaiagents.knowledge.rerankers", "RerankerProtocol"),
    "RerankerRegistry": ("praisonaiagents.knowledge.rerankers", "RerankerRegistry"),
    "get_reranker_registry": ("praisonaiagents.knowledge.rerankers", "get_reranker_registry"),
    "SimpleReranker": ("praisonaiagents.knowledge.rerankers", "SimpleReranker"),
    
    # Index
    "IndexType": ("praisonaiagents.knowledge.index", "IndexType"),
    "IndexStats": ("praisonaiagents.knowledge.index", "IndexStats"),
    "IndexProtocol": ("praisonaiagents.knowledge.index", "IndexProtocol"),
    "IndexRegistry": ("praisonaiagents.knowledge.index", "IndexRegistry"),
    "get_index_registry": ("praisonaiagents.knowledge.index", "get_index_registry"),
    "KeywordIndex": ("praisonaiagents.knowledge.index", "KeywordIndex"),
    
    # Query engine
    "QueryMode": ("praisonaiagents.knowledge.query_engine", "QueryMode"),
    "QueryResult": ("praisonaiagents.knowledge.query_engine", "QueryResult"),
    "QueryEngineProtocol": ("praisonaiagents.knowledge.query_engine", "QueryEngineProtocol"),
    "QueryEngineRegistry": ("praisonaiagents.knowledge.query_engine", "QueryEngineRegistry"),
    "get_query_engine_registry": ("praisonaiagents.knowledge.query_engine", "get_query_engine_registry"),
    "decompose_question": ("praisonaiagents.knowledge.query_engine", "decompose_question"),
    "SimpleQueryEngine": ("praisonaiagents.knowledge.query_engine", "SimpleQueryEngine"),
    "SubQuestionEngine": ("praisonaiagents.knowledge.query_engine", "SubQuestionEngine"),
}


def __getattr__(name: str):
    """Lazy load protocols and registries."""
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """List available attributes."""
    return list(_LAZY_IMPORTS.keys()) + ["Knowledge", "Chunking"]


__all__ = [
    # Core
    "Knowledge",
    "Chunking",
    # Models and Protocols
    "SearchResultItem",
    "SearchResult",
    "AddResult",
    "normalize_search_item",
    "normalize_search_result",
    "normalize_to_dict",
    "KnowledgeStoreProtocol",
    "KnowledgeBackendError",
    "ScopeRequiredError",
    "BackendNotAvailableError",
    # Readers
    "Document",
    "ReaderProtocol",
    "ReaderRegistry",
    "get_reader_registry",
    "detect_source_kind",
    # Vector stores
    "VectorRecord",
    "VectorStoreProtocol",
    "VectorStoreRegistry",
    "get_vector_store_registry",
    "InMemoryVectorStore",
    # Retrieval
    "RetrievalResult",
    "RetrievalStrategy",
    "RetrieverProtocol",
    "RetrieverRegistry",
    "get_retriever_registry",
    "reciprocal_rank_fusion",
    "merge_adjacent_chunks",
    # Rerankers
    "RerankResult",
    "RerankerProtocol",
    "RerankerRegistry",
    "get_reranker_registry",
    "SimpleReranker",
    # Index
    "IndexType",
    "IndexStats",
    "IndexProtocol",
    "IndexRegistry",
    "get_index_registry",
    "KeywordIndex",
    # Query engine
    "QueryMode",
    "QueryResult",
    "QueryEngineProtocol",
    "QueryEngineRegistry",
    "get_query_engine_registry",
    "decompose_question",
    "SimpleQueryEngine",
    "SubQuestionEngine",
] 