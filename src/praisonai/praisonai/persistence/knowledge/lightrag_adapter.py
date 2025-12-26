"""
LightRAG adapter implementation of KnowledgeStore.

Requires: lightrag
Install: pip install lightrag
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class LightRAGKnowledgeStore(KnowledgeStore):
    """
    LightRAG adapter for knowledge/RAG.
    
    Wraps LightRAG for use with PraisonAI's KnowledgeStore interface.
    
    Example:
        store = LightRAGKnowledgeStore(
            working_dir="./lightrag_data"
        )
    """
    
    def __init__(
        self,
        working_dir: str = "./lightrag_data",
        llm_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        **kwargs
    ):
        """
        Initialize LightRAG adapter.
        
        Args:
            working_dir: Directory for LightRAG data
            llm_model: LLM model for graph extraction
            embedding_model: Embedding model name
            **kwargs: Additional LightRAG options
        """
        self.working_dir = working_dir
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.kwargs = kwargs
        
        self._rag = None
        self._initialized = False
    
    def _init_client(self):
        """Initialize LightRAG client lazily."""
        if self._initialized:
            return
        
        try:
            from lightrag import LightRAG, QueryParam
            from lightrag.llm import gpt_4o_mini_complete, openai_embedding
        except ImportError:
            raise ImportError(
                "lightrag is required for LightRAG support. "
                "Install with: pip install lightrag"
            )
        
        self._QueryParam = QueryParam
        self._rag = LightRAG(
            working_dir=self.working_dir,
            llm_model_func=gpt_4o_mini_complete,
            embedding_func=openai_embedding,
            **self.kwargs
        )
        self._initialized = True
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create collection (LightRAG uses working directory)."""
        self._init_client()
        logger.info(f"LightRAG uses working_dir: {self.working_dir}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete collection data."""
        import shutil
        import os
        
        try:
            if os.path.exists(self.working_dir):
                shutil.rmtree(self.working_dir)
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if working directory exists."""
        import os
        return os.path.exists(self.working_dir)
    
    def list_collections(self) -> List[str]:
        """List collections (single collection per working_dir)."""
        import os
        if os.path.exists(self.working_dir):
            return ["default"]
        return []
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents into LightRAG."""
        self._init_client()
        
        ids = []
        for doc in documents:
            try:
                self._rag.insert(doc.content)
                ids.append(doc.id)
            except Exception as e:
                logger.warning(f"Failed to insert document {doc.id}: {e}")
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents (same as insert for LightRAG)."""
        return self.insert(collection, documents)
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search using LightRAG's query method."""
        self._init_client()
        
        # LightRAG uses text query, not embeddings directly
        # This is a limitation - we need the original query text
        logger.warning(
            "LightRAG search requires text query, not embeddings. "
            "Use query() method directly for best results."
        )
        return []
    
    def query(
        self,
        query_text: str,
        mode: str = "hybrid",
        limit: int = 5
    ) -> str:
        """
        Query LightRAG with text (native method).
        
        Args:
            query_text: The query string
            mode: Query mode (naive, local, global, hybrid)
            limit: Maximum results
        
        Returns:
            Query response as string
        """
        self._init_client()
        
        try:
            result = self._rag.query(
                query_text,
                param=self._QueryParam(mode=mode, top_k=limit)
            )
            return result
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return ""
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs (not supported by LightRAG)."""
        logger.warning("LightRAG does not support get by ID")
        return []
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents (not directly supported)."""
        logger.warning("LightRAG does not support individual document deletion")
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents (not directly supported)."""
        logger.warning("LightRAG does not support document counting")
        return -1
    
    def close(self) -> None:
        """Close the client."""
        self._rag = None
        self._initialized = False
