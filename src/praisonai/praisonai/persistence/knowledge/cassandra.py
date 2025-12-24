"""
Cassandra Vector implementation of KnowledgeStore.

Requires: cassandra-driver
Install: pip install cassandra-driver
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class CassandraKnowledgeStore(KnowledgeStore):
    """
    Cassandra-based knowledge store using vector search (SAI).
    
    Requires Cassandra 5.0+ or DataStax Astra with vector search.
    
    Example:
        store = CassandraKnowledgeStore(
            hosts=["localhost"],
            keyspace="praisonai"
        )
    """
    
    def __init__(
        self,
        hosts: Optional[List[str]] = None,
        keyspace: str = "praisonai",
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 9042,
        secure_connect_bundle: Optional[str] = None,
    ):
        try:
            from cassandra.cluster import Cluster
            from cassandra.auth import PlainTextAuthProvider
        except ImportError:
            raise ImportError(
                "cassandra-driver is required for Cassandra support. "
                "Install with: pip install cassandra-driver"
            )
        
        self._Cluster = Cluster
        self.keyspace = keyspace
        
        auth = None
        if username and password:
            auth = PlainTextAuthProvider(username=username, password=password)
        
        if secure_connect_bundle:
            # Astra DB connection
            from cassandra.cluster import Cluster
            cloud_config = {"secure_connect_bundle": secure_connect_bundle}
            self._cluster = Cluster(cloud=cloud_config, auth_provider=auth)
        else:
            hosts = hosts or ["localhost"]
            self._cluster = Cluster(hosts, port=port, auth_provider=auth)
        
        self._session = self._cluster.connect()
        
        # Create keyspace if not exists
        self._session.execute(f"""
            CREATE KEYSPACE IF NOT EXISTS {keyspace}
            WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}
        """)
        self._session.set_keyspace(keyspace)
        logger.info(f"Connected to Cassandra keyspace: {keyspace}")
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new table with vector column."""
        similarity_map = {"cosine": "COSINE", "euclidean": "EUCLIDEAN", "dot": "DOT_PRODUCT"}
        
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {name} (
                id text PRIMARY KEY,
                content text,
                content_hash text,
                created_at double,
                embedding vector<float, {dimension}>
            )
        """)
        
        # Create SAI index for vector search
        self._session.execute(f"""
            CREATE CUSTOM INDEX IF NOT EXISTS {name}_embedding_idx ON {name} (embedding)
            USING 'StorageAttachedIndex'
            WITH OPTIONS = {{'similarity_function': '{similarity_map.get(distance, "COSINE")}'}}
        """)
        logger.info(f"Created Cassandra table: {name}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a table."""
        try:
            self._session.execute(f"DROP TABLE IF EXISTS {name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete table {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if a table exists."""
        result = self._session.execute("""
            SELECT table_name FROM system_schema.tables 
            WHERE keyspace_name = %s AND table_name = %s
        """, (self.keyspace, name))
        return len(list(result)) > 0
    
    def list_collections(self) -> List[str]:
        """List all tables."""
        result = self._session.execute("""
            SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s
        """, (self.keyspace,))
        return [row.table_name for row in result]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        ids = []
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            
            self._session.execute(f"""
                INSERT INTO {collection} (id, content, content_hash, created_at, embedding)
                VALUES (%s, %s, %s, %s, %s)
            """, (doc.id, doc.content, doc.content_hash or "", doc.created_at, doc.embedding))
            ids.append(doc.id)
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents."""
        return self.insert(collection, documents)  # Cassandra INSERT is upsert
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents using ANN."""
        result = self._session.execute(f"""
            SELECT id, content, content_hash, created_at, similarity_cosine(embedding, %s) as score
            FROM {collection}
            ORDER BY embedding ANN OF %s
            LIMIT %s
        """, (query_embedding, query_embedding, limit))
        
        documents = []
        for row in result:
            if score_threshold and row.score < score_threshold:
                continue
            
            doc = KnowledgeDocument(
                id=row.id,
                content=row.content,
                embedding=None,
                metadata={},
                content_hash=row.content_hash,
                created_at=row.created_at,
            )
            documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        documents = []
        for doc_id in ids:
            result = self._session.execute(f"""
                SELECT id, content, content_hash, created_at, embedding
                FROM {collection} WHERE id = %s
            """, (doc_id,))
            
            for row in result:
                doc = KnowledgeDocument(
                    id=row.id,
                    content=row.content,
                    embedding=list(row.embedding) if row.embedding else None,
                    metadata={},
                    content_hash=row.content_hash,
                    created_at=row.created_at,
                )
                documents.append(doc)
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        if ids:
            for doc_id in ids:
                self._session.execute(f"DELETE FROM {collection} WHERE id = %s", (doc_id,))
            return len(ids)
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        result = self._session.execute(f"SELECT COUNT(*) FROM {collection}")
        return result.one()[0]
    
    def close(self) -> None:
        """Close the store."""
        if self._cluster:
            self._cluster.shutdown()
