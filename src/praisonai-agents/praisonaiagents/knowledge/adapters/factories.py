"""
Knowledge Adapter Factory Functions

Provides factory functions for heavy knowledge adapters that replace hardcoded imports
in knowledge/knowledge.py. These enable lazy loading of heavy dependencies while maintaining
the protocol-driven architecture.

Each factory function:
1. Lazy imports the required dependencies 
2. Creates and returns an adapter instance that implements KnowledgeStoreProtocol
3. Raises clear ImportError with installation instructions if dependencies missing

This approach follows the protocol-driven core principle by moving heavy implementations
out of the core Knowledge class while preserving backward compatibility.
"""

import os
from typing import Any, Dict, List, Optional
from ..protocols import KnowledgeStoreProtocol


def create_mem0_knowledge_adapter(**kwargs) -> KnowledgeStoreProtocol:
    """
    Factory function to create Mem0 knowledge adapter.
    
    Lazy imports mem0 and creates an adapter that wraps mem0.Memory
    to implement KnowledgeStoreProtocol.
    
    Args:
        **kwargs: Configuration passed to mem0 Memory
        
    Returns:
        KnowledgeStoreProtocol adapter instance
        
    Raises:
        ImportError: If mem0 is not installed
    """
    try:
        # Lazy import - only when actually needed
        from .mem0_adapter import Mem0Adapter
        return Mem0Adapter(**kwargs)
    except ImportError:
        raise ImportError(
            "mem0 is required for mem0 knowledge adapter. Install with: pip install mem0ai"
        )


def create_mongodb_knowledge_adapter(**kwargs) -> KnowledgeStoreProtocol:
    """
    Factory function to create MongoDB knowledge adapter.
    
    Lazy imports pymongo and creates an adapter that implements KnowledgeStoreProtocol
    using MongoDB as the document store backend.
    
    Args:
        **kwargs: Configuration passed to MongoDB adapter
        
    Returns:
        KnowledgeStoreProtocol adapter instance
        
    Raises:
        ImportError: If pymongo is not installed
    """
    try:
        # Lazy import - only when actually needed
        from .mongodb_adapter import MongoDBKnowledgeAdapter
        return MongoDBKnowledgeAdapter(**kwargs)
    except ImportError:
        raise ImportError(
            "pymongo is required for mongodb knowledge adapter. Install with: pip install pymongo"
        )


def create_chroma_knowledge_adapter(**kwargs) -> KnowledgeStoreProtocol:
    """
    Factory function to create ChromaDB knowledge adapter.
    
    Lazy imports chromadb and markitdown dependencies then creates an adapter
    that implements KnowledgeStoreProtocol using ChromaDB as the vector store backend.
    
    Args:
        **kwargs: Configuration passed to ChromaDB adapter
        
    Returns:
        KnowledgeStoreProtocol adapter instance
        
    Raises:
        ImportError: If chromadb or markitdown are not installed
    """
    try:
        import chromadb
        from markitdown import MarkItDown
    except ImportError:
        raise ImportError(
            "chromadb and markitdown are required for chroma knowledge adapter. "
            "Install with: pip install chromadb markitdown"
        )
    
    return ChromaKnowledgeAdapter(chromadb=chromadb, markitdown=MarkItDown(), **kwargs)


class ChromaKnowledgeAdapter:
    """
    Knowledge adapter that uses ChromaDB to implement KnowledgeStoreProtocol.
    
    This adapter replaces the hardcoded chromadb import in knowledge.py (lines 77-78).
    """
    
    def __init__(self, chromadb, markitdown, **kwargs):
        """Initialize ChromaDB knowledge adapter."""
        self.chromadb = chromadb
        self.markitdown = markitdown
        
        # Configuration
        config = kwargs.get("config", {})
        vector_config = config.get("vector_store", {}).get("config", {})
        
        collection_name = vector_config.get("collection_name", "praisonai_knowledge")
        persist_dir = vector_config.get("path", "knowledge_db")
        os.makedirs(persist_dir, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False)
        )
        
        # Initialize collection
        try:
            self.collection = self.client.get_collection(name=collection_name)
        except Exception:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
    
    def search(self, query: str, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
               run_id: Optional[str] = None, limit: int = 10, filters: Optional[Dict[str, Any]] = None,
               **kwargs: Any):
        """Search for relevant content in ChromaDB."""
        from ..models import SearchResult, SearchResultItem
        
        # Get embedding for query
        try:
            from praisonaiagents.embedding import embedding
            result = embedding(query, model="text-embedding-3-small")
            query_embedding = result.embeddings[0] if result.embeddings else None
        except Exception:
            query_embedding = None
        
        if query_embedding is None:
            return SearchResult(results=[])
        
        # Search ChromaDB
        try:
            response = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                include=["documents", "metadatas", "distances"]
            )
            
            items = []
            if response["ids"]:
                for i in range(len(response["ids"][0])):
                    metadata = response["metadatas"][0][i] if "metadatas" in response else {}
                    # Ensure metadata is dict, never None (required by protocol)
                    metadata = metadata or {}
                    
                    score = 1.0 - (response["distances"][0][i] if "distances" in response else 0.0)
                    
                    items.append(SearchResultItem(
                        id=response["ids"][0][i],
                        text=response["documents"][0][i],
                        metadata=metadata,
                        score=score
                    ))
            
            return SearchResult(results=items)
            
        except Exception as e:
            return SearchResult(results=[])
    
    def add(self, content: Any, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
            run_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None,
            **kwargs: Any):
        """Add content to ChromaDB."""
        from ..models import AddResult
        
        # Convert content to string
        content_str = str(content)
        
        # Get embedding
        try:
            from praisonaiagents.embedding import embedding
            result = embedding(content_str, model="text-embedding-3-small")
            content_embedding = result.embeddings[0] if result.embeddings else None
        except Exception:
            content_embedding = None
        
        if content_embedding is None:
            return AddResult(success=False, message="Failed to generate embedding")
        
        # Generate ID and store
        import time
        doc_id = str(time.time_ns())
        
        # Prepare metadata
        doc_metadata = metadata or {}
        if user_id:
            doc_metadata["user_id"] = user_id
        if agent_id:
            doc_metadata["agent_id"] = agent_id
        if run_id:
            doc_metadata["run_id"] = run_id
        
        try:
            self.collection.add(
                documents=[content_str],
                metadatas=[doc_metadata],
                ids=[doc_id],
                embeddings=[content_embedding]
            )
            
            return AddResult(success=True, id=doc_id)
            
        except Exception as e:
            return AddResult(success=False, message=str(e))
    
    def get(self, item_id: str, **kwargs: Any):
        """Get a specific item by ID from ChromaDB."""
        from ..models import SearchResultItem
        
        try:
            response = self.collection.get(
                ids=[item_id],
                include=["documents", "metadatas"]
            )
            
            if response["ids"] and len(response["ids"]) > 0:
                metadata = response["metadatas"][0] if "metadatas" in response else {}
                # Ensure metadata is dict, never None
                metadata = metadata or {}
                
                return SearchResultItem(
                    id=response["ids"][0],
                    text=response["documents"][0],
                    metadata=metadata,
                    score=1.0
                )
            
            return None
            
        except Exception:
            return None
    
    def get_all(self, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
                run_id: Optional[str] = None, limit: int = 100, **kwargs: Any):
        """Get all items from ChromaDB."""
        from ..models import SearchResult, SearchResultItem
        
        try:
            # ChromaDB doesn't support get_all with filters easily, so we'll use peek
            response = self.collection.peek(limit=limit)
            
            items = []
            if response["ids"]:
                for i in range(len(response["ids"])):
                    metadata = response["metadatas"][i] if "metadatas" in response else {}
                    # Ensure metadata is dict, never None
                    metadata = metadata or {}
                    
                    # Apply filtering if specified
                    if user_id and metadata.get("user_id") != user_id:
                        continue
                    if agent_id and metadata.get("agent_id") != agent_id:
                        continue
                    if run_id and metadata.get("run_id") != run_id:
                        continue
                    
                    items.append(SearchResultItem(
                        id=response["ids"][i],
                        text=response["documents"][i],
                        metadata=metadata,
                        score=1.0
                    ))
            
            return SearchResult(results=items)
            
        except Exception:
            return SearchResult(results=[])
    
    def update(self, item_id: str, content: Any, **kwargs: Any):
        """Update an existing item in ChromaDB."""
        from ..models import AddResult
        
        # ChromaDB doesn't support direct updates, so we delete and re-add
        try:
            self.collection.delete(ids=[item_id])
            return self.add(content, **kwargs)
        except Exception as e:
            return AddResult(success=False, message=str(e))
    
    def delete(self, item_id: str, **kwargs: Any) -> bool:
        """Delete an item by ID from ChromaDB."""
        try:
            self.collection.delete(ids=[item_id])
            return True
        except Exception:
            return False
    
    def delete_all(self, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
                   run_id: Optional[str] = None, **kwargs: Any) -> bool:
        """Delete all items matching scope from ChromaDB."""
        try:
            if not any([user_id, agent_id, run_id]):
                # Delete entire collection
                self.client.delete_collection(self.collection.name)
                return True
            else:
                # Get filtered items and delete them
                all_items = self.get_all(user_id=user_id, agent_id=agent_id, run_id=run_id)
                item_ids = [item.id for item in all_items.results]
                if item_ids:
                    self.collection.delete(ids=item_ids)
                return True
        except Exception:
            return False


def create_sqlite_knowledge_adapter(**kwargs) -> KnowledgeStoreProtocol:
    """
    Factory function to create SQLite knowledge adapter.
    
    Creates a lightweight SQLite-based knowledge adapter for core usage.
    
    Args:
        **kwargs: Configuration passed to SQLite adapter
        
    Returns:
        KnowledgeStoreProtocol adapter instance
    """
    return SQLiteKnowledgeAdapter(**kwargs)


class SQLiteKnowledgeAdapter:
    """
    Lightweight SQLite-based knowledge adapter implementing KnowledgeStoreProtocol.
    
    This provides a core adapter that doesn't require heavy dependencies.
    """
    
    def __init__(self, **kwargs):
        """Initialize SQLite knowledge adapter."""
        import sqlite3
        import json
        import threading
        
        self.db_path = kwargs.get("db_path", "knowledge.db")
        self._local = threading.local()
        self._lock = threading.Lock()
        
        # Initialize database
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata TEXT,
                user_id TEXT,
                agent_id TEXT,
                run_id TEXT,
                created_at REAL
            )
        """)
        conn.commit()
    
    def _get_conn(self):
        """Get thread-local SQLite connection."""
        if not hasattr(self._local, 'conn'):
            import sqlite3
            self._local.conn = sqlite3.connect(self.db_path)
        return self._local.conn
    
    def search(self, query: str, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
               run_id: Optional[str] = None, limit: int = 10, filters: Optional[Dict[str, Any]] = None,
               **kwargs: Any):
        """Search for relevant content in SQLite."""
        from ..models import SearchResult, SearchResultItem
        import json
        
        conn = self._get_conn()
        
        # Build query with filters
        sql = "SELECT id, content, metadata FROM knowledge WHERE content LIKE ?"
        params = [f"%{query}%"]
        
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)
        
        sql += " LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        
        items = []
        for row in rows:
            metadata = json.loads(row[2] or "{}")
            items.append(SearchResultItem(
                id=row[0],
                text=row[1],
                metadata=metadata,
                score=1.0
            ))
        
        return SearchResult(results=items)
    
    def add(self, content: Any, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
            run_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None,
            **kwargs: Any):
        """Add content to SQLite."""
        from ..models import AddResult
        import json
        import time
        
        content_str = str(content)
        doc_id = str(time.time_ns())
        metadata_json = json.dumps(metadata or {})
        
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO knowledge (id, content, metadata, user_id, agent_id, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, content_str, metadata_json, user_id, agent_id, run_id, time.time())
            )
            conn.commit()
            
            return AddResult(success=True, id=doc_id)
            
        except Exception as e:
            return AddResult(success=False, message=str(e))
    
    def get(self, item_id: str, **kwargs: Any):
        """Get a specific item by ID from SQLite."""
        from ..models import SearchResultItem
        import json
        
        conn = self._get_conn()
        cursor = conn.execute("SELECT id, content, metadata FROM knowledge WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        
        if row:
            metadata = json.loads(row[2] or "{}")
            return SearchResultItem(
                id=row[0],
                text=row[1],
                metadata=metadata,
                score=1.0
            )
        
        return None
    
    def get_all(self, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
                run_id: Optional[str] = None, limit: int = 100, **kwargs: Any):
        """Get all items from SQLite."""
        from ..models import SearchResult, SearchResultItem
        import json
        
        conn = self._get_conn()
        
        # Build query with filters
        sql = "SELECT id, content, metadata FROM knowledge WHERE 1=1"
        params = []
        
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)
        
        sql += " LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        
        items = []
        for row in rows:
            metadata = json.loads(row[2] or "{}")
            items.append(SearchResultItem(
                id=row[0],
                text=row[1],
                metadata=metadata,
                score=1.0
            ))
        
        return SearchResult(results=items)
    
    def update(self, item_id: str, content: Any, **kwargs: Any):
        """Update an existing item in SQLite."""
        from ..models import AddResult
        import json
        
        content_str = str(content)
        metadata = kwargs.get("metadata", {})
        metadata_json = json.dumps(metadata)
        
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE knowledge SET content = ?, metadata = ? WHERE id = ?",
                (content_str, metadata_json, item_id)
            )
            conn.commit()
            
            return AddResult(success=True, id=item_id)
            
        except Exception as e:
            return AddResult(success=False, message=str(e))
    
    def delete(self, item_id: str, **kwargs: Any) -> bool:
        """Delete an item by ID from SQLite."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM knowledge WHERE id = ?", (item_id,))
            conn.commit()
            return True
        except Exception:
            return False
    
    def delete_all(self, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
                   run_id: Optional[str] = None, **kwargs: Any) -> bool:
        """Delete all items matching scope from SQLite."""
        try:
            conn = self._get_conn()
            
            if not any([user_id, agent_id, run_id]):
                # Delete all
                conn.execute("DELETE FROM knowledge")
            else:
                # Delete with filters
                sql = "DELETE FROM knowledge WHERE 1=1"
                params = []
                
                if user_id:
                    sql += " AND user_id = ?"
                    params.append(user_id)
                if agent_id:
                    sql += " AND agent_id = ?"
                    params.append(agent_id)
                if run_id:
                    sql += " AND run_id = ?"
                    params.append(run_id)
                
                conn.execute(sql, params)
            
            conn.commit()
            return True
            
        except Exception:
            return False