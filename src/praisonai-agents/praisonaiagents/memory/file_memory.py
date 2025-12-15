"""
File-based Memory System for PraisonAI Agents.

Zero-dependency memory implementation using JSON files.
Provides short-term, long-term, entity, and episodic memory
without requiring any external packages.

Storage Structure:
    .praison/memory/{user_id}/
    ├── config.json           # Memory configuration
    ├── short_term.json       # Rolling buffer (recent context)
    ├── long_term.json        # Persistent facts/knowledge
    ├── entities.json         # Named entities
    ├── episodic/             # Date-based memories
    │   └── {date}.json
    └── summaries.json        # LLM-generated summaries
"""

import json
import time
import fcntl
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class MemoryItem:
    """A single memory item."""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    importance: float = 0.5  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryItem':
        return cls(**data)


@dataclass
class EntityItem:
    """An entity memory item (person, place, concept)."""
    id: str
    name: str
    entity_type: str  # person, place, organization, concept, etc.
    attributes: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Dict[str, str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntityItem':
        return cls(**data)


class FileMemory:
    """
    Zero-dependency file-based memory system.
    
    Uses JSON files for persistence with support for:
    - Short-term memory (rolling buffer)
    - Long-term memory (persistent facts)
    - Entity memory (people, places, concepts)
    - Episodic memory (date-based interactions)
    - Memory summarization (optional, requires LLM)
    
    Example:
        ```python
        memory = FileMemory(user_id="user123")
        
        # Store short-term memory
        memory.add_short_term("User prefers dark mode")
        
        # Store long-term memory
        memory.add_long_term("User's name is John", importance=0.9)
        
        # Store entity
        memory.add_entity("John", "person", {"role": "developer"})
        
        # Search memories
        results = memory.search("John")
        
        # Get context for LLM
        context = memory.get_context(query="What does John prefer?")
        ```
    """
    
    DEFAULT_CONFIG = {
        "short_term_limit": 100,      # Max items in short-term memory
        "long_term_limit": 1000,      # Max items in long-term memory
        "episodic_retention_days": 30, # Days to keep episodic memories
        "enable_summarization": False, # Requires LLM
        "summarization_threshold": 50, # Summarize after N items
        "importance_threshold": 0.7,   # Min importance for long-term
        "auto_promote": True,          # Auto-promote important short-term to long-term
    }
    
    def __init__(
        self,
        user_id: str = "default",
        base_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        verbose: int = 0
    ):
        """
        Initialize FileMemory.
        
        Args:
            user_id: Unique identifier for the user/session
            base_path: Base directory for memory storage (default: .praison/memory)
            config: Configuration overrides
            verbose: Verbosity level (0=quiet, 1=info, 2+=debug)
        """
        self.user_id = user_id
        self.verbose = verbose
        
        # Set up paths
        if base_path:
            self.base_path = Path(base_path)
        else:
            self.base_path = Path(".praison/memory")
        
        self.user_path = self.base_path / user_id
        self.episodic_path = self.user_path / "episodic"
        
        # Create directories
        self.user_path.mkdir(parents=True, exist_ok=True)
        self.episodic_path.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.config_file = self.user_path / "config.json"
        self.short_term_file = self.user_path / "short_term.json"
        self.long_term_file = self.user_path / "long_term.json"
        self.entities_file = self.user_path / "entities.json"
        self.summaries_file = self.user_path / "summaries.json"
        
        # Load or create config
        self.config = self._load_config(config)
        
        # Initialize memory stores
        self._short_term: List[MemoryItem] = []
        self._long_term: List[MemoryItem] = []
        self._entities: Dict[str, EntityItem] = {}
        self._summaries: List[Dict[str, Any]] = []
        
        # Load existing data
        self._load_all()
        
        self._log(f"FileMemory initialized for user '{user_id}' at {self.user_path}")
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message if verbose."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _generate_id(self, content: str) -> str:
        """Generate a unique ID for content."""
        timestamp = str(time.time())
        hash_input = f"{content}{timestamp}{self.user_id}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    # -------------------------------------------------------------------------
    #                          File Operations
    # -------------------------------------------------------------------------
    
    def _read_json(self, filepath: Path, default: Any = None) -> Any:
        """Read JSON file with file locking."""
        if not filepath.exists():
            return default if default is not None else []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, IOError) as e:
            self._log(f"Error reading {filepath}: {e}", logging.WARNING)
            return default if default is not None else []
    
    def _write_json(self, filepath: Path, data: Any) -> bool:
        """Write JSON file with file locking."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except IOError as e:
            self._log(f"Error writing {filepath}: {e}", logging.ERROR)
            return False
    
    def _load_config(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Load or create configuration."""
        config = self.DEFAULT_CONFIG.copy()
        
        # Load existing config
        if self.config_file.exists():
            saved_config = self._read_json(self.config_file, {})
            config.update(saved_config)
        
        # Apply overrides
        if overrides:
            config.update(overrides)
        
        # Save config
        self._write_json(self.config_file, config)
        
        return config
    
    def _load_all(self):
        """Load all memory data from files."""
        # Load short-term
        short_data = self._read_json(self.short_term_file, [])
        self._short_term = [MemoryItem.from_dict(item) for item in short_data]
        
        # Load long-term
        long_data = self._read_json(self.long_term_file, [])
        self._long_term = [MemoryItem.from_dict(item) for item in long_data]
        
        # Load entities
        entities_data = self._read_json(self.entities_file, {})
        self._entities = {k: EntityItem.from_dict(v) for k, v in entities_data.items()}
        
        # Load summaries
        self._summaries = self._read_json(self.summaries_file, [])
        
        self._log(f"Loaded {len(self._short_term)} short-term, {len(self._long_term)} long-term, {len(self._entities)} entities")
    
    def _save_short_term(self):
        """Save short-term memory to file."""
        data = [item.to_dict() for item in self._short_term]
        self._write_json(self.short_term_file, data)
    
    def _save_long_term(self):
        """Save long-term memory to file."""
        data = [item.to_dict() for item in self._long_term]
        self._write_json(self.long_term_file, data)
    
    def _save_entities(self):
        """Save entities to file."""
        data = {k: v.to_dict() for k, v in self._entities.items()}
        self._write_json(self.entities_file, data)
    
    def _save_summaries(self):
        """Save summaries to file."""
        self._write_json(self.summaries_file, self._summaries)
    
    # -------------------------------------------------------------------------
    #                          Short-Term Memory
    # -------------------------------------------------------------------------
    
    def add_short_term(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5
    ) -> str:
        """
        Add item to short-term memory.
        
        Args:
            content: The memory content
            metadata: Optional metadata dict
            importance: Importance score (0.0 to 1.0)
            
        Returns:
            The generated memory ID
        """
        item = MemoryItem(
            id=self._generate_id(content),
            content=content,
            metadata=metadata or {},
            importance=importance
        )
        
        self._short_term.append(item)
        
        # Enforce limit (rolling buffer)
        limit = self.config["short_term_limit"]
        if len(self._short_term) > limit:
            # Before removing, check if should promote to long-term
            if self.config["auto_promote"]:
                self._auto_promote_to_long_term()
            
            # Remove oldest items
            self._short_term = self._short_term[-limit:]
        
        self._save_short_term()
        self._log(f"Added short-term memory: {content[:50]}...")
        
        return item.id
    
    def get_short_term(self, limit: Optional[int] = None) -> List[MemoryItem]:
        """Get short-term memories, most recent first."""
        items = list(reversed(self._short_term))
        if limit:
            items = items[:limit]
        return items
    
    def _auto_promote_to_long_term(self):
        """Promote high-importance short-term memories to long-term."""
        threshold = self.config["importance_threshold"]
        promoted = []
        
        for item in self._short_term:
            if item.importance >= threshold:
                # Check if not already in long-term
                existing_ids = {m.id for m in self._long_term}
                if item.id not in existing_ids:
                    self._long_term.append(item)
                    promoted.append(item.id)
        
        if promoted:
            self._save_long_term()
            self._log(f"Auto-promoted {len(promoted)} items to long-term memory")
    
    # -------------------------------------------------------------------------
    #                          Long-Term Memory
    # -------------------------------------------------------------------------
    
    def add_long_term(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.8
    ) -> str:
        """
        Add item to long-term memory.
        
        Args:
            content: The memory content
            metadata: Optional metadata dict
            importance: Importance score (0.0 to 1.0)
            
        Returns:
            The generated memory ID
        """
        item = MemoryItem(
            id=self._generate_id(content),
            content=content,
            metadata=metadata or {},
            importance=importance
        )
        
        self._long_term.append(item)
        
        # Enforce limit
        limit = self.config["long_term_limit"]
        if len(self._long_term) > limit:
            # Remove lowest importance items
            self._long_term.sort(key=lambda x: x.importance, reverse=True)
            self._long_term = self._long_term[:limit]
        
        self._save_long_term()
        self._log(f"Added long-term memory: {content[:50]}...")
        
        return item.id
    
    def get_long_term(self, limit: Optional[int] = None) -> List[MemoryItem]:
        """Get long-term memories, sorted by importance."""
        items = sorted(self._long_term, key=lambda x: x.importance, reverse=True)
        if limit:
            items = items[:limit]
        return items
    
    # -------------------------------------------------------------------------
    #                          Entity Memory
    # -------------------------------------------------------------------------
    
    def add_entity(
        self,
        name: str,
        entity_type: str,
        attributes: Optional[Dict[str, Any]] = None,
        relationships: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Add or update an entity.
        
        Args:
            name: Entity name
            entity_type: Type (person, place, organization, concept)
            attributes: Entity attributes
            relationships: List of relationships [{type, target}]
            
        Returns:
            The entity ID
        """
        entity_id = self._generate_id(f"{name}:{entity_type}")
        
        # Check if entity exists
        existing = self._find_entity_by_name(name, entity_type)
        if existing:
            # Update existing entity
            existing.attributes.update(attributes or {})
            if relationships:
                existing.relationships.extend(relationships)
            existing.updated_at = time.time()
            entity_id = existing.id
        else:
            # Create new entity
            entity = EntityItem(
                id=entity_id,
                name=name,
                entity_type=entity_type,
                attributes=attributes or {},
                relationships=relationships or []
            )
            self._entities[entity_id] = entity
        
        self._save_entities()
        self._log(f"Added/updated entity: {name} ({entity_type})")
        
        return entity_id
    
    def get_entity(self, name: str, entity_type: Optional[str] = None) -> Optional[EntityItem]:
        """Get entity by name and optionally type."""
        return self._find_entity_by_name(name, entity_type)
    
    def get_all_entities(self, entity_type: Optional[str] = None) -> List[EntityItem]:
        """Get all entities, optionally filtered by type."""
        entities = list(self._entities.values())
        if entity_type:
            entities = [e for e in entities if e.entity_type == entity_type]
        return entities
    
    def _find_entity_by_name(self, name: str, entity_type: Optional[str] = None) -> Optional[EntityItem]:
        """Find entity by name."""
        name_lower = name.lower()
        for entity in self._entities.values():
            if entity.name.lower() == name_lower:
                if entity_type is None or entity.entity_type == entity_type:
                    return entity
        return None
    
    # -------------------------------------------------------------------------
    #                          Episodic Memory
    # -------------------------------------------------------------------------
    
    def add_episodic(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        date: Optional[str] = None
    ) -> str:
        """
        Add episodic memory (date-based).
        
        Args:
            content: The memory content
            metadata: Optional metadata
            date: Date string (YYYY-MM-DD), defaults to today
            
        Returns:
            The memory ID
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        episodic_file = self.episodic_path / f"{date}.json"
        
        # Load existing episodic memories for this date
        episodes = self._read_json(episodic_file, [])
        
        # Create new item
        item = MemoryItem(
            id=self._generate_id(content),
            content=content,
            metadata=metadata or {}
        )
        
        episodes.append(item.to_dict())
        self._write_json(episodic_file, episodes)
        
        self._log(f"Added episodic memory for {date}: {content[:50]}...")
        
        return item.id
    
    def get_episodic(
        self,
        date: Optional[str] = None,
        days_back: int = 7
    ) -> List[MemoryItem]:
        """
        Get episodic memories.
        
        Args:
            date: Specific date (YYYY-MM-DD), or None for recent
            days_back: Number of days to look back if date is None
            
        Returns:
            List of episodic memories
        """
        if date:
            episodic_file = self.episodic_path / f"{date}.json"
            data = self._read_json(episodic_file, [])
            return [MemoryItem.from_dict(item) for item in data]
        
        # Get memories from last N days
        all_episodes = []
        for i in range(days_back):
            check_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            episodic_file = self.episodic_path / f"{check_date}.json"
            if episodic_file.exists():
                data = self._read_json(episodic_file, [])
                all_episodes.extend([MemoryItem.from_dict(item) for item in data])
        
        return all_episodes
    
    def cleanup_episodic(self):
        """Remove old episodic memories based on retention policy."""
        retention_days = self.config["episodic_retention_days"]
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        removed = 0
        for episodic_file in self.episodic_path.glob("*.json"):
            try:
                file_date = datetime.strptime(episodic_file.stem, "%Y-%m-%d")
                if file_date < cutoff_date:
                    episodic_file.unlink()
                    removed += 1
            except ValueError:
                continue
        
        if removed:
            self._log(f"Cleaned up {removed} old episodic memory files")
        
        return removed
    
    # -------------------------------------------------------------------------
    #                          Search & Retrieval
    # -------------------------------------------------------------------------
    
    def search(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search across all memory types.
        
        Args:
            query: Search query
            memory_types: List of types to search (short_term, long_term, entity, episodic)
            limit: Maximum results
            
        Returns:
            List of matching memories with scores
        """
        if memory_types is None:
            memory_types = ["short_term", "long_term", "entity", "episodic"]
        
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        def score_match(text: str) -> float:
            """Simple relevance scoring."""
            text_lower = text.lower()
            
            # Exact match
            if query_lower in text_lower:
                return 1.0
            
            # Word overlap
            text_words = set(text_lower.split())
            overlap = len(query_words & text_words)
            if overlap > 0:
                return overlap / len(query_words) * 0.8
            
            return 0.0
        
        # Search short-term
        if "short_term" in memory_types:
            for item in self._short_term:
                score = score_match(item.content)
                if score > 0:
                    results.append({
                        "type": "short_term",
                        "item": item.to_dict(),
                        "score": score * item.importance
                    })
        
        # Search long-term
        if "long_term" in memory_types:
            for item in self._long_term:
                score = score_match(item.content)
                if score > 0:
                    results.append({
                        "type": "long_term",
                        "item": item.to_dict(),
                        "score": score * item.importance
                    })
        
        # Search entities
        if "entity" in memory_types:
            for entity in self._entities.values():
                score = max(
                    score_match(entity.name),
                    score_match(str(entity.attributes))
                )
                if score > 0:
                    results.append({
                        "type": "entity",
                        "item": entity.to_dict(),
                        "score": score
                    })
        
        # Search episodic (recent only)
        if "episodic" in memory_types:
            episodes = self.get_episodic(days_back=7)
            for item in episodes:
                score = score_match(item.content)
                if score > 0:
                    results.append({
                        "type": "episodic",
                        "item": item.to_dict(),
                        "score": score
                    })
        
        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def get_context(
        self,
        query: Optional[str] = None,
        include_short_term: bool = True,
        include_long_term: bool = True,
        include_entities: bool = True,
        include_episodic: bool = False,
        max_tokens: int = 2000
    ) -> str:
        """
        Build context string for LLM from memories.
        
        Args:
            query: Optional query to focus context
            include_short_term: Include short-term memories
            include_long_term: Include long-term memories
            include_entities: Include entity information
            include_episodic: Include recent episodic memories
            max_tokens: Approximate max tokens (chars / 4)
            
        Returns:
            Formatted context string
        """
        context_parts = []
        char_limit = max_tokens * 4  # Rough estimate
        
        # If query provided, use search
        if query:
            memory_types = []
            if include_short_term:
                memory_types.append("short_term")
            if include_long_term:
                memory_types.append("long_term")
            if include_entities:
                memory_types.append("entity")
            if include_episodic:
                memory_types.append("episodic")
            
            results = self.search(query, memory_types, limit=20)
            
            if results:
                context_parts.append("## Relevant Memories")
                for r in results:
                    if r["type"] == "entity":
                        item = r["item"]
                        context_parts.append(f"- {item['name']} ({item['entity_type']}): {item['attributes']}")
                    else:
                        context_parts.append(f"- {r['item']['content']}")
        else:
            # No query - include recent/important memories
            if include_long_term:
                long_term = self.get_long_term(limit=10)
                if long_term:
                    context_parts.append("## Important Facts")
                    for item in long_term:
                        context_parts.append(f"- {item.content}")
            
            if include_entities:
                entities = self.get_all_entities()
                if entities:
                    context_parts.append("## Known Entities")
                    for entity in entities[:10]:
                        attrs = ", ".join(f"{k}={v}" for k, v in entity.attributes.items())
                        context_parts.append(f"- {entity.name} ({entity.entity_type}): {attrs}")
            
            if include_short_term:
                short_term = self.get_short_term(limit=10)
                if short_term:
                    context_parts.append("## Recent Context")
                    for item in short_term:
                        context_parts.append(f"- {item.content}")
            
            if include_episodic:
                episodes = self.get_episodic(days_back=3)
                if episodes:
                    context_parts.append("## Recent Interactions")
                    for item in episodes[:10]:
                        context_parts.append(f"- {item.content}")
        
        # Join and truncate
        context = "\n".join(context_parts)
        if len(context) > char_limit:
            context = context[:char_limit] + "\n... (truncated)"
        
        return context
    
    # -------------------------------------------------------------------------
    #                          Summarization
    # -------------------------------------------------------------------------
    
    def add_summary(
        self,
        summary: str,
        source_type: str,
        source_count: int,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Add a summary (typically LLM-generated).
        
        Args:
            summary: The summary text
            source_type: What was summarized (short_term, episodic, etc.)
            source_count: Number of items summarized
            metadata: Optional metadata
        """
        self._summaries.append({
            "id": self._generate_id(summary),
            "summary": summary,
            "source_type": source_type,
            "source_count": source_count,
            "metadata": metadata or {},
            "created_at": time.time()
        })
        
        self._save_summaries()
        self._log(f"Added summary for {source_count} {source_type} items")
    
    def get_summaries(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent summaries."""
        return list(reversed(self._summaries))[:limit]
    
    # -------------------------------------------------------------------------
    #                          Utility Methods
    # -------------------------------------------------------------------------
    
    def clear_short_term(self):
        """Clear all short-term memory."""
        self._short_term = []
        self._save_short_term()
        self._log("Cleared short-term memory")
    
    def clear_all(self):
        """Clear all memory for this user."""
        self._short_term = []
        self._long_term = []
        self._entities = {}
        self._summaries = []
        
        self._save_short_term()
        self._save_long_term()
        self._save_entities()
        self._save_summaries()
        
        # Clear episodic
        for f in self.episodic_path.glob("*.json"):
            f.unlink()
        
        self._log("Cleared all memory")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        episodic_count = sum(1 for _ in self.episodic_path.glob("*.json"))
        
        return {
            "user_id": self.user_id,
            "short_term_count": len(self._short_term),
            "long_term_count": len(self._long_term),
            "entity_count": len(self._entities),
            "episodic_days": episodic_count,
            "summary_count": len(self._summaries),
            "storage_path": str(self.user_path)
        }
    
    def export(self) -> Dict[str, Any]:
        """Export all memory data."""
        return {
            "user_id": self.user_id,
            "config": self.config,
            "short_term": [item.to_dict() for item in self._short_term],
            "long_term": [item.to_dict() for item in self._long_term],
            "entities": {k: v.to_dict() for k, v in self._entities.items()},
            "summaries": self._summaries,
            "exported_at": time.time()
        }
    
    def import_data(self, data: Dict[str, Any]):
        """Import memory data from export."""
        if "short_term" in data:
            self._short_term = [MemoryItem.from_dict(item) for item in data["short_term"]]
            self._save_short_term()
        
        if "long_term" in data:
            self._long_term = [MemoryItem.from_dict(item) for item in data["long_term"]]
            self._save_long_term()
        
        if "entities" in data:
            self._entities = {k: EntityItem.from_dict(v) for k, v in data["entities"].items()}
            self._save_entities()
        
        if "summaries" in data:
            self._summaries = data["summaries"]
            self._save_summaries()
        
        self._log("Imported memory data")


# Convenience function for simple usage
def create_memory(
    user_id: str = "default",
    **kwargs
) -> FileMemory:
    """
    Create a FileMemory instance.
    
    Args:
        user_id: User identifier
        **kwargs: Additional configuration
        
    Returns:
        FileMemory instance
    """
    return FileMemory(user_id=user_id, **kwargs)
