"""
Core memory functionality for Memory class.

This module contains the core Memory class definition, initialization,
and quality scoring logic. Split from the main memory.py file for better maintainability.
"""

import json
import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MemoryCoreMixin:
    """Mixin class containing core memory functionality for the Memory class."""

    # -----------------------------------------------------------------------
    # Store helpers
    # -----------------------------------------------------------------------

    def store_short_term(self, content: str, metadata: Optional[Dict] = None,
                         quality_score: Optional[float] = None,
                         user_id: Optional[str] = None, auto_promote: bool = True) -> str:
        """Store content in short-term memory."""
        if not content or not content.strip():
            return ""

        if quality_score is None:
            quality_score = self.compute_quality_score(content, metadata)

        meta = dict(metadata or {})
        if user_id:
            meta["user_id"] = user_id
        meta.setdefault("timestamp", datetime.now().isoformat())
        clean_meta = self._sanitize_metadata(meta)

        memory_id: Optional[str] = None

        if getattr(self, "use_rag", False) and hasattr(self, "stm_collection"):
            try:
                memory_id = self._store_vector_stm(content, clean_meta, quality_score)
            except Exception as exc:
                logging.warning(f"Failed to store in vector STM: {exc}")

        if getattr(self, "use_mongodb", False) and hasattr(self, "stm_collection"):
            try:
                memory_id = self._store_mongodb_stm(content, clean_meta, quality_score)
            except Exception as exc:
                logging.warning(f"Failed to store in MongoDB STM: {exc}")

        try:
            if not memory_id:
                memory_id = self._store_sqlite_stm(content, clean_meta, quality_score)
        except Exception as exc:
            logging.error(f"Failed to store in SQLite STM: {exc}")
            return ""

        if auto_promote and quality_score >= 7.5:
            try:
                self.store_long_term(content, clean_meta, quality_score, user_id)
            except Exception as exc:
                logging.warning(f"Failed to auto-promote to LTM: {exc}")

        self._emit_memory_event("store", "short_term", content, clean_meta)
        return memory_id or ""

    def store_long_term(self, content: str, metadata: Optional[Dict] = None,
                        quality_score: Optional[float] = None,
                        user_id: Optional[str] = None) -> str:
        """Store content in long-term memory."""
        if not content or not content.strip():
            return ""

        if quality_score is None:
            quality_score = self.compute_quality_score(content, metadata)

        if quality_score < 5.0:
            return ""

        meta = dict(metadata or {})
        if user_id:
            meta["user_id"] = user_id
        meta.setdefault("timestamp", datetime.now().isoformat())
        meta.setdefault("promoted_at", datetime.now().isoformat())
        clean_meta = self._sanitize_metadata(meta)

        memory_id: Optional[str] = None

        if getattr(self, "use_rag", False) and hasattr(self, "ltm_collection"):
            try:
                memory_id = self._store_vector_ltm(content, clean_meta, quality_score)
            except Exception as exc:
                logging.warning(f"Failed to store in vector LTM: {exc}")

        if getattr(self, "use_mongodb", False) and hasattr(self, "ltm_collection"):
            try:
                memory_id = self._store_mongodb_ltm(content, clean_meta, quality_score)
            except Exception as exc:
                logging.warning(f"Failed to store in MongoDB LTM: {exc}")

        try:
            if not memory_id:
                memory_id = self._store_sqlite_ltm(content, clean_meta, quality_score)
        except Exception as exc:
            logging.error(f"Failed to store in SQLite LTM: {exc}")
            return ""

        self._emit_memory_event("store", "long_term", content, clean_meta)
        return memory_id or ""

    # -----------------------------------------------------------------------
    # Aggregate / context helpers
    # -----------------------------------------------------------------------

    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Return all stored memories from all active backends."""
        results: List[Dict[str, Any]] = []

        # SQLite STM
        try:
            conn = self._get_stm_conn()
            rows = conn.execute(
                "SELECT id, content, metadata, timestamp, quality_score FROM short_term"
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                try:
                    row_dict["metadata"] = json.loads(row_dict.get("metadata") or "{}")
                except (json.JSONDecodeError, TypeError):
                    row_dict["metadata"] = {}
                row_dict["memory_type"] = "short_term"
                results.append(row_dict)
        except Exception as exc:
            logging.warning(f"get_all_memories: SQLite STM error: {exc}")

        # SQLite LTM
        try:
            conn = self._get_ltm_conn()
            rows = conn.execute(
                "SELECT id, content, metadata, timestamp, quality_score FROM long_term"
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                try:
                    row_dict["metadata"] = json.loads(row_dict.get("metadata") or "{}")
                except (json.JSONDecodeError, TypeError):
                    row_dict["metadata"] = {}
                row_dict["memory_type"] = "long_term"
                results.append(row_dict)
        except Exception as exc:
            logging.warning(f"get_all_memories: SQLite LTM error: {exc}")

        return results

    def get_context(self, query: Optional[str] = None, max_items: int = 5,
                    **kwargs) -> str:
        """Build a context string from the most relevant stored memories."""
        if query:
            memories = (
                self.search_short_term(query, limit=max_items)
                + self.search_long_term(query, limit=max_items)
            )
        else:
            all_mem = self.get_all_memories()
            memories = sorted(
                all_mem,
                key=lambda m: m.get("quality_score", 0.0),
                reverse=True,
            )[:max_items]

        if not memories:
            return ""

        lines = [f"- {m.get('content', '')}" for m in memories if m.get("content")]
        return "Relevant memories:\n" + "\n".join(lines) if lines else ""

    def save_session(self, name: str,
                     conversation_history: Optional[List[Dict[str, Any]]] = None,
                     metadata: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """Persist a conversation session into long-term memory."""
        if not conversation_history:
            return
        for msg in conversation_history:
            content = msg.get("content", "")
            if not content:
                continue
            meta = {**(metadata or {}), "session": name, "role": msg.get("role", "unknown")}
            self.store_long_term(content, meta)

    # -----------------------------------------------------------------------
    # Quality scoring and metadata helpers
    # -----------------------------------------------------------------------

    def compute_quality_score(self, content: str, metadata: Optional[Dict] = None,
                               user_engagement: Optional[Dict] = None,
                               context: Optional[str] = None) -> float:
        """Compute a quality score for memory content (0-10 scale)."""
        if not content or not content.strip():
            return 0.0

        score = 5.0

        content_length = len(content.strip())
        if content_length < 10:
            score -= 2.0
        elif content_length > 500:
            score += 1.0
        elif content_length > 100:
            score += 0.5

        word_count = len(content.split())
        unique_words = len(set(content.lower().split()))
        if word_count > 0:
            score += min((unique_words / word_count) * 2, 1.5)

        if any(m in content for m in (":", "-", "•", "\n", "\t")):
            score += 0.5

        valuable_kw = [
            "definition", "explain", "process", "step", "method", "approach",
            "important", "key", "critical", "remember", "note", "warning",
            "example", "instance", "case", "scenario", "situation",
        ]
        score += min(sum(1 for kw in valuable_kw if kw in content.lower()) * 0.3, 1.0)

        if user_engagement:
            score += min(user_engagement.get("follow_up_questions", 0) * 0.5, 1.0)
            if user_engagement.get("bookmarked"):
                score += 1.0
            if user_engagement.get("shared"):
                score += 0.5

        if context:
            overlap = len(
                set(context.lower().split()).intersection(set(content.lower().split()))
            )
            if overlap and content.split():
                score += min(overlap / len(content.split()), 0.3) * 2

        if metadata:
            importance = metadata.get("importance", "")
            if importance == "high":
                score += 1.5
            elif importance == "medium":
                score += 0.5
            if metadata.get("verified"):
                score += 1.0
            if metadata.get("source") in ("expert", "documentation", "official"):
                score += 1.0

        return round(max(0.0, min(10.0, score)), 2)

    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """Sanitize metadata to ensure it is JSON-serializable."""
        if not isinstance(metadata, dict):
            return {}
        sanitized: Dict[str, Any] = {}
        for key, value in metadata.items():
            str_key = str(key)
            try:
                if value is None or isinstance(value, (str, int, float, bool)):
                    sanitized[str_key] = value
                elif isinstance(value, (list, dict)):
                    json.dumps(value)  # validate serialisability
                    sanitized[str_key] = value
                else:
                    sanitized[str_key] = str(value)
            except (ValueError, TypeError) as exc:
                logging.warning(f"Skipping non-serializable metadata key '{key}': {exc}")
        return sanitized

    def _log_verbose(self, msg: str, level: int = logging.INFO) -> None:
        """Log a message when verbose mode is enabled."""
        if getattr(self, "verbose", 0) >= 1:
            logger.log(level, msg)

    def _emit_memory_event(self, event_type: str, memory_type: str,
                           content: str, metadata: Dict) -> None:
        """Emit a lightweight memory event (no-op placeholder for hook integration)."""
        try:
            _ = {
                "type": event_type,
                "memory_type": memory_type,
                "content_preview": content[:100] + ("..." if len(content) > 100 else ""),
                "metadata": metadata,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as exc:
            logging.debug(f"Failed to emit memory event: {exc}")

    @property
    def learn(self):
        """Lazy-load the LearnManager."""
        if getattr(self, "_learn_manager", None) is None and getattr(self, "_learn_config", None):
            try:
                from praisonaiagents.memory.learn.manager import LearnManager
                self._learn_manager = LearnManager(config=self._learn_config)
            except ImportError:
                logging.warning("LearnManager not available – install learn dependencies")
        return self._learn_manager