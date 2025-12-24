"""
ClickHouse Vector implementation of KnowledgeStore.

Requires: clickhouse-connect
Install: pip install clickhouse-connect
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class ClickHouseKnowledgeStore(KnowledgeStore):
    """
    ClickHouse-based knowledge store using vector search.
    
    Example:
        store = ClickHouseKnowledgeStore(
            host="localhost",
            port=8123
        )
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "",
        database: str = "praisonai",
        secure: bool = False,
    ):
        try:
            import clickhouse_connect
        except ImportError:
            raise ImportError(
                "clickhouse-connect is required for ClickHouse support. "
                "Install with: pip install clickhouse-connect"
            )
        
        self._client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            secure=secure,
        )
        self.database = database
        
        # Create database if not exists
        self._client.command(f"CREATE DATABASE IF NOT EXISTS {database}")
        logger.info(f"Connected to ClickHouse database: {database}")
    
    def _table_name(self, collection: str) -> str:
        return f"{self.database}.praison_vec_{collection}"
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new table with vector column."""
        table = self._table_name(name)
        
        self._client.command(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id String,
                content String,
                content_hash String,
                created_at Float64,
                embedding Array(Float32)
            ) ENGINE = MergeTree()
            ORDER BY id
        """)
        logger.info(f"Created ClickHouse table: {table}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a table."""
        table = self._table_name(name)
        try:
            self._client.command(f"DROP TABLE IF EXISTS {table}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete table {table}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if a table exists."""
        table = self._table_name(name)
        result = self._client.query(f"EXISTS TABLE {table}")
        return result.result_rows[0][0] == 1
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        result = self._client.query(f"""
            SELECT name FROM system.tables 
            WHERE database = '{self.database}' AND name LIKE 'praison_vec_%'
        """)
        return [row[0].replace("praison_vec_", "") for row in result.result_rows]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        table = self._table_name(collection)
        
        data = []
        ids = []
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            data.append([
                doc.id,
                doc.content,
                doc.content_hash or "",
                doc.created_at,
                doc.embedding,
            ])
            ids.append(doc.id)
        
        self._client.insert(
            table,
            data,
            column_names=["id", "content", "content_hash", "created_at", "embedding"]
        )
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents."""
        # ClickHouse doesn't have native upsert for MergeTree
        # Delete then insert
        ids = [doc.id for doc in documents]
        self.delete(collection, ids)
        return self.insert(collection, documents)
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents using cosine distance."""
        table = self._table_name(collection)
        
        # Convert embedding to string for query
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        query = f"""
            SELECT 
                id, content, content_hash, created_at,
                1 - cosineDistance(embedding, {embedding_str}) as score
            FROM {table}
        """
        
        if score_threshold:
            query += f" WHERE 1 - cosineDistance(embedding, {embedding_str}) >= {score_threshold}"
        
        query += f" ORDER BY score DESC LIMIT {limit}"
        
        result = self._client.query(query)
        
        documents = []
        for row in result.result_rows:
            doc = KnowledgeDocument(
                id=row[0],
                content=row[1],
                embedding=None,
                metadata={},
                content_hash=row[2],
                created_at=row[3],
            )
            documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        table = self._table_name(collection)
        
        id_list = ", ".join([f"'{i}'" for i in ids])
        result = self._client.query(f"""
            SELECT id, content, content_hash, created_at, embedding
            FROM {table} WHERE id IN ({id_list})
        """)
        
        documents = []
        for row in result.result_rows:
            doc = KnowledgeDocument(
                id=row[0],
                content=row[1],
                embedding=list(row[4]) if row[4] else None,
                metadata={},
                content_hash=row[2],
                created_at=row[3],
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
        table = self._table_name(collection)
        
        if ids:
            id_list = ", ".join([f"'{i}'" for i in ids])
            self._client.command(f"ALTER TABLE {table} DELETE WHERE id IN ({id_list})")
            return len(ids)
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        table = self._table_name(collection)
        result = self._client.query(f"SELECT COUNT(*) FROM {table}")
        return result.result_rows[0][0]
    
    def close(self) -> None:
        """Close the store."""
        if self._client:
            self._client.close()
