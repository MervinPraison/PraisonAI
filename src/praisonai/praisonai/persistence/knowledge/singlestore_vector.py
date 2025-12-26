"""
SingleStore Vector implementation of KnowledgeStore.

Requires: singlestoredb
Install: pip install singlestoredb
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class SingleStoreVectorKnowledgeStore(KnowledgeStore):
    """
    SingleStore vector store for knowledge/RAG.
    
    Uses SingleStore's native vector capabilities.
    
    Example:
        store = SingleStoreVectorKnowledgeStore(
            url="singlestoredb://user:pass@host:3306/db"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 3306,
        database: str = "praisonai",
        user: str = "root",
        password: str = "",
        table_prefix: str = "praisonai_",
        embedding_dim: int = 1536,
    ):
        """
        Initialize SingleStore Vector store.
        
        Args:
            url: SingleStore connection URL
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            table_prefix: Prefix for table names
            embedding_dim: Embedding dimension
        """
        self.url = url
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table_prefix = table_prefix
        self.embedding_dim = embedding_dim
        
        self._conn = None
        self._initialized = False
    
    def _init_client(self):
        """Initialize SingleStore client lazily."""
        if self._initialized:
            return
        
        try:
            import singlestoredb as s2
        except ImportError:
            raise ImportError(
                "singlestoredb is required for SingleStore Vector support. "
                "Install with: pip install singlestoredb"
            )
        
        if self.url:
            self._conn = s2.connect(self.url)
        else:
            self._conn = s2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
        
        self._initialized = True
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a vector table."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{name}"
        
        with self._conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id VARCHAR(255) PRIMARY KEY,
                    content TEXT,
                    embedding VECTOR({dimension}),
                    metadata JSON,
                    content_hash VARCHAR(64),
                    created_at DOUBLE
                )
            """)
    
    def delete_collection(self, name: str) -> bool:
        """Delete a vector table."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{name}"
        try:
            with self._conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if table exists."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{name}"
        with self._conn.cursor() as cur:
            cur.execute(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            """, (self.database, table_name))
            return cur.fetchone()[0] > 0
    
    def list_collections(self) -> List[str]:
        """List all vector tables."""
        self._init_client()
        
        with self._conn.cursor() as cur:
            cur.execute(f"""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = %s AND table_name LIKE %s
            """, (self.database, f"{self.table_prefix}%"))
            return [row[0][len(self.table_prefix):] for row in cur.fetchall()]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{collection}"
        ids = []
        
        with self._conn.cursor() as cur:
            for doc in documents:
                embedding_str = str(doc.embedding) if doc.embedding else None
                cur.execute(f"""
                    INSERT INTO {table_name} (id, content, embedding, metadata, content_hash, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (doc.id, doc.content, embedding_str,
                      str(doc.metadata) if doc.metadata else None,
                      doc.content_hash, doc.created_at))
                ids.append(doc.id)
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{collection}"
        ids = []
        
        with self._conn.cursor() as cur:
            for doc in documents:
                embedding_str = str(doc.embedding) if doc.embedding else None
                cur.execute(f"""
                    REPLACE INTO {table_name} (id, content, embedding, metadata, content_hash, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (doc.id, doc.content, embedding_str,
                      str(doc.metadata) if doc.metadata else None,
                      doc.content_hash, doc.created_at))
                ids.append(doc.id)
        
        return ids
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents using vector search."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{collection}"
        embedding_str = str(query_embedding)
        
        with self._conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, content, metadata, content_hash, created_at,
                       DOT_PRODUCT(embedding, %s) as score
                FROM {table_name}
                ORDER BY score DESC
                LIMIT %s
            """, (embedding_str, limit))
            
            documents = []
            for row in cur.fetchall():
                score = row[5] if len(row) > 5 else 0
                if score_threshold and score < score_threshold:
                    continue
                
                documents.append(KnowledgeDocument(
                    id=row[0],
                    content=row[1],
                    metadata=eval(row[2]) if row[2] else None,
                    content_hash=row[3],
                    created_at=row[4]
                ))
            
            return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{collection}"
        placeholders = ','.join(['%s'] * len(ids))
        
        with self._conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, content, metadata, content_hash, created_at
                FROM {table_name}
                WHERE id IN ({placeholders})
            """, ids)
            
            return [
                KnowledgeDocument(
                    id=row[0],
                    content=row[1],
                    metadata=eval(row[2]) if row[2] else None,
                    content_hash=row[3],
                    created_at=row[4]
                )
                for row in cur.fetchall()
            ]
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{collection}"
        
        with self._conn.cursor() as cur:
            if ids:
                placeholders = ','.join(['%s'] * len(ids))
                cur.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", ids)
            else:
                cur.execute(f"DELETE FROM {table_name}")
            return cur.rowcount
    
    def count(self, collection: str) -> int:
        """Count documents."""
        self._init_client()
        
        table_name = f"{self.table_prefix}{collection}"
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            return cur.fetchone()[0]
    
    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False
