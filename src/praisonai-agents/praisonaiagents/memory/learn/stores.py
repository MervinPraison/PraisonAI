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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearnEntry":
        return cls(
            id=data["id"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
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
    ):
        self.user_id = user_id or "default"
        self.scope = scope
        self._backend = backend
        self.store_path = store_path or self._default_path()
        self._entries: Dict[str, LearnEntry] = {}
        
        # DRY: Use BaseJSONStore for thread-safe storage
        self._store = BaseJSONStore(
            storage_path=self.store_path,
            backend=backend,
        )
        self._load()
    
    @property
    @abstractmethod
    def store_name(self) -> str:
        """Name of the store (used for file naming)."""
        pass
    
    def _default_path(self) -> str:
        """Default storage path."""
        base = Path.home() / ".praison" / "learn" / self.scope / self.user_id
        base.mkdir(parents=True, exist_ok=True)
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
        """Add a new entry."""
        entry_id = f"{self.store_name}_{len(self._entries)}_{datetime.utcnow().timestamp()}"
        entry = LearnEntry(
            id=entry_id,
            content=content,
            metadata=metadata or {},
        )
        self._entries[entry_id] = entry
        self._save()
        return entry
    
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
        return results[:limit]
    
    def list_all(self, limit: int = 100) -> List[LearnEntry]:
        """List all entries."""
        entries = list(self._entries.values())
        entries.sort(key=lambda x: x.updated_at, reverse=True)
        return entries[:limit]
    
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
        return entry
    
    def delete(self, entry_id: str) -> bool:
        """Delete an entry."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._save()
            return True
        return False
    
    def clear(self) -> int:
        """Clear all entries."""
        count = len(self._entries)
        self._entries = {}
        self._save()
        return count


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
