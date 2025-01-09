import os
import sqlite3
import json
import time
import shutil
from typing import Any, Dict, List, Optional, Union, Literal
import logging

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    import mem0
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Memory:
    """
    A single-file memory manager covering:
    - Short-term memory (STM) for ephemeral context
    - Long-term memory (LTM) for persistent knowledge
    - Entity memory (structured data about named entities)
    - User memory (preferences/history for each user)
    - Quality score logic for deciding which data to store in LTM
    - Context building from multiple memory sources

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
        ...
      }
    }
    """

    def __init__(self, config: Dict[str, Any]):
        self.cfg = config or {}
        self.provider = self.cfg.get("provider", "rag")
        self.use_mem0 = (self.provider.lower() == "mem0") and MEM0_AVAILABLE
        self.use_rag = (self.provider.lower() == "rag") and CHROMADB_AVAILABLE and self.cfg.get("use_embedding", False)

        # Short-term DB
        self.short_db = self.cfg.get("short_db", "short_term.db")
        self._init_stm()

        # Long-term DB
        self.long_db = self.cfg.get("long_db", "long_term.db")
        self._init_ltm()

        # Conditionally init Mem0 or local RAG
        if self.use_mem0:
            self._init_mem0()
        elif self.use_rag:
            self._init_chroma()

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
        """Initialize Mem0 client for agent or user memory."""
        from mem0 import MemoryClient
        mem_cfg = self.cfg.get("config", {})
        api_key = mem_cfg.get("api_key", os.getenv("MEM0_API_KEY"))
        org_id = mem_cfg.get("org_id")
        proj_id = mem_cfg.get("project_id")
        if org_id and proj_id:
            self.mem0_client = MemoryClient(api_key=api_key, org_id=org_id, project_id=proj_id)
        else:
            self.mem0_client = MemoryClient(api_key=api_key)

    def _init_chroma(self):
        """Initialize a local Chroma client for embedding-based search."""
        import chromadb
        self.chroma_client = chromadb.PersistentClient(
            path=self.cfg.get("rag_db_path", "chroma_db"),
            settings=ChromaSettings(allow_reset=True),
        )
        try:
            self.chroma_col = self.chroma_client.get_collection(name="unified_memory")
        except:
            self.chroma_col = self.chroma_client.create_collection(name="unified_memory")

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
        metadata = self._process_quality_metrics(
            metadata, completeness, relevance, clarity, 
            accuracy, weights, evaluator_quality
        )
        
        # Existing store logic
        conn = sqlite3.connect(self.short_db)
        ident = str(time.time_ns())
        conn.execute(
            "INSERT INTO short_mem (id, content, meta, created_at) VALUES (?,?,?,?)",
            (ident, text, json.dumps(metadata), time.time())
        )
        conn.commit()
        conn.close()

    def search_short_term(self, query: str, limit: int = 5, relevance_cutoff: float = 0.0) -> List[Dict[str, Any]]:
        """
        Simple text-based or embedding-based search in short-term memory with optional relevance cutoff.
        """
        if self.use_mem0 and hasattr(self, "mem0_client"):
            results = self.mem0_client.search(query=query, limit=limit)
            # Filter by score
            filtered = [r for r in results if r.get("score", 1.0) >= relevance_cutoff]
            return filtered

        elif self.use_rag and hasattr(self, "chroma_col"):
            resp = self.chroma_col.query(query_texts=query, n_results=limit)
            found = []
            for i in range(len(resp["ids"][0])):
                distance = resp["distances"][0][i]
                # Keep if distance is within the cutoff
                if distance <= (1.0 - relevance_cutoff):
                    found.append({
                        "id": resp["ids"][0][i],
                        "text": resp["documents"][0][i],
                        "metadata": resp["metadatas"][0][i],
                        "score": distance
                    })
            return found

        else:
            # Local fallback
            conn = sqlite3.connect(self.short_db)
            c = conn.cursor()
            rows = c.execute(
                "SELECT id, content, meta, created_at FROM short_mem WHERE content LIKE ? LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()
            conn.close()

            results = []
            for r in rows:
                results.append({
                    "id": r[0],
                    "content": r[1],
                    "meta": json.loads(r[2] or "{}"),
                    "created_at": r[3]
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
        metadata = self._process_quality_metrics(
            metadata, completeness, relevance, clarity,
            accuracy, weights, evaluator_quality
        )
        
        # Rest of existing store_long_term code remains unchanged
        ident = str(time.time_ns())
        meta_str = json.dumps(metadata)
        created = time.time()

        conn = sqlite3.connect(self.long_db)
        conn.execute(
            "INSERT INTO long_mem (id, content, meta, created_at) VALUES (?,?,?,?)",
            (ident, text, meta_str, created)
        )
        conn.commit()
        conn.close()

        if self.use_mem0 and hasattr(self, "mem0_client"):
            self.mem0_client.add(text, metadata=metadata)
        elif self.use_rag and hasattr(self, "chroma_col"):
            self.chroma_col.add(
                documents=[text],
                metadatas=[metadata],
                ids=[ident]
            )

    def search_long_term(
        self, 
        query: str, 
        limit: int = 5, 
        relevance_cutoff: float = 0.0,
        min_quality: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Search long-term memory with optional quality filter"""
        logger.info(f"Searching long memory for: {query}")
        logger.info(f"Min quality: {min_quality}")
        
        results = []
        
        # Get initial results using existing logic
        if self.use_mem0 and hasattr(self, "mem0_client"):
            results = self.mem0_client.search(query=query, limit=limit)
        elif self.use_rag and hasattr(self, "chroma_col"):
            resp = self.chroma_col.query(query_texts=query, n_results=limit)
            found = []
            for i in range(len(resp["ids"][0])):
                distance = resp["distances"][0][i]
                if distance <= (1.0 - relevance_cutoff):
                    found.append({
                        "id": resp["ids"][0][i],
                        "text": resp["documents"][0][i],
                        "metadata": resp["metadatas"][0][i],
                        "score": distance
                    })
            results = found
        else:
            # Local fallback
            conn = sqlite3.connect(self.long_db)
            c = conn.cursor()
            rows = c.execute(
                "SELECT id, content, meta, created_at FROM long_mem WHERE content LIKE ? LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()
            conn.close()

            found = []
            for row in rows:
                found.append({
                    "id": row[0],
                    "text": row[1],
                    "metadata": json.loads(row[2] or "{}"),
                    "created_at": row[3]
                })
            results = found

        # Filter by quality if needed
        if min_quality > 0:
            logger.info(f"Found {len(results)} initial results")
            results = [
                r for r in results 
                if r.get("metadata", {}).get("quality", 0.0) >= min_quality
            ]
            logger.info(f"After quality filter: {len(results)} results")
        
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

    def search_user_memory(self, user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        If mem0 is used, pass user_id in. Otherwise fallback to local filter on user in metadata.
        """
        if self.use_mem0 and hasattr(self, "mem0_client"):
            return self.mem0_client.search(query=query, limit=limit, user_id=user_id)
        else:
            hits = self.search_long_term(query, limit=20)
            filtered = []
            for h in hits:
                meta = h.get("metadata", {})
                if meta.get("user_id") == user_id:
                    filtered.append(h)
            return filtered[:limit]

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
        agent_name: str = "Agent",
        quality_score: float = 0.0,
        threshold: float = 0.7
    ):
        """
        Example method. Called right after the agent finishes a step:
         1) Always store content in short-term memory
         2) If quality >= threshold, store in long-term memory
        """
        metadata = {
            "agent": agent_name, 
            "quality": quality_score,  # Store quality in metadata
            "score": quality_score
        }
        
        self.store_short_term(
            text=content,
            metadata=metadata
        )
        if quality_score >= threshold:
            self.store_long_term(
                text=content,
                metadata=metadata
            )

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
        into a single text block. 
        """
        q = (task_descr + " " + additional).strip()

        lines = []

        # STM
        stm_hits = self.search_short_term(q, limit=max_items)
        if stm_hits:
            lines.append("ShortTerm context:")
            for h in stm_hits:
                lines.append(f"  - {h['content'][:150]}")

        # LTM
        ltm_hits = self.search_long_term(q, limit=max_items)
        if ltm_hits:
            lines.append("LongTerm context:")
            for h in ltm_hits:
                snippet = h.get("text", "")[:150]
                lines.append(f"  - {snippet}")

        # Entities
        entity_hits = self.search_entity(q, limit=max_items)
        if entity_hits:
            lines.append("Entities found:")
            for e in entity_hits:
                snippet = e.get("text", "")[:150]
                lines.append(f"  - {snippet}")

        # If we have a user, fetch user context
        if user_id:
            user_stuff = self.search_user_memory(user_id, q, limit=max_items)
            if user_stuff:
                lines.append(f"User {user_id} context:")
                for us in user_stuff:
                    snippet = us.get("text", "") or us.get("content", "")
                    lines.append(f"  - {snippet[:150]}")

        return "\n".join(lines)

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
            # Use OpenAI client from main.py
            from ..main import client
            
            response = client.chat.completions.create(
                model=llm or "gpt-4o",
                messages=[{
                    "role": "user", 
                    "content": custom_prompt or default_prompt
                }],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
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
