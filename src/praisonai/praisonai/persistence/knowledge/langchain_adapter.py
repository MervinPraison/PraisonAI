"""
LangChain VectorStore adapter implementation of KnowledgeStore.

Wraps any LangChain VectorStore for use with PraisonAI.

Requires: langchain-core
Install: pip install langchain-core
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class LangChainKnowledgeStore(KnowledgeStore):
    """
    LangChain VectorStore adapter for knowledge/RAG.
    
    Wraps any LangChain VectorStore for use with PraisonAI's interface.
    
    Example:
        from langchain_chroma import Chroma
        
        lc_store = Chroma(persist_directory="./chroma_db")
        store = LangChainKnowledgeStore(vectorstore=lc_store)
    """
    
    def __init__(
        self,
        vectorstore: Any = None,
        vectorstore_cls: Optional[str] = None,
        vectorstore_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize LangChain adapter.
        
        Args:
            vectorstore: Pre-initialized LangChain VectorStore instance
            vectorstore_cls: Class name to import (e.g., "langchain_chroma.Chroma")
            vectorstore_kwargs: Kwargs for vectorstore initialization
        """
        self._vectorstore = vectorstore
        self._vectorstore_cls = vectorstore_cls
        self._vectorstore_kwargs = vectorstore_kwargs or {}
        self._initialized = vectorstore is not None
    
    def _init_client(self):
        """Initialize vectorstore lazily."""
        if self._initialized:
            return
        
        if not self._vectorstore_cls:
            raise ValueError(
                "Either vectorstore or vectorstore_cls must be provided"
            )
        
        # Dynamic import of vectorstore class
        parts = self._vectorstore_cls.rsplit(".", 1)
        if len(parts) == 2:
            module_name, class_name = parts
            import importlib
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            self._vectorstore = cls(**self._vectorstore_kwargs)
        else:
            raise ValueError(f"Invalid vectorstore_cls: {self._vectorstore_cls}")
        
        self._initialized = True
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create collection (handled by underlying vectorstore)."""
        self._init_client()
        logger.info(f"Collection creation handled by LangChain vectorstore")
    
    def delete_collection(self, name: str) -> bool:
        """Delete collection."""
        self._init_client()
        try:
            if hasattr(self._vectorstore, 'delete_collection'):
                self._vectorstore.delete_collection()
                return True
            logger.warning("Underlying vectorstore doesn't support delete_collection")
            return False
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if collection exists."""
        self._init_client()
        return self._vectorstore is not None
    
    def list_collections(self) -> List[str]:
        """List collections."""
        self._init_client()
        if hasattr(self._vectorstore, 'list_collections'):
            return self._vectorstore.list_collections()
        return ["default"]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        self._init_client()
        
        try:
            from langchain_core.documents import Document as LCDocument
        except ImportError:
            raise ImportError(
                "langchain-core is required. Install with: pip install langchain-core"
            )
        
        lc_docs = []
        ids = []
        for doc in documents:
            lc_doc = LCDocument(
                page_content=doc.content,
                metadata={
                    **(doc.metadata or {}),
                    "id": doc.id,
                    "content_hash": doc.content_hash,
                    "created_at": doc.created_at,
                }
            )
            lc_docs.append(lc_doc)
            ids.append(doc.id)
        
        if hasattr(self._vectorstore, 'add_documents'):
            self._vectorstore.add_documents(lc_docs, ids=ids)
        else:
            logger.warning("Vectorstore doesn't support add_documents")
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents."""
        # Most LangChain vectorstores handle upsert via add_documents
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
            if hasattr(self._vectorstore, 'similarity_search_by_vector'):
                results = self._vectorstore.similarity_search_by_vector(
                    query_embedding,
                    k=limit,
                    filter=filters
                )
            else:
                logger.warning("Vectorstore doesn't support vector search")
                return []
            
            documents = []
            for lc_doc in results:
                metadata = lc_doc.metadata or {}
                documents.append(KnowledgeDocument(
                    id=metadata.get("id", ""),
                    content=lc_doc.page_content,
                    metadata=metadata,
                    content_hash=metadata.get("content_hash"),
                    created_at=metadata.get("created_at", 0)
                ))
            
            return documents
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def similarity_search(
        self,
        query_text: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[KnowledgeDocument]:
        """
        Text-based similarity search (native LangChain method).
        
        Args:
            query_text: Query string
            limit: Maximum results
            filters: Metadata filters
        
        Returns:
            List of matching documents
        """
        self._init_client()
        
        try:
            results = self._vectorstore.similarity_search(
                query_text,
                k=limit,
                filter=filters
            )
            
            documents = []
            for lc_doc in results:
                metadata = lc_doc.metadata or {}
                documents.append(KnowledgeDocument(
                    id=metadata.get("id", ""),
                    content=lc_doc.page_content,
                    metadata=metadata,
                    content_hash=metadata.get("content_hash"),
                    created_at=metadata.get("created_at", 0)
                ))
            
            return documents
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        self._init_client()
        
        if hasattr(self._vectorstore, 'get'):
            try:
                results = self._vectorstore.get(ids)
                documents = []
                for lc_doc in results:
                    metadata = lc_doc.metadata or {}
                    documents.append(KnowledgeDocument(
                        id=metadata.get("id", ""),
                        content=lc_doc.page_content,
                        metadata=metadata
                    ))
                return documents
            except Exception as e:
                logger.warning(f"Get by ID failed: {e}")
        
        return []
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        self._init_client()
        
        if ids and hasattr(self._vectorstore, 'delete'):
            try:
                self._vectorstore.delete(ids)
                return len(ids)
            except Exception as e:
                logger.error(f"Delete failed: {e}")
        
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        self._init_client()
        
        if hasattr(self._vectorstore, '__len__'):
            return len(self._vectorstore)
        
        logger.warning("Vectorstore doesn't support counting")
        return -1
    
    def close(self) -> None:
        """Close the client."""
        self._vectorstore = None
        self._initialized = False
