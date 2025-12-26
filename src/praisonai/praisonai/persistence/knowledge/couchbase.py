"""
Couchbase implementation of KnowledgeStore.

Requires: couchbase
Install: pip install couchbase
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class CouchbaseKnowledgeStore(KnowledgeStore):
    """
    Couchbase vector store for knowledge/RAG.
    
    Uses Couchbase's vector search capabilities.
    
    Example:
        store = CouchbaseKnowledgeStore(
            connection_string="couchbase://localhost",
            username="admin",
            password="password",
            bucket_name="praisonai"
        )
    """
    
    def __init__(
        self,
        connection_string: str = "couchbase://localhost",
        username: str = "Administrator",
        password: str = "",
        bucket_name: str = "praisonai",
        scope_name: str = "_default",
        collection_name: str = "vectors",
        index_name: str = "vector_index",
        vector_field: str = "embedding",
        text_field: str = "content",
        embedding_dim: int = 1536,
    ):
        """
        Initialize Couchbase knowledge store.
        
        Args:
            connection_string: Couchbase connection string
            username: Couchbase username
            password: Couchbase password
            bucket_name: Bucket name
            scope_name: Scope name
            collection_name: Collection name
            index_name: Vector search index name
            vector_field: Field name for embeddings
            text_field: Field name for text content
            embedding_dim: Embedding dimension
        """
        self.connection_string = connection_string
        self.username = username
        self.password = password
        self.bucket_name = bucket_name
        self.scope_name = scope_name
        self.collection_name = collection_name
        self.index_name = index_name
        self.vector_field = vector_field
        self.text_field = text_field
        self.embedding_dim = embedding_dim
        
        self._cluster = None
        self._bucket = None
        self._collection = None
        self._initialized = False
    
    def _init_client(self):
        """Initialize Couchbase client lazily."""
        if self._initialized:
            return
        
        try:
            from couchbase.cluster import Cluster
            from couchbase.options import ClusterOptions
            from couchbase.auth import PasswordAuthenticator
            from datetime import timedelta
        except ImportError:
            raise ImportError(
                "couchbase is required for Couchbase support. "
                "Install with: pip install couchbase"
            )
        
        auth = PasswordAuthenticator(self.username, self.password)
        options = ClusterOptions(auth)
        
        self._cluster = Cluster(self.connection_string, options)
        self._cluster.wait_until_ready(timedelta(seconds=10))
        
        self._bucket = self._cluster.bucket(self.bucket_name)
        scope = self._bucket.scope(self.scope_name)
        self._collection = scope.collection(self.collection_name)
        
        self._initialized = True
    
    def insert(
        self,
        collection_name: str,
        documents: List[KnowledgeDocument],
        embeddings: Optional[List[List[float]]] = None,
    ) -> List[str]:
        """Insert documents into the store."""
        self._init_client()
        
        ids = []
        for i, doc in enumerate(documents):
            doc_id = doc.id or f"doc_{i}_{hash(doc.content)}"
            
            data = {
                self.text_field: doc.content,
                "metadata": doc.metadata or {},
            }
            
            if embeddings and i < len(embeddings):
                data[self.vector_field] = embeddings[i]
            
            self._collection.upsert(doc_id, data)
            ids.append(doc_id)
        
        return ids
    
    def upsert(
        self,
        collection_name: str,
        documents: List[KnowledgeDocument],
        embeddings: Optional[List[List[float]]] = None,
    ) -> List[str]:
        """Upsert documents (same as insert for Couchbase)."""
        return self.insert(collection_name, documents, embeddings)
    
    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeDocument]:
        """Search for similar documents using vector search."""
        self._init_client()
        
        try:
            from couchbase.vector_search import VectorQuery, VectorSearch
        except ImportError:
            logger.warning("Vector search not available in this Couchbase version")
            return []
        
        vector_query = VectorQuery(
            self.vector_field,
            query_embedding,
            num_candidates=limit * 2
        )
        
        search_req = VectorSearch.from_vector_query(vector_query)
        
        try:
            scope = self._bucket.scope(self.scope_name)
            result = scope.search(
                self.index_name,
                search_req,
                limit=limit
            )
            
            documents = []
            for row in result.rows():
                doc_id = row.id
                try:
                    doc_data = self._collection.get(doc_id).content_as[dict]
                    documents.append(KnowledgeDocument(
                        id=doc_id,
                        content=doc_data.get(self.text_field, ""),
                        metadata=doc_data.get("metadata", {}),
                        score=row.score if hasattr(row, 'score') else None
                    ))
                except Exception as e:
                    logger.warning(f"Failed to fetch document {doc_id}: {e}")
            
            return documents
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def delete(
        self,
        collection_name: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Delete documents by ID."""
        self._init_client()
        
        if not ids:
            return 0
        
        count = 0
        for doc_id in ids:
            try:
                self._collection.remove(doc_id)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to delete {doc_id}: {e}")
        
        return count
    
    def get(
        self,
        collection_name: str,
        ids: List[str],
    ) -> List[KnowledgeDocument]:
        """Get documents by ID."""
        self._init_client()
        
        documents = []
        for doc_id in ids:
            try:
                doc_data = self._collection.get(doc_id).content_as[dict]
                documents.append(KnowledgeDocument(
                    id=doc_id,
                    content=doc_data.get(self.text_field, ""),
                    metadata=doc_data.get("metadata", {})
                ))
            except Exception as e:
                logger.warning(f"Failed to get {doc_id}: {e}")
        
        return documents
    
    def count(self, collection_name: str) -> int:
        """Count documents in collection."""
        self._init_client()
        
        try:
            query = f"SELECT COUNT(*) as count FROM `{self.bucket_name}`.`{self.scope_name}`.`{self.collection_name}`"
            result = self._cluster.query(query)
            for row in result:
                return row.get("count", 0)
        except Exception as e:
            logger.error(f"Count query failed: {e}")
        
        return 0
    
    def create_collection(self, collection_name: str, **kwargs) -> bool:
        """Create collection (Couchbase collections are pre-created)."""
        self._init_client()
        return True
    
    def delete_collection(self, collection_name: str) -> bool:
        """Delete all documents in collection."""
        self._init_client()
        
        try:
            query = f"DELETE FROM `{self.bucket_name}`.`{self.scope_name}`.`{self.collection_name}`"
            self._cluster.query(query)
            return True
        except Exception as e:
            logger.error(f"Delete collection failed: {e}")
            return False
    
    def list_collections(self) -> List[str]:
        """List available collections."""
        self._init_client()
        
        try:
            collections = self._bucket.collections().get_all_scopes()
            result = []
            for scope in collections:
                for coll in scope.collections:
                    result.append(f"{scope.name}.{coll.name}")
            return result
        except Exception as e:
            logger.error(f"List collections failed: {e}")
            return []
    
    def close(self) -> None:
        """Close the connection."""
        if self._cluster:
            self._cluster.close()
            self._cluster = None
            self._bucket = None
            self._collection = None
            self._initialized = False
