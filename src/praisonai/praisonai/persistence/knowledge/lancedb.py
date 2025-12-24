"""
LanceDB implementation of KnowledgeStore.

Requires: lancedb
Install: pip install lancedb
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class LanceDBKnowledgeStore(KnowledgeStore):
    """
    LanceDB-based knowledge store for vector search.
    
    Embedded serverless vector database.
    
    Example:
        store = LanceDBKnowledgeStore(
            path="./lancedb"
        )
    """
    
    def __init__(
        self,
        path: str = "./lancedb",
        uri: Optional[str] = None,
    ):
        try:
            import lancedb
        except ImportError:
            raise ImportError(
                "lancedb is required for LanceDB support. "
                "Install with: pip install lancedb"
            )
        
        self._lancedb = lancedb
        self._db = lancedb.connect(uri or path)
        self._tables: Dict[str, Any] = {}
        logger.info(f"Connected to LanceDB at {uri or path}")
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new table."""
        import pyarrow as pa
        
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("content", pa.string()),
            pa.field("content_hash", pa.string()),
            pa.field("created_at", pa.float64()),
            pa.field("vector", pa.list_(pa.float32(), dimension)),
        ])
        
        self._db.create_table(name, schema=schema)
        logger.info(f"Created LanceDB table: {name}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a table."""
        try:
            self._db.drop_table(name)
            if name in self._tables:
                del self._tables[name]
            return True
        except Exception as e:
            logger.warning(f"Failed to delete table {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if a table exists."""
        return name in self._db.table_names()
    
    def list_collections(self) -> List[str]:
        """List all tables."""
        return self._db.table_names()
    
    def _get_table(self, name: str):
        """Get or cache a table."""
        if name not in self._tables:
            self._tables[name] = self._db.open_table(name)
        return self._tables[name]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        table = self._get_table(collection)
        
        data = []
        ids = []
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            
            data.append({
                "id": doc.id,
                "content": doc.content,
                "content_hash": doc.content_hash or "",
                "created_at": doc.created_at,
                "vector": doc.embedding,
            })
            ids.append(doc.id)
        
        table.add(data)
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents."""
        # LanceDB doesn't have native upsert, delete then insert
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
        """Search for similar documents."""
        table = self._get_table(collection)
        
        query = table.search(query_embedding).limit(limit)
        
        if filters:
            where_clauses = [f"{k} = '{v}'" for k, v in filters.items()]
            query = query.where(" AND ".join(where_clauses))
        
        results = query.to_pandas()
        
        documents = []
        for _, row in results.iterrows():
            if score_threshold and row.get("_distance", 1) > (1 - score_threshold):
                continue
            
            doc = KnowledgeDocument(
                id=row["id"],
                content=row["content"],
                embedding=None,
                metadata={},
                content_hash=row.get("content_hash"),
                created_at=row.get("created_at", 0),
            )
            documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        table = self._get_table(collection)
        
        id_list = ", ".join([f"'{i}'" for i in ids])
        results = table.search().where(f"id IN ({id_list})").to_pandas()
        
        documents = []
        for _, row in results.iterrows():
            doc = KnowledgeDocument(
                id=row["id"],
                content=row["content"],
                embedding=list(row["vector"]) if "vector" in row else None,
                metadata={},
                content_hash=row.get("content_hash"),
                created_at=row.get("created_at", 0),
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
        table = self._get_table(collection)
        
        if ids:
            id_list = ", ".join([f"'{i}'" for i in ids])
            table.delete(f"id IN ({id_list})")
            return len(ids)
        elif filters:
            where_clauses = [f"{k} = '{v}'" for k, v in filters.items()]
            table.delete(" AND ".join(where_clauses))
            return -1
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        table = self._get_table(collection)
        return table.count_rows()
    
    def close(self) -> None:
        """Close the store."""
        self._tables.clear()
