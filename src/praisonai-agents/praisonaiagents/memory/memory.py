import os
import sqlite3
import json
import time
import shutil
from typing import Any, Dict, List, Optional, Union, Literal
import logging

# Disable litellm telemetry before any imports
os.environ["LITELLM_TELEMETRY"] = "False"

# Set up logger
logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    pass

try:
    import mem0
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import litellm
    litellm.telemetry = False  # Disable telemetry
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False




class Memory:
    """
    A single-file memory manager covering:
    - Short-term memory (STM) for ephemeral context
    - Long-term memory (LTM) for persistent knowledge
    - Entity memory (structured data about named entities)
    - User memory (preferences/history for each user)
    - Quality score logic for deciding which data to store in LTM
    - Context building from multiple memory sources
    - Graph memory support for complex relationship storage (via Mem0)

    Config example:
    {
      "provider": "rag" or "mem0" or "none",
      "use_embedding": True,
      "short_db": "short_term.db",
      "long_db": "long_term.db",
      "rag_db_path": "rag_db",   # optional path for local embedding store
      "config": {
        "api_key": "...",       # if mem0 usage
        "org_id": "...",
        "project_id": "...",
        
        # Graph memory configuration (optional)
        "graph_store": {
          "provider": "neo4j" or "memgraph",
          "config": {
            "url": "neo4j+s://xxx" or "bolt://localhost:7687",
            "username": "neo4j" or "memgraph",
            "password": "xxx"
          }
        },
        
        # Optional additional configurations for graph memory
        "vector_store": {
          "provider": "qdrant",
          "config": {"host": "localhost", "port": 6333}
        },
        "llm": {
          "provider": "openai",
          "config": {"model": "gpt-4o", "api_key": "..."}
        },
        "embedder": {
          "provider": "openai",
          "config": {"model": "text-embedding-3-small", "api_key": "..."}
        }
      }
    }
    
    Note: Graph memory requires "mem0ai[graph]" installation and works alongside 
    vector-based memory for enhanced relationship-aware retrieval.
    """

    def __init__(self, config: Dict[str, Any], verbose: int = 0):
        self.cfg = config or {}
        self.verbose = verbose
        
        # Set logger level based on verbose
        if verbose >= 5:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)
            
        # Also set ChromaDB and OpenAI client loggers to WARNING
        logging.getLogger('chromadb').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('chromadb.segment.impl.vector.local_persistent_hnsw').setLevel(logging.ERROR)
            
        self.provider = self.cfg.get("provider", "rag")
        self.use_mem0 = (self.provider.lower() == "mem0") and MEM0_AVAILABLE
        self.use_rag = (self.provider.lower() == "rag") and CHROMADB_AVAILABLE and self.cfg.get("use_embedding", False)
        self.graph_enabled = False  # Initialize graph support flag

        # Create .praison directory if it doesn't exist
        os.makedirs(".praison", exist_ok=True)

        # Short-term DB
        self.short_db = self.cfg.get("short_db", ".praison/short_term.db")
        self._init_stm()

        # Long-term DB
        self.long_db = self.cfg.get("long_db", ".praison/long_term.db")
        self._init_ltm()

        # Conditionally init Mem0 or local RAG
        if self.use_mem0:
            self._init_mem0()
        elif self.use_rag:
            self._init_chroma()

    def _log_verbose(self, msg: str, level: int = logging.INFO):
        """Only log if verbose >= 5"""
        if self.verbose >= 5:
            logger.log(level, msg)

    # -------------------------------------------------------------------------
    #                          Initialization
    # -------------------------------------------------------------------------
    def _init_stm(self):
        """Creates or verifies short-term memory table."""
        os.makedirs(os.path.dirname(self.short_db) or ".", exist_ok=True)
        conn = sqlite3.connect(self.short_db)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS short_mem (
            id TEXT PRIMARY KEY,
            content TEXT,
            meta TEXT,
            created_at REAL
        )
        """)
        conn.commit()
        conn.close()

    def _init_ltm(self):
        """Creates or verifies long-term memory table."""
        os.makedirs(os.path.dirname(self.long_db) or ".", exist_ok=True)
        conn = sqlite3.connect(self.long_db)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS long_mem (
            id TEXT PRIMARY KEY,
            content TEXT,
            meta TEXT,
            created_at REAL
        )
        """)
        conn.commit()
        conn.close()

    def _init_mem0(self):
        """Initialize Mem0 client for agent or user memory with optional graph support."""
        mem_cfg = self.cfg.get("config", {})
        api_key = mem_cfg.get("api_key", os.getenv("MEM0_API_KEY"))
        org_id = mem_cfg.get("org_id")
        proj_id = mem_cfg.get("project_id")
        
        # Check if graph memory is enabled
        graph_config = mem_cfg.get("graph_store")
        use_graph = graph_config is not None
        
        if use_graph:
            # Initialize with graph memory support
            from mem0 import Memory
            self._log_verbose("Initializing Mem0 with graph memory support")
            
            # Build Mem0 config with graph store
            mem0_config = {}
            
            # Add graph store configuration
            mem0_config["graph_store"] = graph_config
            
            # Add other configurations if provided
            if "vector_store" in mem_cfg:
                mem0_config["vector_store"] = mem_cfg["vector_store"]
            if "llm" in mem_cfg:
                mem0_config["llm"] = mem_cfg["llm"]
            if "embedder" in mem_cfg:
                mem0_config["embedder"] = mem_cfg["embedder"]
            
            # Initialize Memory with graph support
            self.mem0_client = Memory.from_config(config_dict=mem0_config)
            self.graph_enabled = True
            self._log_verbose("Graph memory initialized successfully")
        else:
            # Use traditional MemoryClient
            from mem0 import MemoryClient
            self._log_verbose("Initializing Mem0 with traditional memory client")
            
            if org_id and proj_id:
                self.mem0_client = MemoryClient(api_key=api_key, org_id=org_id, project_id=proj_id)
            else:
                self.mem0_client = MemoryClient(api_key=api_key)
            self.graph_enabled = False

    def _init_chroma(self):
        """Initialize a local Chroma client for embedding-based search."""
        try:
            # Create directory if it doesn't exist
            rag_path = self.cfg.get("rag_db_path", "chroma_db")
            os.makedirs(rag_path, exist_ok=True)

            # Initialize ChromaDB with persistent storage
            self.chroma_client = chromadb.PersistentClient(
                path=rag_path,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )

            collection_name = "memory_store"
            try:
                self.chroma_col = self.chroma_client.get_collection(name=collection_name)
                self._log_verbose("Using existing ChromaDB collection")
            except Exception as e:
                self._log_verbose(f"Collection '{collection_name}' not found. Creating new collection. Error: {e}")
                self.chroma_col = self.chroma_client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                self._log_verbose("Created new ChromaDB collection")

        except Exception as e:
            self._log_verbose(f"Failed to initialize ChromaDB: {e}", logging.ERROR)
            self.use_rag = False

    # -------------------------------------------------------------------------
    #                      Basic Quality Score Computation
    # -------------------------------------------------------------------------
    def compute_quality_score(
        self,
        completeness: float,
        relevance: float,
        clarity: float,
        accuracy: float,
        weights: Dict[str, float] = None
    ) -> float:
        """
        Combine multiple sub-metrics into one final score, as an example.

        Args:
            completeness (float): 0-1
            relevance (float): 0-1
            clarity (float): 0-1
            accuracy (float): 0-1
            weights (Dict[str, float]): optional weighting like {"completeness": 0.25, "relevance": 0.3, ...}

        Returns:
            float: Weighted average 0-1
        """
        if not weights:
            weights = {
                "completeness": 0.25,
                "relevance": 0.25,
                "clarity": 0.25,
                "accuracy": 0.25
            }
        total = (completeness * weights["completeness"]
                 + relevance   * weights["relevance"]
                 + clarity     * weights["clarity"]
                 + accuracy    * weights["accuracy"]
                )
        return round(total, 3)  # e.g. round to 3 decimal places

    # -------------------------------------------------------------------------
    #                           Short-Term Methods
    # -------------------------------------------------------------------------
    def store_short_term(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
        completeness: float = None,
        relevance: float = None,
        clarity: float = None,
        accuracy: float = None,
        weights: Dict[str, float] = None,
        evaluator_quality: float = None
    ):
        """Store in short-term memory with optional quality metrics"""
        logger.info(f"Storing in short-term memory: {text[:100]}...")
        logger.info(f"Metadata: {metadata}")
        
        metadata = self._process_quality_metrics(
            metadata, completeness, relevance, clarity, 
            accuracy, weights, evaluator_quality
        )
        logger.info(f"Processed metadata: {metadata}")
        
        # Existing store logic
        try:
            conn = sqlite3.connect(self.short_db)
            ident = str(time.time_ns())
            conn.execute(
                "INSERT INTO short_mem (id, content, meta, created_at) VALUES (?,?,?,?)",
                (ident, text, json.dumps(metadata), time.time())
            )
            conn.commit()
            conn.close()
            logger.info(f"Successfully stored in short-term memory with ID: {ident}")
        except Exception as e:
            logger.error(f"Failed to store in short-term memory: {e}")
            raise

    def search_short_term(
        self, 
        query: str, 
        limit: int = 5,
        min_quality: float = 0.0,
        relevance_cutoff: float = 0.0,
        rerank: bool = False,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search short-term memory with optional quality filter"""
        self._log_verbose(f"Searching short memory for: {query}")
        
        if self.use_mem0 and hasattr(self, "mem0_client"):
            # Pass rerank and other kwargs to Mem0 search
            search_params = {"query": query, "limit": limit, "rerank": rerank}
            search_params.update(kwargs)
            results = self.mem0_client.search(**search_params)
            filtered = [r for r in results if r.get("score", 1.0) >= relevance_cutoff]
            return filtered
            
        elif self.use_rag and hasattr(self, "chroma_col"):
            try:
                if LITELLM_AVAILABLE:
                    # Use LiteLLM for consistency with the rest of the codebase
                    import litellm
                    
                    response = litellm.embedding(
                        model="text-embedding-3-small",
                        input=query
                    )
                    query_embedding = response.data[0]["embedding"]
                elif OPENAI_AVAILABLE:
                    # Fallback to OpenAI client
                    from openai import OpenAI
                    client = OpenAI()
                    
                    response = client.embeddings.create(
                        input=query,
                        model="text-embedding-3-small"
                    )
                    query_embedding = response.data[0].embedding
                else:
                    self._log_verbose("Neither litellm nor openai available for embeddings", logging.WARNING)
                    return []
                
                resp = self.chroma_col.query(
                    query_embeddings=[query_embedding],
                    n_results=limit
                )
                
                results = []
                if resp["ids"]:
                    for i in range(len(resp["ids"][0])):
                        metadata = resp["metadatas"][0][i] if "metadatas" in resp else {}
                        quality = metadata.get("quality", 0.0)
                        score = 1.0 - (resp["distances"][0][i] if "distances" in resp else 0.0)
                        if quality >= min_quality and score >= relevance_cutoff:
                            results.append({
                                "id": resp["ids"][0][i],
                                "text": resp["documents"][0][i],
                                "metadata": metadata,
                                "score": score
                            })
                return results
            except Exception as e:
                self._log_verbose(f"Error searching ChromaDB: {e}", logging.ERROR)
                return []
        
        else:
            # Local fallback
            conn = sqlite3.connect(self.short_db)
            c = conn.cursor()
            rows = c.execute(
                "SELECT id, content, meta FROM short_mem WHERE content LIKE ? LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()
            conn.close()

            results = []
            for row in rows:
                meta = json.loads(row[2] or "{}")
                quality = meta.get("quality", 0.0)
                if quality >= min_quality:
                    results.append({
                        "id": row[0],
                        "text": row[1],
                        "metadata": meta
                    })
            return results

    def reset_short_term(self):
        """Completely clears short-term memory."""
        conn = sqlite3.connect(self.short_db)
        conn.execute("DELETE FROM short_mem")
        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    #                           Long-Term Methods
    # -------------------------------------------------------------------------
    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """Sanitize metadata for ChromaDB - convert to acceptable types"""
        sanitized = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                sanitized[k] = v
            elif isinstance(v, dict):
                # Convert dict to string representation
                sanitized[k] = str(v)
            else:
                # Convert other types to string
                sanitized[k] = str(v)
        return sanitized

    def store_long_term(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
        completeness: float = None,
        relevance: float = None,
        clarity: float = None,
        accuracy: float = None,
        weights: Dict[str, float] = None,
        evaluator_quality: float = None
    ):
        """Store in long-term memory with optional quality metrics"""
        logger.info(f"Storing in long-term memory: {text[:100]}...")
        logger.info(f"Initial metadata: {metadata}")
        
        # Process metadata
        metadata = metadata or {}
        metadata = self._process_quality_metrics(
            metadata, completeness, relevance, clarity,
            accuracy, weights, evaluator_quality
        )
        logger.info(f"Processed metadata: {metadata}")
        
        # Generate unique ID
        ident = str(time.time_ns())
        created = time.time()

        # Store in SQLite
        try:
            conn = sqlite3.connect(self.long_db)
            conn.execute(
                "INSERT INTO long_mem (id, content, meta, created_at) VALUES (?,?,?,?)",
                (ident, text, json.dumps(metadata), created)
            )
            conn.commit()
            conn.close()
            logger.info(f"Successfully stored in SQLite with ID: {ident}")
        except Exception as e:
            logger.error(f"Error storing in SQLite: {e}")
            return

        # Store in vector database if enabled
        if self.use_rag and hasattr(self, "chroma_col"):
            try:
                if LITELLM_AVAILABLE:
                    # Use LiteLLM for consistency with the rest of the codebase
                    import litellm
                    
                    logger.info("Getting embeddings from LiteLLM...")
                    logger.debug(f"Embedding input text: {text}")
                    
                    response = litellm.embedding(
                        model="text-embedding-3-small",
                        input=text
                    )
                    embedding = response.data[0]["embedding"]
                    logger.info("Successfully got embeddings from LiteLLM")
                    logger.debug(f"Received embedding of length: {len(embedding)}")
                    
                elif OPENAI_AVAILABLE:
                    # Fallback to OpenAI client
                    from openai import OpenAI
                    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                    
                    logger.info("Getting embeddings from OpenAI...")
                    logger.debug(f"Embedding input text: {text}")
                    
                    response = client.embeddings.create(
                        input=text,
                        model="text-embedding-3-small"
                    )
                    embedding = response.data[0].embedding
                    logger.info("Successfully got embeddings from OpenAI")
                    logger.debug(f"Received embedding of length: {len(embedding)}")
                else:
                    logger.warning("Neither litellm nor openai available for embeddings")
                    return
                
                # Sanitize metadata for ChromaDB
                sanitized_metadata = self._sanitize_metadata(metadata)
                
                # Store in ChromaDB with embedding
                self.chroma_col.add(
                    documents=[text],
                    metadatas=[sanitized_metadata],
                    ids=[ident],
                    embeddings=[embedding]
                )
                logger.info(f"Successfully stored in ChromaDB with ID: {ident}")
            except Exception as e:
                logger.error(f"Error storing in ChromaDB: {e}")
        
        elif self.use_mem0 and hasattr(self, "mem0_client"):
            try:
                self.mem0_client.add(text, metadata=metadata)
                logger.info("Successfully stored in Mem0")
            except Exception as e:
                logger.error(f"Error storing in Mem0: {e}")


    def search_long_term(
        self, 
        query: str, 
        limit: int = 5, 
        relevance_cutoff: float = 0.0,
        min_quality: float = 0.0,
        rerank: bool = False,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search long-term memory with optional quality filter"""
        self._log_verbose(f"Searching long memory for: {query}")
        self._log_verbose(f"Min quality: {min_quality}")

        found = []

        if self.use_mem0 and hasattr(self, "mem0_client"):
            # Pass rerank and other kwargs to Mem0 search
            search_params = {"query": query, "limit": limit, "rerank": rerank}
            search_params.update(kwargs)
            results = self.mem0_client.search(**search_params)
            # Filter by quality
            filtered = [r for r in results if r.get("metadata", {}).get("quality", 0.0) >= min_quality]
            logger.info(f"Found {len(filtered)} results in Mem0")
            return filtered

        elif self.use_rag and hasattr(self, "chroma_col"):
            try:
                if LITELLM_AVAILABLE:
                    # Use LiteLLM for consistency with the rest of the codebase
                    import litellm
                    
                    response = litellm.embedding(
                        model="text-embedding-3-small",
                        input=query
                    )
                    query_embedding = response.data[0]["embedding"]
                elif OPENAI_AVAILABLE:
                    # Fallback to OpenAI client
                    from openai import OpenAI
                    client = OpenAI()
                    
                    response = client.embeddings.create(
                        input=query,
                        model="text-embedding-3-small"
                    )
                    query_embedding = response.data[0].embedding
                else:
                    self._log_verbose("Neither litellm nor openai available for embeddings", logging.WARNING)
                    return []
                
                # Search ChromaDB with embedding
                resp = self.chroma_col.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    include=["documents", "metadatas", "distances"]
                )
                
                results = []
                if resp["ids"]:
                    for i in range(len(resp["ids"][0])):
                        metadata = resp["metadatas"][0][i] if "metadatas" in resp else {}
                        text = resp["documents"][0][i]
                        # Add memory record citation
                        text = f"{text} (Memory record: {text})"
                        found.append({
                            "id": resp["ids"][0][i],
                            "text": text,
                            "metadata": metadata,
                            "score": 1.0 - (resp["distances"][0][i] if "distances" in resp else 0.0)
                        })
                logger.info(f"Found {len(found)} results in ChromaDB")

            except Exception as e:
                self._log_verbose(f"Error searching ChromaDB: {e}", logging.ERROR)

        # Always try SQLite as fallback or additional source
        conn = sqlite3.connect(self.long_db)
        c = conn.cursor()
        rows = c.execute(
            "SELECT id, content, meta, created_at FROM long_mem WHERE content LIKE ? LIMIT ?",
            (f"%{query}%", limit)
        ).fetchall()
        conn.close()

        for row in rows:
            meta = json.loads(row[2] or "{}")
            text = row[1]
            # Add memory record citation if not already present
            if "(Memory record:" not in text:
                text = f"{text} (Memory record: {text})"
            # Only add if not already found by ChromaDB/Mem0
            if not any(f["id"] == row[0] for f in found):
                found.append({
                    "id": row[0],
                    "text": text,
                    "metadata": meta,
                    "created_at": row[3]
                })
        logger.info(f"Found {len(found)} total results after SQLite")

        results = found

        # Filter by quality if needed
        if min_quality > 0:
            self._log_verbose(f"Found {len(results)} initial results")
            results = [
                r for r in results 
                if r.get("metadata", {}).get("quality", 0.0) >= min_quality
            ]
            self._log_verbose(f"After quality filter: {len(results)} results")

        # Apply relevance cutoff if specified
        if relevance_cutoff > 0:
            results = [r for r in results if r.get("score", 1.0) >= relevance_cutoff]
            logger.info(f"After relevance filter: {len(results)} results")
        
        return results[:limit]

    def reset_long_term(self):
        """Clear local LTM DB, plus Chroma or mem0 if in use."""
        conn = sqlite3.connect(self.long_db)
        conn.execute("DELETE FROM long_mem")
        conn.commit()
        conn.close()

        if self.use_mem0 and hasattr(self, "mem0_client"):
            # Mem0 has no universal reset API. Could implement partial or no-op.
            pass
        if self.use_rag and hasattr(self, "chroma_client"):
            self.chroma_client.reset()  # entire DB
            self._init_chroma()         # re-init fresh

    # -------------------------------------------------------------------------
    #                       Entity Memory Methods
    # -------------------------------------------------------------------------
    def store_entity(self, name: str, type_: str, desc: str, relations: str):
        """
        Save entity info in LTM (or mem0/rag). 
        We'll label the metadata type = entity for easy filtering.
        """
        data = f"Entity {name}({type_}): {desc} | relationships: {relations}"
        self.store_long_term(data, metadata={"category": "entity"})

    def search_entity(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Filter to items that have metadata 'category=entity'.
        """
        all_hits = self.search_long_term(query, limit=20)  # gather more
        ents = []
        for h in all_hits:
            meta = h.get("metadata") or {}
            if meta.get("category") == "entity":
                ents.append(h)
        return ents[:limit]

    def reset_entity_only(self):
        """
        If you only want to drop entity items from LTM, you'd do a custom 
        delete from local DB where meta LIKE '%category=entity%'. 
        For brevity, we do a full LTM reset here.
        """
        self.reset_long_term()

    # -------------------------------------------------------------------------
    #                       User Memory Methods
    # -------------------------------------------------------------------------
    def store_user_memory(self, user_id: str, text: str, extra: Dict[str, Any] = None):
        """
        If mem0 is used, do user-based addition. Otherwise store in LTM with user in metadata.
        """
        meta = {"user_id": user_id}
        if extra:
            meta.update(extra)

        if self.use_mem0 and hasattr(self, "mem0_client"):
            self.mem0_client.add(text, user_id=user_id, metadata=meta)
        else:
            self.store_long_term(text, metadata=meta)

    def search_user_memory(self, user_id: str, query: str, limit: int = 5, rerank: bool = False, **kwargs) -> List[Dict[str, Any]]:
        """
        If mem0 is used, pass user_id in. Otherwise fallback to local filter on user in metadata.
        """
        if self.use_mem0 and hasattr(self, "mem0_client"):
            # Pass rerank and other kwargs to Mem0 search
            search_params = {"query": query, "limit": limit, "user_id": user_id, "rerank": rerank}
            search_params.update(kwargs)
            return self.mem0_client.search(**search_params)
        else:
            hits = self.search_long_term(query, limit=20)
            filtered = []
            for h in hits:
                meta = h.get("metadata", {})
                if meta.get("user_id") == user_id:
                    filtered.append(h)
            return filtered[:limit]

    def search(self, query: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, 
               run_id: Optional[str] = None, limit: int = 5, rerank: bool = False, **kwargs) -> List[Dict[str, Any]]:
        """
        Generic search method that delegates to appropriate specific search methods.
        Provides compatibility with mem0.Memory interface.
        
        Args:
            query: The search query string
            user_id: Optional user ID for user-specific search
            agent_id: Optional agent ID for agent-specific search  
            run_id: Optional run ID for run-specific search
            limit: Maximum number of results to return
            rerank: Whether to use advanced reranking
            **kwargs: Additional search parameters
            
        Returns:
            List of search results
        """
        # If using mem0, pass all parameters directly
        if self.use_mem0 and hasattr(self, "mem0_client"):
            search_params = {
                "query": query,
                "limit": limit,
                "rerank": rerank
            }
            
            # Add optional parameters if provided
            if user_id is not None:
                search_params["user_id"] = user_id
            if agent_id is not None:
                search_params["agent_id"] = agent_id
            if run_id is not None:
                search_params["run_id"] = run_id
                
            # Include any additional kwargs
            search_params.update(kwargs)
            
            return self.mem0_client.search(**search_params)
        
        # For local memory, use specific search methods
        if user_id:
            # Use user-specific search
            return self.search_user_memory(user_id, query, limit=limit, rerank=rerank, **kwargs)
        else:
            # Default to long-term memory search
            # Note: agent_id and run_id filtering could be added to metadata filtering in the future
            return self.search_long_term(query, limit=limit, rerank=rerank, **kwargs)

    def reset_user_memory(self):
        """
        Clear all user-based info. For simplicity, we do a full LTM reset. 
        Real usage might filter only metadata "user_id".
        """
        self.reset_long_term()

    # -------------------------------------------------------------------------
    #                 Putting it all Together: Task Finalization
    # -------------------------------------------------------------------------
    def finalize_task_output(
        self,
        content: str,
        agent_name: str,
        quality_score: float,
        threshold: float = 0.7,
        metrics: Dict[str, Any] = None,
        task_id: str = None
    ):
        """Store task output in memory with appropriate metadata"""
        logger.info(f"Finalizing task output: {content[:100]}...")
        logger.info(f"Agent: {agent_name}, Quality: {quality_score}, Threshold: {threshold}")
        
        metadata = {
            "task_id": task_id,
            "agent": agent_name,
            "quality": quality_score,
            "metrics": metrics,
            "task_type": "output",
            "stored_at": time.time()
        }
        logger.info(f"Prepared metadata: {metadata}")
        
        # Always store in short-term memory
        try:
            logger.info("Storing in short-term memory...")
            self.store_short_term(
                text=content,
                metadata=metadata
            )
            logger.info("Successfully stored in short-term memory")
        except Exception as e:
            logger.error(f"Failed to store in short-term memory: {e}")
        
        # Store in long-term memory if quality meets threshold
        if quality_score >= threshold:
            try:
                logger.info(f"Quality score {quality_score} >= {threshold}, storing in long-term memory...")
                self.store_long_term(
                    text=content,
                    metadata=metadata
                )
                logger.info("Successfully stored in long-term memory")
            except Exception as e:
                logger.error(f"Failed to store in long-term memory: {e}")
        else:
            logger.info(f"Quality score {quality_score} < {threshold}, skipping long-term storage")

    # -------------------------------------------------------------------------
    #                 Building Context (Short, Long, Entities, User)
    # -------------------------------------------------------------------------
    def build_context_for_task(
        self,
        task_descr: str,
        user_id: Optional[str] = None,
        additional: str = "",
        max_items: int = 3
    ) -> str:
        """
        Merges relevant short-term, long-term, entity, user memories
        into a single text block with deduplication and clean formatting.
        """
        q = (task_descr + " " + additional).strip()
        lines = []
        seen_contents = set()  # Track unique contents

        def normalize_content(content: str) -> str:
            """Normalize content for deduplication"""
            # Extract just the main content without citations for comparison
            normalized = content.split("(Memory record:")[0].strip()
            # Keep more characters to reduce false duplicates
            normalized = ''.join(c.lower() for c in normalized if not c.isspace())
            return normalized

        def format_content(content: str, max_len: int = 150) -> str:
            """Format content with clean truncation at word boundaries"""
            if not content:
                return ""
            
            # Clean up content by removing extra whitespace and newlines
            content = ' '.join(content.split())
            
            # If content contains a memory citation, preserve it
            if "(Memory record:" in content:
                return content  # Keep original citation format
            
            # Regular content truncation
            if len(content) <= max_len:
                return content
            
            truncate_at = content.rfind(' ', 0, max_len - 3)
            if truncate_at == -1:
                truncate_at = max_len - 3
            return content[:truncate_at] + "..."

        def add_section(title: str, hits: List[Any]) -> None:
            """Add a section of memory hits with deduplication"""
            if not hits:
                return
                
            formatted_hits = []
            for h in hits:
                content = h.get('text', '') if isinstance(h, dict) else str(h)
                if not content:
                    continue
                    
                # Keep original format if it has a citation
                if "(Memory record:" in content:
                    formatted = content
                else:
                    formatted = format_content(content)
                
                # Only add if we haven't seen this normalized content before
                normalized = normalize_content(formatted)
                if normalized not in seen_contents:
                    seen_contents.add(normalized)
                    formatted_hits.append(formatted)
            
            if formatted_hits:
                # Add section header
                if lines:
                    lines.append("")  # Space before new section
                lines.append(title)
                lines.append("=" * len(title))  # Underline the title
                lines.append("")  # Space after title
                
                # Add formatted content with bullet points
                for content in formatted_hits:
                    lines.append(f" • {content}")

        # Add each section
        # First get all results
        short_term = self.search_short_term(q, limit=max_items)
        long_term = self.search_long_term(q, limit=max_items)
        entities = self.search_entity(q, limit=max_items)
        user_mem = self.search_user_memory(user_id, q, limit=max_items) if user_id else []

        # Add sections in order of priority
        add_section("Short-term Memory Context", short_term)
        add_section("Long-term Memory Context", long_term)
        add_section("Entity Context", entities)
        if user_id:
            add_section("User Context", user_mem)

        return "\n".join(lines) if lines else ""

    # -------------------------------------------------------------------------
    #                      Master Reset (Everything)
    # -------------------------------------------------------------------------
    def reset_all(self):
        """
        Fully wipes short-term, long-term, and any memory in mem0 or rag.
        """
        self.reset_short_term()
        self.reset_long_term()
        # Entities & user memory are stored in LTM or mem0, so no separate step needed.

    def _process_quality_metrics(
        self,
        metadata: Dict[str, Any],
        completeness: float = None,
        relevance: float = None,
        clarity: float = None, 
        accuracy: float = None,
        weights: Dict[str, float] = None,
        evaluator_quality: float = None
    ) -> Dict[str, Any]:
        """Process and store quality metrics in metadata"""
        metadata = metadata or {}
        
        # Handle sub-metrics if provided
        if None not in [completeness, relevance, clarity, accuracy]:
            metadata.update({
                "completeness": completeness,
                "relevance": relevance,
                "clarity": clarity,
                "accuracy": accuracy,
                "quality": self.compute_quality_score(
                    completeness, relevance, clarity, accuracy, weights
                )
            })
        # Handle external evaluator quality if provided
        elif evaluator_quality is not None:
            metadata["quality"] = evaluator_quality
        
        return metadata

    def calculate_quality_metrics(
        self,
        output: str,
        expected_output: str,
        llm: Optional[str] = None,
        custom_prompt: Optional[str] = None
    ) -> Dict[str, float]:
        """Calculate quality metrics using LLM"""
        logger.info("Calculating quality metrics for output")
        logger.info(f"Output: {output[:100]}...")
        logger.info(f"Expected: {expected_output[:100]}...")
        
        # Default evaluation prompt
        default_prompt = f"""
        Evaluate the following output against expected output.
        Score each metric from 0.0 to 1.0:
        - Completeness: Does it address all requirements?
        - Relevance: Does it match expected output?
        - Clarity: Is it clear and well-structured?
        - Accuracy: Is it factually correct?

        Expected: {expected_output}
        Actual: {output}

        Return ONLY a JSON with these keys: completeness, relevance, clarity, accuracy
        Example: {{"completeness": 0.95, "relevance": 0.8, "clarity": 0.9, "accuracy": 0.85}}
        """

        try:
            if LITELLM_AVAILABLE:
                # Use LiteLLM for consistency with the rest of the codebase
                import litellm
                
                # Convert model name if it's in litellm format
                model_name = llm or "gpt-4o-mini"
                
                response = litellm.completion(
                    model=model_name,
                    messages=[{
                        "role": "user", 
                        "content": custom_prompt or default_prompt
                    }],
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
            elif OPENAI_AVAILABLE:
                # Fallback to OpenAI client
                from openai import OpenAI
                client = OpenAI()
                
                response = client.chat.completions.create(
                    model=llm or "gpt-4o-mini",
                    messages=[{
                        "role": "user", 
                        "content": custom_prompt or default_prompt
                    }],
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
            else:
                logger.error("Neither litellm nor openai available for quality calculation")
                return {
                    "completeness": 0.0,
                    "relevance": 0.0,
                    "clarity": 0.0,
                    "accuracy": 0.0
                }
            
            metrics = json.loads(response.choices[0].message.content)
            
            # Validate metrics
            required = ["completeness", "relevance", "clarity", "accuracy"]
            if not all(k in metrics for k in required):
                raise ValueError("Missing required metrics in LLM response")
            
            logger.info(f"Calculated metrics: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return {
                "completeness": 0.0,
                "relevance": 0.0,
                "clarity": 0.0,
                "accuracy": 0.0
            }

    def store_quality(
        self,
        text: str,
        quality_score: float,
        task_id: Optional[str] = None,
        iteration: Optional[int] = None,
        metrics: Optional[Dict[str, float]] = None,
        memory_type: Literal["short", "long"] = "long"
    ) -> None:
        """Store quality metrics in memory"""
        logger.info(f"Attempting to store in {memory_type} memory: {text[:100]}...")
        
        metadata = {
            "quality": quality_score,
            "task_id": task_id,
            "iteration": iteration
        }
        
        if metrics:
            metadata.update({
                k: v for k, v in metrics.items()  # Remove metric_ prefix
            })
            
        logger.info(f"With metadata: {metadata}")
        
        try:
            if memory_type == "short":
                self.store_short_term(text, metadata=metadata)
                logger.info("Successfully stored in short-term memory")
            else:
                self.store_long_term(text, metadata=metadata)
                logger.info("Successfully stored in long-term memory")
        except Exception as e:
            logger.error(f"Failed to store in memory: {e}")

    def search_with_quality(
        self,
        query: str,
        min_quality: float = 0.0,
        memory_type: Literal["short", "long"] = "long",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search with quality filter"""
        logger.info(f"Searching {memory_type} memory for: {query}")
        logger.info(f"Min quality: {min_quality}")
        
        search_func = (
            self.search_short_term if memory_type == "short" 
            else self.search_long_term
        )
        
        results = search_func(query, limit=limit)
        logger.info(f"Found {len(results)} initial results")
        
        filtered = [
            r for r in results 
            if r.get("metadata", {}).get("quality", 0.0) >= min_quality
        ]
        logger.info(f"After quality filter: {len(filtered)} results")
        
        return filtered
