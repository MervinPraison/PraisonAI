"""
Memory Adapter Factory Functions

Provides factory functions for heavy memory adapters that replace hardcoded imports
in memory/memory.py. These enable lazy loading of heavy dependencies while maintaining
the protocol-driven architecture.

Each factory function:
1. Lazy imports the required dependencies 
2. Creates and returns an adapter instance that implements MemoryProtocol
3. Raises clear ImportError with installation instructions if dependencies missing

This approach follows the protocol-driven core principle by moving heavy implementations
out of the core Memory class while preserving backward compatibility.
"""

import logging
import os
import threading
from typing import Any, Dict, List, Optional
from ..protocols import MemoryProtocol

logger = logging.getLogger(__name__)


def safe_mem0_search(mem0_client, **kwargs) -> List[Dict[str, Any]]:
    """
    Defensive wrapper for mem0.search() to handle MongoDB vector store compatibility.

    Catches the specific TypeError about an unexpected 'vectors' kwarg and falls back
    gracefully by returning an empty result set. This addresses the upstream mem0 bug:
    https://github.com/mem0ai/mem0/issues/3185

    Any other TypeError is re-raised unchanged.
    """
    try:
        return mem0_client.search(**kwargs)
    except TypeError as e:
        error_msg = str(e).lower()
        if "unexpected keyword argument" in error_msg and "vectors" in error_msg:
            logger.warning(
                "Detected mem0 MongoDB vector store compatibility issue. "
                "This is a known upstream bug: https://github.com/mem0ai/mem0/issues/3185. "
                "The MongoDB vector store requires Atlas and has signature mismatches. "
                "Consider using Qdrant or Chroma as mem0 vector store backends instead."
            )
            # Return empty results rather than crashing
            return []
        # Re-raise if it's a different TypeError
        raise


def create_mem0_memory_adapter(**kwargs) -> MemoryProtocol:
    """
    Factory function to create Mem0 memory adapter.
    
    Lazy imports mem0 and creates an adapter that wraps mem0.Memory
    to implement MemoryProtocol.
    
    Args:
        **kwargs: Configuration passed to mem0 Memory
        
    Returns:
        MemoryProtocol adapter instance
        
    Raises:
        ImportError: If mem0 is not installed
    """
    try:
        import mem0
    except ImportError:
        raise ImportError(
            "mem0ai is not installed. "
            "Run: pip install 'praisonaiagents[memory]'"
        )
    
    return Mem0MemoryAdapter(mem0_config=kwargs)


def create_chroma_memory_adapter(**kwargs) -> MemoryProtocol:
    """
    Factory function to create ChromaDB memory adapter.
    
    Lazy imports chromadb and creates an adapter that implements MemoryProtocol
    using ChromaDB as the vector store backend.
    
    Args:
        **kwargs: Configuration passed to ChromaDB
        
    Returns:
        MemoryProtocol adapter instance
        
    Raises:
        ImportError: If chromadb is not installed
    """
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError:
        raise ImportError(
            "chromadb is required for chroma adapter. Install with: pip install chromadb"
        )
    
    return ChromaMemoryAdapter(chromadb=chromadb, chroma_settings=ChromaSettings, **kwargs)


def create_mongodb_memory_adapter(**kwargs) -> MemoryProtocol:
    """
    Factory function to create MongoDB memory adapter.
    
    Lazy imports pymongo and creates an adapter that implements MemoryProtocol
    using MongoDB as the document store backend.
    
    Args:
        **kwargs: Configuration passed to MongoDB client
        
    Returns:
        MemoryProtocol adapter instance
        
    Raises:
        ImportError: If pymongo is not installed
    """
    try:
        import pymongo
        from pymongo import MongoClient
    except ImportError:
        raise ImportError(
            "pymongo is required for mongodb adapter. Install with: pip install pymongo"
        )
    
    return MongoDBMemoryAdapter(pymongo=pymongo, mongo_client=MongoClient, **kwargs)


def create_dakera_memory_adapter(**kwargs) -> MemoryProtocol:
    """
    Factory function to create a Dakera memory adapter.

    Lazy imports the ``dakera`` SDK and creates an adapter that wraps a
    ``DakeraClient`` to implement ``MemoryProtocol``. Dakera is a self-hosted
    memory server providing decay-weighted vector recall scoped by ``agent_id``.

    Args:
        **kwargs: Configuration passed to the adapter. Recognised keys (either
            at the top level or nested under a ``"config"`` dict, mirroring the
            mem0 adapter):

            - ``url`` / ``base_url``: Dakera server URL
              (falls back to ``DAKERA_URL`` / ``DAKERA_API_URL`` env, then
              ``http://localhost:3000``).
            - ``api_key``: API key (falls back to ``DAKERA_API_KEY`` env).
            - ``agent_id``: Namespace for the agent's memories
              (falls back to ``DAKERA_AGENT_ID`` env, then ``"praisonai"``).
            - ``short_term_type`` / ``long_term_type``: Dakera memory types to
              use for the two tiers (default ``"working"`` and ``"episodic"``).
            - ``default_importance``: Importance score for stored memories
              when none is supplied (default ``0.5``).

    Returns:
        MemoryProtocol adapter instance.

    Raises:
        ImportError: If the ``dakera`` SDK is not installed.
    """
    try:
        import dakera  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "dakera is required for the dakera adapter. "
            "Install with: pip install 'praisonaiagents[dakera]' (or: pip install dakera)"
        ) from exc

    return DakeraMemoryAdapter(dakera_config=kwargs)


class Mem0MemoryAdapter:
    """
    Memory adapter that wraps mem0.Memory to implement MemoryProtocol.
    
    This adapter handles the integration between PraisonAI's memory interface
    and mem0's memory system.
    """
    
    def __init__(self, mem0_config: Dict[str, Any]):
        """Initialize mem0 memory adapter."""
        import mem0
        
        config = mem0_config.get("config", {})
        api_key = config.get("api_key", os.getenv("MEM0_API_KEY"))
        org_id = config.get("org_id")
        proj_id = config.get("project_id")
        
        # Check if graph memory is enabled
        graph_config = config.get("graph_store")
        use_graph = graph_config is not None
        
        if use_graph:
            # Initialize with graph memory support
            mem0_config_dict = {"graph_store": graph_config}
            
            # Add other configurations if provided
            for key in ["vector_store", "llm", "embedder"]:
                if key in config:
                    mem0_config_dict[key] = config[key]
            
            self.mem0_client = mem0.Memory.from_config(config_dict=mem0_config_dict)
            self.graph_enabled = True
        else:
            # Use traditional MemoryClient
            if org_id and proj_id:
                self.mem0_client = mem0.MemoryClient(api_key=api_key, org_id=org_id, project_id=proj_id)
            else:
                self.mem0_client = mem0.MemoryClient(api_key=api_key)
            self.graph_enabled = False
    
    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store in mem0 (treated as long-term since mem0 doesn't distinguish)."""
        return self.store_long_term(text, metadata, **kwargs)
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search mem0 (treated as long-term since mem0 doesn't distinguish)."""
        return self.search_long_term(query, limit, **kwargs)
    
    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store text in mem0."""
        result = self.mem0_client.add(text, metadata=metadata or {})
        return str(result[0]["id"]) if result else ""
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search mem0 for relevant memories."""
        search_params = {"query": query, "limit": limit}
        search_params.update(kwargs)

        return safe_mem0_search(self.mem0_client, **search_params)
    
    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all memories from mem0."""
        return self.mem0_client.get_all(**kwargs)


class ChromaMemoryAdapter:
    """
    Memory adapter that uses ChromaDB to implement MemoryProtocol.
    """
    
    def __init__(self, chromadb, chroma_settings, **kwargs):
        """Initialize ChromaDB memory adapter."""
        self.chromadb = chromadb
        self.chroma_settings = chroma_settings
        
        # Configuration
        rag_path = kwargs.get("rag_db_path", "chroma_db")
        os.makedirs(rag_path, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=rag_path,
            settings=chroma_settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Initialize collection
        collection_name = kwargs.get("collection_name", "memory_store")
        self.collection_name = collection_name
        try:
            self.collection = self.client.get_collection(name=collection_name)
        except Exception:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
    
    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store in ChromaDB (short-term and long-term treated the same)."""
        return self.store_long_term(text, metadata, **kwargs)
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search ChromaDB."""
        return self.search_long_term(query, limit, **kwargs)
    
    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store text in ChromaDB with embedding."""
        # Get embedding
        from praisonaiagents.embedding import embedding
        embedding_model = kwargs.get("embedding_model", "text-embedding-3-small")
        
        result = embedding(text, model=embedding_model)
        text_embedding = result.embeddings[0] if result.embeddings else None
        
        if text_embedding is None:
            raise RuntimeError("Failed to generate embedding for text")
        
        # Generate ID and store
        import time
        doc_id = str(time.time_ns())
        
        # Sanitize metadata for ChromaDB
        sanitized_metadata = self._sanitize_metadata(metadata or {})
        
        self.collection.add(
            documents=[text],
            metadatas=[sanitized_metadata],
            ids=[doc_id],
            embeddings=[text_embedding]
        )
        
        return doc_id
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search ChromaDB using vector similarity."""
        from praisonaiagents.embedding import embedding
        embedding_model = kwargs.get("embedding_model", "text-embedding-3-small")
        
        result = embedding(query, model=embedding_model)
        query_embedding = result.embeddings[0] if result.embeddings else None
        
        if query_embedding is None:
            return []
        
        # Search ChromaDB
        response = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )
        
        results = []
        if response["ids"]:
            for i in range(len(response["ids"][0])):
                metadata = response["metadatas"][0][i] if "metadatas" in response else {}
                text = response["documents"][0][i]
                score = 1.0 - (response["distances"][0][i] if "distances" in response else 0.0)
                
                results.append({
                    "id": response["ids"][0][i],
                    "text": text,
                    "metadata": metadata,
                    "score": score
                })
        
        return results
    
    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all memories from ChromaDB."""
        response = self.collection.get(include=["documents", "metadatas"])
        
        results = []
        if response["ids"]:
            for i, doc_id in enumerate(response["ids"]):
                results.append({
                    "id": doc_id,
                    "text": response["documents"][i],
                    "metadata": response["metadatas"][i] if "metadatas" in response else {},
                    "type": "long_term"
                })
        
        return results
    
    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """Sanitize metadata for ChromaDB - convert to acceptable types."""
        sanitized = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                sanitized[k] = v
            elif isinstance(v, dict):
                sanitized[k] = str(v)
            else:
                sanitized[k] = str(v)
        return sanitized
    
    def close(self):
        """Clean up ChromaDB resources."""
        # ChromaDB PersistentClient has no explicit close; release references.
        self.client = None
        self.collection = None


class MongoDBMemoryAdapter:
    """
    Memory adapter that uses MongoDB to implement MemoryProtocol.
    """
    
    def __init__(self, pymongo, mongo_client, **kwargs):
        """Initialize MongoDB memory adapter."""
        self.pymongo = pymongo
        
        config = kwargs.get("config", {})
        connection_string = config.get("connection_string", "mongodb://localhost:27017/")
        database_name = config.get("database", "praisonai")
        self.use_vector_search = config.get("use_vector_search", False)
        
        # Initialize MongoDB client
        self.client = mongo_client(
            connection_string,
            maxPoolSize=config.get("max_pool_size", 50),
            minPoolSize=config.get("min_pool_size", 10),
            maxIdleTimeMS=config.get("max_idle_time", 30000),
            serverSelectionTimeoutMS=config.get("server_selection_timeout", 5000),
            retryWrites=True,
            retryReads=True
        )
        
        # Test connection
        self.client.admin.command('ping')
        
        # Setup database and collections
        self.db = self.client[database_name]
        self.short_collection = self.db.short_term_memory
        self.long_collection = self.db.long_term_memory
        
        # Create indexes for better performance
        self._create_indexes()
    
    def _create_indexes(self):
        """Create MongoDB indexes for better performance."""
        try:
            # Text search indexes
            self.short_collection.create_index([("content", "text")])
            self.long_collection.create_index([("content", "text")])
            
            # Compound indexes for filtering
            self.short_collection.create_index([("created_at", -1), ("metadata.quality", -1)])
            self.long_collection.create_index([("created_at", -1), ("metadata.quality", -1)])
        except Exception:
            pass  # Indexes might already exist
    
    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store in MongoDB short-term collection."""
        from datetime import datetime, timezone
        import time
        
        doc_id = str(time.time_ns())
        doc = {
            "_id": doc_id,
            "content": text,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
            "memory_type": "short_term"
        }
        
        self.short_collection.insert_one(doc)
        return doc_id
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search MongoDB short-term collection."""
        search_filter = {"$text": {"$search": query}}
        
        results = []
        for doc in self.short_collection.find(search_filter).limit(limit):
            results.append({
                "id": str(doc["_id"]),
                "text": doc["content"],
                "metadata": doc.get("metadata", {}),
                "score": 1.0
            })
        
        return results
    
    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store in MongoDB long-term collection."""
        from datetime import datetime, timezone
        import time
        
        doc_id = str(time.time_ns())
        doc = {
            "_id": doc_id,
            "content": text,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
            "memory_type": "long_term"
        }
        
        # Add embedding if vector search is enabled
        if self.use_vector_search:
            embedding = self._get_embedding(text)
            if embedding:
                doc["embedding"] = embedding
        
        self.long_collection.insert_one(doc)
        return doc_id
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search MongoDB long-term collection."""
        results = []
        
        # Try vector search first if enabled
        if self.use_vector_search:
            embedding = self._get_embedding(query)
            if embedding:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": "vector_index",
                            "path": "embedding",
                            "queryVector": embedding,
                            "numCandidates": limit * 10,
                            "limit": limit
                        }
                    },
                    {
                        "$addFields": {
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
                
                try:
                    for doc in self.long_collection.aggregate(pipeline):
                        results.append({
                            "id": str(doc["_id"]),
                            "text": doc["content"],
                            "metadata": doc.get("metadata", {}),
                            "score": doc.get("score", 1.0)
                        })
                except Exception:
                    pass  # Fall back to text search
        
        # Fallback to text search
        if not results:
            search_filter = {"$text": {"$search": query}}
            for doc in self.long_collection.find(search_filter).limit(limit):
                results.append({
                    "id": str(doc["_id"]),
                    "text": doc["content"],
                    "metadata": doc.get("metadata", {}),
                    "score": 1.0
                })
        
        return results
    
    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all memories from both collections."""
        results = []
        
        # Get short-term memories
        for doc in self.short_collection.find():
            results.append({
                "id": str(doc["_id"]),
                "text": doc["content"],
                "metadata": doc.get("metadata", {}),
                "created_at": doc.get("created_at"),
                "type": "short_term"
            })
        
        # Get long-term memories
        for doc in self.long_collection.find():
            results.append({
                "id": str(doc["_id"]),
                "text": doc["content"],
                "metadata": doc.get("metadata", {}),
                "created_at": doc.get("created_at"),
                "type": "long_term"
            })
        
        return results
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text."""
        try:
            from praisonaiagents.embedding import embedding
            result = embedding(text, model="text-embedding-3-small")
            return result.embeddings[0] if result.embeddings else None
        except Exception:
            return None
    
    def close(self):
        """Clean up MongoDB resources."""
        if hasattr(self, 'client') and self.client:
            try:
                self.client.close()
            except Exception as e:
                import logging
                logging.warning(f"MongoDB cleanup failed: {e}")
            finally:
                self.client = None


class DakeraMemoryAdapter:
    """
    Memory adapter that wraps the Dakera SDK to implement ``MemoryProtocol``.

    Dakera (https://dakera.ai) is a self-hosted memory server that provides
    persistent, decay-weighted vector recall across sessions: memories are
    importance-scored and decay over time, so stale context stops competing
    with fresh, relevant facts. All memories are scoped by ``agent_id``.

    Unlike a flat vector store, Dakera has a first-class ``memory_type`` field,
    so this adapter maps PraisonAI's two tiers onto distinct Dakera types
    (short-term -> ``"working"``, long-term -> ``"episodic"`` by default),
    keeping recency-heavy scratch context separate from durable knowledge.

    Also implements the optional ``DeletableMemoryProtocol`` (``delete_memory`` /
    ``delete_memories``) and ``ResettableMemoryProtocol`` (``reset_short_term`` /
    ``reset_long_term``).
    """

    def __init__(self, dakera_config: Dict[str, Any]):
        """Initialise the Dakera memory adapter."""
        from dakera import DakeraClient

        # Support both a flat config and a nested {"config": {...}} form,
        # mirroring Mem0MemoryAdapter.
        config = dakera_config.get("config", dakera_config) or {}

        url = (
            config.get("url")
            or config.get("base_url")
            or os.getenv("DAKERA_URL")
            or os.getenv("DAKERA_API_URL")
            or "http://localhost:3000"
        )
        api_key = config.get("api_key") or os.getenv("DAKERA_API_KEY")

        self.agent_id = (
            config.get("agent_id")
            or os.getenv("DAKERA_AGENT_ID")
            or "praisonai"
        )
        self.short_term_type = config.get("short_term_type", "working")
        self.long_term_type = config.get("long_term_type", "episodic")
        self.default_importance = config.get("default_importance", 0.5)

        self.client = DakeraClient(base_url=url, api_key=api_key)

    # -- helpers ------------------------------------------------------------

    def _store(self, text: str, memory_type: str,
               metadata: Optional[Dict[str, Any]], kwargs: Dict[str, Any]) -> str:
        """Store a memory of ``memory_type`` and return its id."""
        meta = dict(metadata or {})
        # Always strip reserved keys from metadata so they never leak into the
        # stored payload, then let explicit kwargs take precedence over them.
        meta_importance = meta.pop("importance", None)
        meta_session_id = meta.pop("session_id", None)
        meta_tags = meta.pop("tags", None)

        importance = kwargs.get("importance")
        if importance is None:
            importance = (
                meta_importance if meta_importance is not None else self.default_importance
            )
        session_id = kwargs.get("session_id") or meta_session_id
        tags = kwargs.get("tags") or meta_tags

        result = self.client.store_memory(
            agent_id=self.agent_id,
            content=text,
            memory_type=memory_type,
            importance=importance,
            metadata=meta or None,
            session_id=session_id,
            tags=tags,
        )
        # store_memory returns the stored memory dict.
        return str(result.get("id", "")) if isinstance(result, dict) else str(result)

    def _search(self, query: str, memory_type: str,
                limit: int, kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Recall memories of ``memory_type`` matching ``query``."""
        response = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            top_k=limit,
            memory_type=memory_type,
            min_importance=kwargs.get("min_importance"),
        )
        return [self._to_result(m) for m in response.memories]

    @staticmethod
    def _to_result(memory: Any) -> Dict[str, Any]:
        """Normalise a Dakera memory object into PraisonAI's result dict shape."""
        return {
            "id": str(getattr(memory, "id", "")),
            "text": getattr(memory, "content", ""),
            "metadata": getattr(memory, "metadata", None) or {},
            "score": getattr(memory, "score", None),
            "memory_type": getattr(memory, "memory_type", None),
        }

    # -- MemoryProtocol -----------------------------------------------------

    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None,
                         **kwargs) -> str:
        """Store content in short-term (``working``) memory."""
        return self._store(text, self.short_term_type, metadata, kwargs)

    def search_short_term(self, query: str, limit: int = 5,
                          **kwargs) -> List[Dict[str, Any]]:
        """Search short-term (``working``) memory."""
        return self._search(query, self.short_term_type, limit, kwargs)

    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None,
                        **kwargs) -> str:
        """Store content in long-term (``episodic``) memory."""
        return self._store(text, self.long_term_type, metadata, kwargs)

    def search_long_term(self, query: str, limit: int = 5,
                         **kwargs) -> List[Dict[str, Any]]:
        """Search long-term (``episodic``) memory."""
        return self._search(query, self.long_term_type, limit, kwargs)

    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Return all memories for the agent (no embedding required)."""
        from dakera import BatchRecallRequest

        limit = kwargs.get("limit", 1000)
        response = self.client.batch_recall(
            BatchRecallRequest(agent_id=self.agent_id, limit=limit)
        )
        return [self._to_result(m) for m in response.memories]

    # -- DeletableMemoryProtocol -------------------------------------------

    def delete_memory(self, memory_id: str,
                      memory_type: Optional[str] = None) -> bool:
        """Delete a specific memory by id. Returns True on success."""
        try:
            self.client.forget(agent_id=self.agent_id, memory_id=memory_id)
            return True
        except Exception as e:
            import logging
            logging.warning(
                f"Dakera delete_memory({memory_id}) failed for agent "
                f"'{self.agent_id}': {e}"
            )
            return False

    def delete_memories(self, memory_ids: List[str]) -> int:
        """Delete multiple memories by id. Returns the number deleted."""
        return sum(1 for mid in memory_ids if self.delete_memory(mid))

    # -- ResettableMemoryProtocol ------------------------------------------

    def _reset_type(self, memory_type: str) -> None:
        from dakera import BatchForgetRequest, BatchMemoryFilter

        self.client.batch_forget(
            BatchForgetRequest(
                agent_id=self.agent_id,
                filter=BatchMemoryFilter(memory_type=memory_type),
            )
        )

    def reset_short_term(self) -> None:
        """Clear all short-term (``working``) memory for the agent."""
        self._reset_type(self.short_term_type)

    def reset_long_term(self) -> None:
        """Clear all long-term (``episodic``) memory for the agent."""
        self._reset_type(self.long_term_type)