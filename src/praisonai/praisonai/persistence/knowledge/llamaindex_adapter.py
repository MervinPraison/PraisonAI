"""
LlamaIndex VectorStore adapter implementation of KnowledgeStore.

Wraps any LlamaIndex VectorStore for use with PraisonAI.

Requires: llama-index-core
Install: pip install llama-index-core
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class LlamaIndexKnowledgeStore(KnowledgeStore):
    """
    LlamaIndex VectorStore adapter for knowledge/RAG.
    
    Wraps any LlamaIndex VectorStore for use with PraisonAI's interface.
    
    Example:
        from llama_index.vector_stores.chroma import ChromaVectorStore
        
        li_store = ChromaVectorStore(chroma_collection=collection)
        store = LlamaIndexKnowledgeStore(vector_store=li_store)
    """
    
    def __init__(
        self,
        vector_store: Any = None,
        vector_store_cls: Optional[str] = None,
        vector_store_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize LlamaIndex adapter.
        
        Args:
            vector_store: Pre-initialized LlamaIndex VectorStore instance
            vector_store_cls: Class name to import (e.g., "llama_index.vector_stores.chroma.ChromaVectorStore")
            vector_store_kwargs: Kwargs for vector_store initialization
        """
        self._vector_store = vector_store
        self._vector_store_cls = vector_store_cls
        self._vector_store_kwargs = vector_store_kwargs or {}
        self._initialized = vector_store is not None
    
    def _init_client(self):
        """Initialize vector store lazily."""
        if self._initialized:
            return
        
        if not self._vector_store_cls:
            raise ValueError(
                "Either vector_store or vector_store_cls must be provided"
            )
        
        # Dynamic import of vector store class
        parts = self._vector_store_cls.rsplit(".", 1)
        if len(parts) == 2:
            module_name, class_name = parts
            import importlib
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            self._vector_store = cls(**self._vector_store_kwargs)
        else:
            raise ValueError(f"Invalid vector_store_cls: {self._vector_store_cls}")
        
        self._initialized = True
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create collection (handled by underlying vector store)."""
        self._init_client()
        logger.info("Collection creation handled by LlamaIndex vector store")
    
    def delete_collection(self, name: str) -> bool:
        """Delete collection."""
        self._init_client()
        try:
            if hasattr(self._vector_store, 'delete'):
                self._vector_store.delete(delete_all=True)
                return True
            logger.warning("Underlying vector store doesn't support delete")
            return False
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if collection exists."""
        self._init_client()
        return self._vector_store is not None
    
    def list_collections(self) -> List[str]:
        """List collections."""
        self._init_client()
        return ["default"]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        self._init_client()
        
        try:
            from llama_index.core.schema import TextNode
        except ImportError:
            raise ImportError(
                "llama-index-core is required. Install with: pip install llama-index-core"
            )
        
        nodes = []
        ids = []
        for doc in documents:
            node = TextNode(
                text=doc.content,
                id_=doc.id,
                metadata={
                    **(doc.metadata or {}),
                    "content_hash": doc.content_hash,
                    "created_at": doc.created_at,
                },
                embedding=doc.embedding
            )
            nodes.append(node)
            ids.append(doc.id)
        
        if hasattr(self._vector_store, 'add'):
            self._vector_store.add(nodes)
        else:
            logger.warning("Vector store doesn't support add")
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents."""
        return self.insert(collection, documents)
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents."""
        self._init_client()
        
        try:
            from llama_index.core.vector_stores import VectorStoreQuery
        except ImportError:
            raise ImportError(
                "llama-index-core is required. Install with: pip install llama-index-core"
            )
        
        try:
            query = VectorStoreQuery(
                query_embedding=query_embedding,
                similarity_top_k=limit,
            )
            
            result = self._vector_store.query(query)
            
            documents = []
            for i, node in enumerate(result.nodes or []):
                score = result.similarities[i] if result.similarities else None
                if score_threshold and score and score < score_threshold:
                    continue
                
                metadata = node.metadata or {}
                if score:
                    metadata["score"] = score
                
                documents.append(KnowledgeDocument(
                    id=node.node_id or node.id_,
                    content=node.text or node.get_content(),
                    embedding=node.embedding,
                    metadata=metadata,
                    content_hash=metadata.get("content_hash"),
                    created_at=metadata.get("created_at", 0)
                ))
            
            return documents
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        self._init_client()
        
        documents = []
        for doc_id in ids:
            try:
                if hasattr(self._vector_store, 'get'):
                    node = self._vector_store.get(doc_id)
                    if node:
                        metadata = node.metadata or {}
                        documents.append(KnowledgeDocument(
                            id=node.node_id or node.id_,
                            content=node.text or node.get_content(),
                            embedding=node.embedding,
                            metadata=metadata
                        ))
            except Exception as e:
                logger.warning(f"Get by ID failed for {doc_id}: {e}")
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        self._init_client()
        
        if ids and hasattr(self._vector_store, 'delete'):
            try:
                self._vector_store.delete(ref_doc_id=ids[0] if len(ids) == 1 else None)
                return len(ids)
            except Exception as e:
                logger.error(f"Delete failed: {e}")
        
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        self._init_client()
        logger.warning("LlamaIndex vector stores don't typically support counting")
        return -1
    
    def close(self) -> None:
        """Close the client."""
        self._vector_store = None
        self._initialized = False
