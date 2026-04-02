"""
Storage and persistence functionality for Memory class.

This module contains methods related to data storage, database connections, 
and persistence operations. Split from the main memory.py file for better maintainability.
"""

import json
import os
import sqlite3
import threading
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

# Import shared utility functions
from .utils import _check_chromadb, _get_chromadb, _check_pymongo, _get_pymongo


class StorageMixin:
    """Mixin class containing storage and persistence methods for the Memory class."""
    
    def _get_stm_conn(self):
        """Get thread-local short-term memory SQLite connection."""
        if not hasattr(self._local, 'stm_conn') or self._local.stm_conn is None:
            stm_db_path = self.cfg.get("short_db", "short_term_memory.db")
            self._local.stm_conn = sqlite3.connect(stm_db_path, check_same_thread=False)
            self._local.stm_conn.row_factory = sqlite3.Row
            
            # Register for cleanup
            with self._connection_lock:
                self._all_connections.add(self._local.stm_conn)
                
        return self._local.stm_conn

    def _get_ltm_conn(self):
        """Get thread-local long-term memory SQLite connection.""" 
        if not hasattr(self._local, 'ltm_conn') or self._local.ltm_conn is None:
            ltm_db_path = self.cfg.get("long_db", "long_term_memory.db")
            self._local.ltm_conn = sqlite3.connect(ltm_db_path, check_same_thread=False)
            self._local.ltm_conn.row_factory = sqlite3.Row
            
            # Register for cleanup
            with self._connection_lock:
                self._all_connections.add(self._local.ltm_conn)
                
        return self._local.ltm_conn
    
    def _init_stm(self):
        """Initialize short-term memory table."""
        conn = self._get_stm_conn()
        with self._write_lock:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS short_term (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TEXT,
                    quality_score REAL DEFAULT 0.0
                )
            ''')
            conn.commit()

    def _init_ltm(self):
        """Initialize long-term memory table.""" 
        conn = self._get_ltm_conn()
        with self._write_lock:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS long_term (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TEXT,
                    quality_score REAL DEFAULT 0.0
                )
            ''')
            conn.commit()
    
    def _init_chroma(self):
        """Initialize ChromaDB for vector storage."""
        if not _check_chromadb():
            return
            
        chromadb = _get_chromadb()
        chroma_settings = chromadb["settings"]
        
        rag_db_path = self.cfg.get("rag_db_path", "rag_memory_db")
        
        # Create directory if it doesn't exist
        os.makedirs(rag_db_path, exist_ok=True)
        
        self.chroma_client = chromadb["module"].PersistentClient(
            path=rag_db_path,
            settings=chroma_settings(anonymized_telemetry=False)
        )
        
        # Initialize collections
        try:
            self.stm_collection = self.chroma_client.get_collection("short_term_memory")
        except Exception:
            self.stm_collection = self.chroma_client.create_collection("short_term_memory")
            
        try:
            self.ltm_collection = self.chroma_client.get_collection("long_term_memory")
        except Exception:
            self.ltm_collection = self.chroma_client.create_collection("long_term_memory")
    
    def _init_mongodb(self):
        """Initialize MongoDB for storage."""
        if not _check_pymongo():
            return
            
        pymongo = _get_pymongo()
        
        config = self.cfg.get("config", {})
        connection_string = config.get("connection_string", "mongodb://localhost:27017/")
        database_name = config.get("database", "praisonai")
        
        # Connection pool settings
        max_pool_size = config.get("max_pool_size", 50)
        min_pool_size = config.get("min_pool_size", 10)
        max_idle_time = config.get("max_idle_time", 30000)
        server_selection_timeout = config.get("server_selection_timeout", 5000)
        
        self.mongo_client = pymongo["MongoClient"](
            connection_string,
            maxPoolSize=max_pool_size,
            minPoolSize=min_pool_size,
            maxIdleTimeMS=max_idle_time,
            serverSelectionTimeoutMS=server_selection_timeout
        )
        
        self.mongo_db = self.mongo_client[database_name]
        self.stm_collection = self.mongo_db.short_term_memory
        self.ltm_collection = self.mongo_db.long_term_memory
        
        # Create indexes for better performance
        self._create_mongodb_indexes()
        
        # Initialize vector search if enabled
        use_vector_search = config.get("use_vector_search", False)
        if use_vector_search:
            self._create_vector_search_indexes()
    
    def _create_mongodb_indexes(self):
        """Create MongoDB indexes for better query performance."""
        try:
            # Text indexes for search
            self.stm_collection.create_index([("content", "text")])
            self.ltm_collection.create_index([("content", "text")])
            
            # Compound indexes for common queries
            self.stm_collection.create_index([("timestamp", -1), ("quality_score", -1)])
            self.ltm_collection.create_index([("timestamp", -1), ("quality_score", -1)])
            
            logging.info("MongoDB indexes created successfully")
        except Exception as e:
            logging.warning(f"Failed to create MongoDB indexes: {e}")
    
    def _create_vector_search_indexes(self):
        """Create MongoDB Atlas Vector Search indexes.""" 
        try:
            # Vector search indexes would be created via MongoDB Atlas UI
            # or using the Atlas Admin API
            logging.info("Vector search indexes configuration completed")
        except Exception as e:
            logging.warning(f"Failed to configure vector search indexes: {e}")
    
    def reset_short_term(self):
        """Clear all short-term memory."""
        if self.use_rag and hasattr(self, 'stm_collection'):
            try:
                # Clear ChromaDB collection
                self.stm_collection.delete()
                # Recreate collection
                self.stm_collection = self.chroma_client.create_collection("short_term_memory") 
                self._log_verbose("Short-term RAG memory reset")
            except Exception as e:
                logging.warning(f"Failed to reset ChromaDB STM: {e}")
        
        if self.use_mongodb and hasattr(self, 'stm_collection'):
            try:
                self.stm_collection.delete_many({})
                self._log_verbose("Short-term MongoDB memory reset")
            except Exception as e:
                logging.warning(f"Failed to reset MongoDB STM: {e}")
        
        # Clear SQLite STM
        try:
            conn = self._get_stm_conn()
            with self._write_lock:
                conn.execute("DELETE FROM short_term")
                conn.commit()
            self._log_verbose("Short-term SQLite memory reset")
        except Exception as e:
            logging.warning(f"Failed to reset SQLite STM: {e}")

    def reset_long_term(self):
        """Clear all long-term memory."""
        if self.use_rag and hasattr(self, 'ltm_collection'):
            try:
                # Clear ChromaDB collection
                self.ltm_collection.delete()
                # Recreate collection  
                self.ltm_collection = self.chroma_client.create_collection("long_term_memory")
                self._log_verbose("Long-term RAG memory reset")
            except Exception as e:
                logging.warning(f"Failed to reset ChromaDB LTM: {e}")
        
        if self.use_mongodb and hasattr(self, 'ltm_collection'):
            try:
                self.ltm_collection.delete_many({})
                self._log_verbose("Long-term MongoDB memory reset")
            except Exception as e:
                logging.warning(f"Failed to reset MongoDB LTM: {e}")
        
        # Clear SQLite LTM
        try:
            conn = self._get_ltm_conn()
            with self._write_lock:
                conn.execute("DELETE FROM long_term")
                conn.commit()
            self._log_verbose("Long-term SQLite memory reset")
        except Exception as e:
            logging.warning(f"Failed to reset SQLite LTM: {e}")

    # -----------------------------------------------------------------------
    # SQLite write helpers
    # -----------------------------------------------------------------------

    def _store_sqlite_stm(self, content: str, metadata: Dict, quality_score: float) -> str:
        """Insert a record into the short_term SQLite table and return its row id."""
        conn = self._get_stm_conn()
        with self._write_lock:
            cursor = conn.execute(
                "INSERT INTO short_term (content, metadata, timestamp, quality_score) VALUES (?, ?, ?, ?)",
                (content, json.dumps(metadata, default=str, ensure_ascii=False),
                 datetime.now().isoformat(), quality_score),
            )
            conn.commit()
        return str(cursor.lastrowid)

    def _store_sqlite_ltm(self, content: str, metadata: Dict, quality_score: float) -> str:
        """Insert a record into the long_term SQLite table and return its row id."""
        conn = self._get_ltm_conn()
        with self._write_lock:
            cursor = conn.execute(
                "INSERT INTO long_term (content, metadata, timestamp, quality_score) VALUES (?, ?, ?, ?)",
                (content, json.dumps(metadata, default=str, ensure_ascii=False),
                 datetime.now().isoformat(), quality_score),
            )
            conn.commit()
        return str(cursor.lastrowid)

    # -----------------------------------------------------------------------
    # ChromaDB write helpers
    # -----------------------------------------------------------------------

    def _store_vector_stm(self, content: str, metadata: Dict, quality_score: float) -> Optional[str]:
        """Store a record in the ChromaDB short-term collection."""
        if not hasattr(self, 'stm_collection') or self.stm_collection is None:
            return None
        doc_id = str(time.time_ns())
        try:
            self.stm_collection.add(
                documents=[content],
                metadatas=[{**{k: str(v) for k, v in metadata.items()},
                            "quality_score": str(quality_score)}],
                ids=[doc_id],
            )
        except Exception as e:
            logging.warning(f"ChromaDB STM store failed: {e}")
            return None
        return doc_id

    def _store_vector_ltm(self, content: str, metadata: Dict, quality_score: float) -> Optional[str]:
        """Store a record in the ChromaDB long-term collection."""
        if not hasattr(self, 'ltm_collection') or self.ltm_collection is None:
            return None
        doc_id = str(time.time_ns())
        try:
            self.ltm_collection.add(
                documents=[content],
                metadatas=[{**{k: str(v) for k, v in metadata.items()},
                            "quality_score": str(quality_score)}],
                ids=[doc_id],
            )
        except Exception as e:
            logging.warning(f"ChromaDB LTM store failed: {e}")
            return None
        return doc_id

    # -----------------------------------------------------------------------
    # MongoDB write helpers
    # -----------------------------------------------------------------------

    def _store_mongodb_stm(self, content: str, metadata: Dict, quality_score: float) -> Optional[str]:
        """Insert a record into the MongoDB short-term collection."""
        if not hasattr(self, 'stm_collection') or self.stm_collection is None:
            return None
        doc_id = str(time.time_ns())
        try:
            self.stm_collection.insert_one({
                "_id": doc_id,
                "content": content,
                "metadata": metadata,
                "quality_score": quality_score,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logging.warning(f"MongoDB STM store failed: {e}")
            return None
        return doc_id

    def _store_mongodb_ltm(self, content: str, metadata: Dict, quality_score: float) -> Optional[str]:
        """Insert a record into the MongoDB long-term collection."""
        if not hasattr(self, 'ltm_collection') or self.ltm_collection is None:
            return None
        doc_id = str(time.time_ns())
        try:
            self.ltm_collection.insert_one({
                "_id": doc_id,
                "content": content,
                "metadata": metadata,
                "quality_score": quality_score,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logging.warning(f"MongoDB LTM store failed: {e}")
            return None
        return doc_id