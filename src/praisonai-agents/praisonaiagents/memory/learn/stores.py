"""
Learning Stores - Storage backends for different learning capabilities.

Each store handles a specific type of learning data:
- PersonaStore: User preferences and profile
- InsightStore: Observations and learnings
- ThreadStore: Session/conversation context
- PatternStore: Reusable knowledge patterns
- DecisionStore: Decision logging
- FeedbackStore: Outcome signals
- ImprovementStore: Self-improvement proposals
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

# DRY: Import base storage for thread safety
from ...storage.base import BaseJSONStore

if TYPE_CHECKING:
    from ...storage.protocols import StorageBackendProtocol


@dataclass
class LearnEntry:
    """Base entry for all learning stores."""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    use_count: int = 0
    last_used: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "use_count": self.use_count,
            "last_used": self.last_used,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearnEntry":
        return cls(
            id=data["id"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            use_count=data.get("use_count", 0),
            last_used=data.get("last_used"),
        )


class BaseStore(ABC):
    """
    Abstract base class for learning stores.
    
    DRY: Uses BaseJSONStore internally for thread-safe, file-locked storage.
    Supports pluggable backends (file, sqlite, etc.) via the backend parameter.
    """
    
    def __init__(
        self,
        store_path: Optional[str] = None,
        user_id: Optional[str] = None,
        scope: str = "private",
        backend: Optional["StorageBackendProtocol"] = None,
        max_entries: int = 0,
        retention_days: int = 0,
    ):
        self.user_id = user_id or "default"
        self.scope = scope
        self._backend = backend
        # Retention policy: 0 disables (permissive default — backward-compatible)
        self.max_entries = max_entries or 0
        self.retention_days = retention_days or 0
        self.store_path = store_path or self._default_path()
        self._entries: Dict[str, LearnEntry] = {}
        self._was_updated: bool = False
        
        # DRY: Use BaseJSONStore for thread-safe storage
        # Fall back to FILE backend if connection fails (e.g., Redis unavailable)
        try:
            self._store = BaseJSONStore(
                storage_path=self.store_path,
                backend=backend,
            )
        except Exception as e:
            import logging
            logging.warning(f"Failed to connect to backend: {e}. Falling back to FILE.")
            self._backend = None
            self._store = BaseJSONStore(
                storage_path=self.store_path,
                backend=None,
            )
        self._load()
    
    @property
    @abstractmethod
    def store_name(self) -> str:
        """Name of the store (used for file naming)."""
        pass
    
    @property
    def was_updated(self) -> bool:
        """Whether this store has been modified since last reset."""
        return self._was_updated
    
    def reset_updated(self) -> None:
        """Reset the was_updated flag."""
        self._was_updated = False
    
    def _default_path(self) -> str:
        """Default storage path (uses centralized paths - DRY)."""
        from ...paths import get_learn_dir, ensure_dir
        base = get_learn_dir() / self.scope / self.user_id
        ensure_dir(base)
        return str(base / f"{self.store_name}.json")
    
    def _load(self) -> None:
        """Load entries from storage using BaseJSONStore."""
        data = self._store.load()
        self._entries = {
            k: LearnEntry.from_dict(v) for k, v in data.items()
        }
    
    def _save(self) -> None:
        """Save entries to storage using BaseJSONStore."""
        self._store.save({k: v.to_dict() for k, v in self._entries.items()})
    
    def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> LearnEntry:
        """Add a new entry with deduplication.
        
        Checks for exact content matches to prevent duplicate learnings.
        If a duplicate is found, returns the existing entry instead of creating a new one.
        """
        # Deduplication: Check for exact content match
        content_normalized = content.strip().lower()
        for existing_entry in self._entries.values():
            if existing_entry.content.strip().lower() == content_normalized:
                # Update metadata if provided, but don't create duplicate
                if metadata:
                    existing_entry.metadata.update(metadata)
                    existing_entry.updated_at = datetime.utcnow().isoformat()
                    self._save()
                    self._was_updated = True
                return existing_entry
        
        # No duplicate found, create new entry
        entry_id = f"{self.store_name}_{len(self._entries)}_{datetime.utcnow().timestamp()}"
        entry = LearnEntry(
            id=entry_id,
            content=content,
            metadata=metadata or {},
        )
        self._entries[entry_id] = entry
        # Bounded retention: prune stale/excess entries on write (no-op if unconfigured)
        self.prune(save=False)
        self._save()
        self._was_updated = True
        return entry
    
    def _touch(self, entries: List[LearnEntry]) -> None:
        """Record usage telemetry for retrieved entries.
        
        Bumps use_count/last_used so value is observable and retention is
        usage-aware. Persisted only when entries were actually touched.
        """
        if not entries:
            return
        now = datetime.utcnow().isoformat()
        for entry in entries:
            entry.use_count += 1
            entry.last_used = now
        self._save()
    
    def get(self, entry_id: str) -> Optional[LearnEntry]:
        """Get entry by ID."""
        return self._entries.get(entry_id)
    
    def search(self, query: str, limit: int = 10) -> List[LearnEntry]:
        """Simple text search (can be overridden for semantic search)."""
        query_lower = query.lower()
        results = [
            entry for entry in self._entries.values()
            if query_lower in entry.content.lower()
        ]
        results = results[:limit]
        self._touch(results)
        return results
    
    def list_all(self, limit: int = 100) -> List[LearnEntry]:
        """List all entries."""
        entries = list(self._entries.values())
        entries.sort(key=lambda x: x.updated_at, reverse=True)
        entries = entries[:limit]
        self._touch(entries)
        return entries
    
    def update(self, entry_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[LearnEntry]:
        """Update an existing entry."""
        if entry_id not in self._entries:
            return None
        entry = self._entries[entry_id]
        entry.content = content
        if metadata:
            entry.metadata.update(metadata)
        entry.updated_at = datetime.utcnow().isoformat()
        self._save()
        self._was_updated = True
        return entry
    
    def delete(self, entry_id: str) -> bool:
        """Delete an entry."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._save()
            self._was_updated = True
            return True
        return False
    
    def clear(self) -> int:
        """Clear all entries."""
        count = len(self._entries)
        self._entries = {}
        self._save()
        self._was_updated = True
        return count
    
    def _archive_path(self) -> Path:
        """Path to the recoverable archive file for this store."""
        return Path(self.store_path).with_suffix(".archive.json")
    
    def _archive(self, entries: List[LearnEntry]) -> None:
        """Append evicted entries to a recoverable archive (never hard-delete)."""
        if not entries:
            return
        try:
            import json
            archive_path = self._archive_path()
            existing: List[Dict[str, Any]] = []
            if archive_path.exists():
                try:
                    with open(archive_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            existing.extend(e.to_dict() for e in entries)
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except Exception as e:
            import logging
            logging.warning(f"Failed to archive pruned entries: {e}")
    
    def _is_stale(self, entry: LearnEntry, now: datetime) -> bool:
        """Whether an entry exceeds the retention window (usage-driven, deterministic)."""
        if self.retention_days <= 0:
            return False
        reference = entry.last_used or entry.updated_at or entry.created_at
        try:
            ref_dt = datetime.fromisoformat(reference)
        except (ValueError, TypeError):
            return False
        age_days = (now - ref_dt).total_seconds() / 86400.0
        return age_days > self.retention_days
    
    def prune(self, save: bool = True) -> int:
        """Archive stale and least-used/oldest excess entries.
        
        Deterministic, usage-driven retention (no LLM judgment):
        - Entries unused beyond ``retention_days`` are archived as stale.
        - When more than ``max_entries`` remain, the least-used (then oldest)
          are archived until the cap is met.
        
        Archival is recoverable (entries moved to a ``.archive.json`` sidecar);
        never a silent hard-delete. Returns the number of entries archived.
        No-op (returns 0) when neither limit is configured — backward-compatible.
        """
        if self.max_entries <= 0 and self.retention_days <= 0:
            return 0
        
        now = datetime.utcnow()
        evicted: List[LearnEntry] = []
        
        # 1. Staleness: archive entries beyond the retention window
        if self.retention_days > 0:
            for entry_id, entry in list(self._entries.items()):
                if self._is_stale(entry, now):
                    evicted.append(self._entries.pop(entry_id))
        
        # 2. Cap: archive least-used (then oldest) beyond max_entries
        if self.max_entries > 0 and len(self._entries) > self.max_entries:
            remaining = sorted(
                self._entries.values(),
                key=lambda e: (e.use_count, e.last_used or "", e.created_at),
            )
            overflow = len(self._entries) - self.max_entries
            for entry in remaining[:overflow]:
                evicted.append(self._entries.pop(entry.id))
        
        if evicted:
            self._archive(evicted)
            self._was_updated = True
            if save:
                self._save()
        return len(evicted)


class PersonaStore(BaseStore):
    """Store for user preferences and profile information."""
    
    @property
    def store_name(self) -> str:
        return "persona"
    
    def add_preference(self, preference: str, category: str = "general") -> LearnEntry:
        """Add a user preference."""
        return self.add(preference, {"category": category, "type": "preference"})
    
    def add_profile(self, profile_data: str, aspect: str = "general") -> LearnEntry:
        """Add profile information."""
        return self.add(profile_data, {"aspect": aspect, "type": "profile"})


class InsightStore(BaseStore):
    """Store for observations and learnings."""
    
    @property
    def store_name(self) -> str:
        return "insights"
    
    def add_insight(self, insight: str, source: str = "interaction") -> LearnEntry:
        """Add an insight."""
        return self.add(insight, {"source": source, "type": "insight"})
    
    def add_observation(self, observation: str, context: str = "") -> LearnEntry:
        """Add an observation."""
        return self.add(observation, {"context": context, "type": "observation"})


class ThreadStore(BaseStore):
    """Store for session/conversation context."""
    
    @property
    def store_name(self) -> str:
        return "threads"
    
    def add_thread_summary(self, summary: str, thread_id: str) -> LearnEntry:
        """Add a thread summary."""
        return self.add(summary, {"thread_id": thread_id, "type": "summary"})
    
    def add_context(self, context: str, thread_id: str) -> LearnEntry:
        """Add thread context."""
        return self.add(context, {"thread_id": thread_id, "type": "context"})


class PatternStore(BaseStore):
    """Store for reusable knowledge patterns."""
    
    @property
    def store_name(self) -> str:
        return "patterns"
    
    def add_pattern(self, pattern: str, pattern_type: str = "general") -> LearnEntry:
        """Add a knowledge pattern."""
        return self.add(pattern, {"pattern_type": pattern_type, "type": "pattern"})


class DecisionStore(BaseStore):
    """Store for decision logging."""
    
    @property
    def store_name(self) -> str:
        return "decisions"
    
    def add_decision(
        self,
        decision: str,
        reasoning: str = "",
        outcome: str = "",
    ) -> LearnEntry:
        """Add a decision record."""
        return self.add(decision, {
            "reasoning": reasoning,
            "outcome": outcome,
            "type": "decision",
        })


class FeedbackStore(BaseStore):
    """Store for outcome signals and feedback."""
    
    @property
    def store_name(self) -> str:
        return "feedback"
    
    def add_feedback(
        self,
        feedback: str,
        rating: Optional[int] = None,
        source: str = "user",
    ) -> LearnEntry:
        """Add feedback."""
        metadata = {"source": source, "type": "feedback"}
        if rating is not None:
            metadata["rating"] = rating
        return self.add(feedback, metadata)


class ImprovementStore(BaseStore):
    """Store for self-improvement proposals."""
    
    @property
    def store_name(self) -> str:
        return "improvements"
    
    def add_improvement(
        self,
        proposal: str,
        area: str = "general",
        priority: str = "medium",
    ) -> LearnEntry:
        """Add an improvement proposal."""
        return self.add(proposal, {
            "area": area,
            "priority": priority,
            "type": "improvement",
        })
