"""
PGVector implementation of KnowledgeStore.

Requires: pgvector, psycopg2-binary
Install: pip install pgvector psycopg2-binary
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class PGVectorKnowledgeStore(KnowledgeStore):
    """
    PGVector-based knowledge store for vector search.
    
    Uses PostgreSQL with pgvector extension.
    
    Example:
        store = PGVectorKnowledgeStore(
            url="postgresql://localhost:5432/praisonai"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: str = "",
        schema: str = "public",
        auto_create_extension: bool = True,
    ):
        try:
            import psycopg2
            from psycopg2 import pool as pg_pool
            from psycopg2.extras import RealDictCursor
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PGVector support. "
                "Install with: pip install psycopg2-binary"
            )
        
        self._psycopg2 = psycopg2
        self._RealDictCursor = RealDictCursor
        self.schema = schema
        
        if url:
            self._pool = pg_pool.ThreadedConnectionPool(1, 5, url)
        else:
            self._pool = pg_pool.ThreadedConnectionPool(
                1, 5,
                host=host, port=port, database=database,
                user=user, password=password,
            )
        
        if auto_create_extension:
            self._create_extension()
    
    def _get_conn(self):
        return self._pool.getconn()
    
    def _put_conn(self, conn):
        self._pool.putconn(conn)
    
    def _create_extension(self):
        """Create pgvector extension if not exists."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
        finally:
            self._put_conn(conn)
    
    def _table_name(self, collection: str) -> str:
        return f"{self.schema}.praison_vec_{collection}"
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new collection table."""
        table = self._table_name(name)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id VARCHAR(255) PRIMARY KEY,
                        content TEXT,
                        content_hash VARCHAR(64),
                        created_at DOUBLE PRECISION,
                        metadata JSONB,
                        embedding vector({dimension})
                    )
                """)
                
                # Create index based on distance metric
                op_map = {"cosine": "vector_cosine_ops", "euclidean": "vector_l2_ops", "dot": "vector_ip_ops"}
                ops = op_map.get(distance, "vector_cosine_ops")
                
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{name}_embedding 
                    ON {table} USING hnsw (embedding {ops})
                """)
                conn.commit()
            logger.info(f"Created PGVector table: {table}")
        finally:
            self._put_conn(conn)
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection table."""
        table = self._table_name(name)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
                conn.commit()
            return True
        except Exception as e:
            logger.warning(f"Failed to delete table {table}: {e}")
            return False
        finally:
            self._put_conn(conn)
    
    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        table = self._table_name(name)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = %s AND table_name = %s
                    )
                """, (self.schema, f"praison_vec_{name}"))
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = %s AND table_name LIKE 'praison_vec_%%'
                """, (self.schema,))
                return [row[0].replace("praison_vec_", "") for row in cur.fetchall()]
        finally:
            self._put_conn(conn)
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        table = self._table_name(collection)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                for doc in documents:
                    if doc.embedding is None:
                        raise ValueError(f"Document {doc.id} has no embedding")
                    cur.execute(f"""
                        INSERT INTO {table} (id, content, content_hash, created_at, metadata, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        doc.id, doc.content, doc.content_hash, doc.created_at,
                        json.dumps(doc.metadata) if doc.metadata else None,
                        doc.embedding,
                    ))
                conn.commit()
            return [doc.id for doc in documents]
        finally:
            self._put_conn(conn)
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents."""
        table = self._table_name(collection)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                for doc in documents:
                    if doc.embedding is None:
                        raise ValueError(f"Document {doc.id} has no embedding")
                    cur.execute(f"""
                        INSERT INTO {table} (id, content, content_hash, created_at, metadata, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            content_hash = EXCLUDED.content_hash,
                            created_at = EXCLUDED.created_at,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding
                    """, (
                        doc.id, doc.content, doc.content_hash, doc.created_at,
                        json.dumps(doc.metadata) if doc.metadata else None,
                        doc.embedding,
                    ))
                conn.commit()
            return [doc.id for doc in documents]
        finally:
            self._put_conn(conn)
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents."""
        table = self._table_name(collection)
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._RealDictCursor) as cur:
                # Use cosine distance operator <=>
                query = f"""
                    SELECT id, content, content_hash, created_at, metadata,
                           1 - (embedding <=> %s::vector) as score
                    FROM {table}
                """
                params = [query_embedding]
                
                if score_threshold:
                    query += " WHERE 1 - (embedding <=> %s::vector) >= %s"
                    params.extend([query_embedding, score_threshold])
                
                query += " ORDER BY embedding <=> %s::vector LIMIT %s"
                params.extend([query_embedding, limit])
                
                cur.execute(query, params)
                
                documents = []
                for row in cur.fetchall():
                    doc = KnowledgeDocument(
                        id=row["id"],
                        content=row["content"],
                        embedding=None,
                        metadata=row["metadata"] or {},
                        content_hash=row["content_hash"],
                        created_at=row["created_at"],
                    )
                    documents.append(doc)
                return documents
        finally:
            self._put_conn(conn)
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        table = self._table_name(collection)
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._RealDictCursor) as cur:
                placeholders = ",".join(["%s"] * len(ids))
                cur.execute(f"""
                    SELECT id, content, content_hash, created_at, metadata, embedding::float[]
                    FROM {table} WHERE id IN ({placeholders})
                """, ids)
                
                documents = []
                for row in cur.fetchall():
                    doc = KnowledgeDocument(
                        id=row["id"],
                        content=row["content"],
                        embedding=row["embedding"],
                        metadata=row["metadata"] or {},
                        content_hash=row["content_hash"],
                        created_at=row["created_at"],
                    )
                    documents.append(doc)
                return documents
        finally:
            self._put_conn(conn)
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        table = self._table_name(collection)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if ids:
                    placeholders = ",".join(["%s"] * len(ids))
                    cur.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", ids)
                    deleted = cur.rowcount
                else:
                    deleted = 0
                conn.commit()
                return deleted
        finally:
            self._put_conn(conn)
    
    def count(self, collection: str) -> int:
        """Count documents."""
        table = self._table_name(collection)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)
    
    def close(self) -> None:
        """Close the store."""
        if self._pool:
            self._pool.closeall()
