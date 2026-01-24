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
import sys
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict, field

# fcntl is Unix-only; on Windows, skip file locking (acceptable for single-process usage)
if sys.platform != 'win32':
    import fcntl
    _HAS_FCNTL = True
else:
    _HAS_FCNTL = False

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
    
    def _emit_memory_event(self, event_type: str, memory_type: str, 
                           content_length: int = 0, query: str = "", 
                           result_count: int = 0, top_score: float = None,
                           metadata: Dict[str, Any] = None):
        """Emit memory trace event if tracing is enabled (zero overhead when disabled)."""
        try:
            from ..trace.context_events import get_context_emitter
            emitter = get_context_emitter()
            if not emitter.enabled:
                return
            agent_name = self.user_id or "unknown"
            if event_type == "store":
                emitter.memory_store(agent_name, memory_type, content_length, metadata)
            elif event_type == "search":
                emitter.memory_search(agent_name, query, result_count, memory_type, top_score)
        except Exception:
            pass  # Silent fail - tracing should never break memory operations
    
    def _generate_id(self, content: str) -> str:
        """Generate a unique ID for content."""
        timestamp = str(time.time())
        hash_input = f"{content}{timestamp}{self.user_id}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    # -------------------------------------------------------------------------
    #                          File Operations
    # -------------------------------------------------------------------------
    
    def _read_json(self, filepath: Path, default: Any = None) -> Any:
        """Read JSON file with file locking (Unix only)."""
        if not filepath.exists():
            return default if default is not None else []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                if _HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    if _HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, IOError) as e:
            self._log(f"Error reading {filepath}: {e}", logging.WARNING)
            return default if default is not None else []

    
    def _write_json(self, filepath: Path, data: Any) -> bool:
        """Write JSON file with file locking (Unix only)."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                if _HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                finally:
                    if _HAS_FCNTL:
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
        
        # Emit trace event
        self._emit_memory_event("store", "short_term", len(content), metadata=metadata)
        
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
        
        # Emit trace event
        self._emit_memory_event("store", "long_term", len(content), metadata=metadata)
        
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
        final_results = results[:limit]
        
        # Emit trace event for search
        top_score = final_results[0]["score"] if final_results else None
        self._emit_memory_event("search", "all", query=query, 
                               result_count=len(final_results), top_score=top_score)
        
        return final_results
    
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
    
    # -------------------------------------------------------------------------
    #                          Selective Deletion
    # -------------------------------------------------------------------------
    
    def delete_short_term(self, memory_id: str) -> bool:
        """
        Delete a specific short-term memory by ID.
        
        Args:
            memory_id: The unique ID of the memory to delete
            
        Returns:
            True if memory was found and deleted, False otherwise
        """
        for i, item in enumerate(self._short_term):
            if item.id == memory_id:
                del self._short_term[i]
                self._save_short_term()
                self._log(f"Deleted short-term memory: {memory_id}")
                return True
        return False
    
    def delete_long_term(self, memory_id: str) -> bool:
        """
        Delete a specific long-term memory by ID.
        
        Args:
            memory_id: The unique ID of the memory to delete
            
        Returns:
            True if memory was found and deleted, False otherwise
        """
        for i, item in enumerate(self._long_term):
            if item.id == memory_id:
                del self._long_term[i]
                self._save_long_term()
                self._log(f"Deleted long-term memory: {memory_id}")
                return True
        return False
    
    def delete_entity(self, name: str) -> bool:
        """
        Delete an entity by name.
        
        Args:
            name: The name of the entity to delete
            
        Returns:
            True if entity was found and deleted, False otherwise
        """
        # Find entity by name using existing helper
        entity = self._find_entity_by_name(name)
        if entity:
            # Delete by entity's ID (which is the dict key)
            if entity.id in self._entities:
                del self._entities[entity.id]
                self._save_entities()
                self._log(f"Deleted entity: {name}")
                return True
        
        # Try direct ID match as fallback (in case name IS the ID)
        if name in self._entities:
            del self._entities[name]
            self._save_entities()
            self._log(f"Deleted entity by ID: {name}")
            return True
        
        return False
    
    def delete_episodic(self, memory_id: str, date: Optional[str] = None) -> bool:
        """
        Delete a specific episodic memory by ID.
        
        Args:
            memory_id: The unique ID of the memory to delete
            date: Optional date string (YYYY-MM-DD) to narrow search
            
        Returns:
            True if memory was found and deleted, False otherwise
        """
        from datetime import datetime, timedelta
        
        # Determine which files to search
        if date:
            dates_to_check = [date]
        else:
            # Check last 30 days
            dates_to_check = [
                (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(30)
            ]
        
        for check_date in dates_to_check:
            episodic_file = self.episodic_path / f"{check_date}.json"
            if episodic_file.exists():
                data = self._read_json(episodic_file, [])
                for i, item in enumerate(data):
                    if item.get("id") == memory_id:
                        del data[i]
                        self._write_json(episodic_file, data)
                        self._log(f"Deleted episodic memory: {memory_id}")
                        return True
        
        return False
    
    def delete_memory(
        self, 
        memory_id: str, 
        memory_type: Optional[str] = None
    ) -> bool:
        """
        Delete a specific memory by ID.
        
        This is the unified deletion method that searches across all memory types.
        Use this when you have a memory ID but don't know its type.
        
        Particularly useful for:
        - Cleaning up image-based memories after processing to free context window
        - Removing outdated or incorrect information
        - Privacy compliance (selective erasure)
        
        Args:
            memory_id: The unique ID of the memory to delete
            memory_type: Optional type hint to narrow search:
                        'short_term', 'long_term', 'entity', 'episodic'
                        If None, searches all types.
            
        Returns:
            True if memory was found and deleted, False otherwise
        
        Example:
            # Delete a specific memory after processing an image
            memory.delete_memory("abc123def456")
            
            # Delete with type hint for faster lookup
            memory.delete_memory("abc123", memory_type="short_term")
        """
        # If type specified, only search that type
        if memory_type == "short_term":
            return self.delete_short_term(memory_id)
        elif memory_type == "long_term":
            return self.delete_long_term(memory_id)
        elif memory_type == "entity":
            return self.delete_entity(memory_id)
        elif memory_type == "episodic":
            return self.delete_episodic(memory_id)
        
        # Search all types
        if self.delete_short_term(memory_id):
            return True
        if self.delete_long_term(memory_id):
            return True
        if self.delete_entity(memory_id):
            return True
        if self.delete_episodic(memory_id):
            return True
        
        return False
    
    def delete_memories(self, memory_ids: List[str]) -> int:
        """
        Delete multiple memories by their IDs.
        
        Args:
            memory_ids: List of memory IDs to delete
            
        Returns:
            Number of memories successfully deleted
        """
        count = 0
        for memory_id in memory_ids:
            if self.delete_memory(memory_id):
                count += 1
        return count
    
    def delete_memories_matching(
        self, 
        query: str, 
        memory_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> int:
        """
        Delete memories matching a search query.
        
        Useful for bulk cleanup of related memories, e.g., all image-related
        context after finishing an image analysis session.
        
        Args:
            query: Search query to match memories
            memory_types: Optional list of types to search
            limit: Maximum number of memories to delete
            
        Returns:
            Number of memories deleted
        """
        # Search for matching memories
        results = self.search(query, memory_types=memory_types, limit=limit)
        
        # Extract IDs and delete
        deleted = 0
        for result in results:
            item = result.get("item", {})
            memory_id = item.get("id")
            memory_type = result.get("type")
            
            if memory_id:
                if self.delete_memory(memory_id, memory_type=memory_type):
                    deleted += 1
        
        if deleted:
            self._log(f"Deleted {deleted} memories matching '{query}'")
        
        return deleted
    
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
    
    # -------------------------------------------------------------------------
    #                          Session Management
    # -------------------------------------------------------------------------
    
    def save_session(
        self,
        name: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save current session state for later resumption.
        
        Similar to Gemini CLI's /chat save command.
        
        Args:
            name: Session name (used as filename)
            conversation_history: Optional conversation messages to save
            metadata: Optional additional metadata
            
        Returns:
            Path to saved session file
        """
        sessions_path = self.user_path / "sessions"
        sessions_path.mkdir(parents=True, exist_ok=True)
        
        session_file = sessions_path / f"{name}.json"
        
        session_data = {
            "name": name,
            "user_id": self.user_id,
            "saved_at": time.time(),
            "saved_at_iso": datetime.now().isoformat(),
            "short_term": [item.to_dict() for item in self._short_term],
            "long_term_snapshot": [item.to_dict() for item in self._long_term[-50:]],  # Last 50
            "entity_ids": list(self._entities.keys()),
            "conversation_history": conversation_history or [],
            "metadata": metadata or {},
            "config": self.config
        }
        
        self._write_json(session_file, session_data)
        self._log(f"Saved session '{name}' to {session_file}")
        
        return str(session_file)
    
    def resume_session(self, name: str) -> Dict[str, Any]:
        """
        Resume a previously saved session.
        
        Similar to Gemini CLI's /chat resume command.
        
        Args:
            name: Session name to resume
            
        Returns:
            Session data including conversation history
        """
        sessions_path = self.user_path / "sessions"
        session_file = sessions_path / f"{name}.json"
        
        if not session_file.exists():
            raise FileNotFoundError(f"Session '{name}' not found")
        
        session_data = self._read_json(session_file, {})
        
        # Restore short-term memory from session
        if "short_term" in session_data:
            self._short_term = [MemoryItem.from_dict(item) for item in session_data["short_term"]]
            self._save_short_term()
        
        self._log(f"Resumed session '{name}'")
        
        return session_data
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all saved sessions.
        
        Similar to Gemini CLI's /chat list command.
        
        Returns:
            List of session info dicts
        """
        sessions_path = self.user_path / "sessions"
        
        if not sessions_path.exists():
            return []
        
        sessions = []
        for session_file in sessions_path.glob("*.json"):
            try:
                data = self._read_json(session_file, {})
                sessions.append({
                    "name": data.get("name", session_file.stem),
                    "saved_at": data.get("saved_at_iso", ""),
                    "short_term_count": len(data.get("short_term", [])),
                    "has_conversation": len(data.get("conversation_history", [])) > 0,
                    "file_path": str(session_file)
                })
            except Exception:
                continue
        
        # Sort by saved_at descending
        sessions.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
        return sessions
    
    def delete_session(self, name: str) -> bool:
        """Delete a saved session."""
        sessions_path = self.user_path / "sessions"
        session_file = sessions_path / f"{name}.json"
        
        if session_file.exists():
            session_file.unlink()
            self._log(f"Deleted session '{name}'")
            return True
        return False
    
    # -------------------------------------------------------------------------
    #                          Context Compression
    # -------------------------------------------------------------------------
    
    def compress(
        self,
        llm_func: Optional[callable] = None,
        max_items: int = 10
    ) -> str:
        """
        Compress short-term memory into a summary.
        
        Similar to Gemini CLI's /compress command.
        
        Args:
            llm_func: Optional LLM function for summarization.
                      Should accept (prompt: str) -> str
            max_items: Max items to keep after compression
            
        Returns:
            The generated summary
        """
        if len(self._short_term) <= max_items:
            return ""  # No compression needed
        
        # Gather content to compress
        items_to_compress = self._short_term[:-max_items]
        content_list = [item.content for item in items_to_compress]
        
        # Generate summary
        if llm_func:
            prompt = f"""Summarize the following conversation context into key points.
Preserve important facts, decisions, and context.
Be concise but comprehensive.

Context to summarize:
{chr(10).join(f'- {c}' for c in content_list)}

Summary:"""
            summary = llm_func(prompt)
        else:
            # Simple concatenation if no LLM
            summary = "Compressed context: " + " | ".join(content_list[:5]) + "..."
        
        # Add summary as a high-importance long-term memory
        self.add_long_term(
            content=f"[Session Summary] {summary}",
            metadata={"type": "compression_summary", "items_compressed": len(items_to_compress)},
            importance=0.9
        )
        
        # Keep only recent items
        self._short_term = self._short_term[-max_items:]
        self._save_short_term()
        
        self._log(f"Compressed {len(items_to_compress)} items into summary")
        
        return summary
    
    def auto_compress_if_needed(
        self,
        threshold_percent: float = 0.7,
        llm_func: Optional[callable] = None
    ) -> Optional[str]:
        """
        Auto-compress if short-term memory exceeds threshold.
        
        Args:
            threshold_percent: Compress when STM is this % full (0.0-1.0)
            llm_func: Optional LLM function for summarization
            
        Returns:
            Summary if compressed, None otherwise
        """
        limit = self.config["short_term_limit"]
        threshold = int(limit * threshold_percent)
        
        if len(self._short_term) >= threshold:
            return self.compress(llm_func=llm_func, max_items=int(limit * 0.3))
        
        return None
    
    # -------------------------------------------------------------------------
    #                          Checkpointing
    # -------------------------------------------------------------------------
    
    def create_checkpoint(
        self,
        name: Optional[str] = None,
        include_files: Optional[List[str]] = None
    ) -> str:
        """
        Create a checkpoint of current memory state.
        
        Similar to Gemini CLI's checkpoint before destructive operations.
        
        Args:
            name: Optional checkpoint name (auto-generated if not provided)
            include_files: Optional list of file paths to snapshot
            
        Returns:
            Checkpoint ID
        """
        checkpoints_path = self.user_path / "checkpoints"
        checkpoints_path.mkdir(parents=True, exist_ok=True)
        
        checkpoint_id = name or f"checkpoint_{int(time.time())}"
        checkpoint_file = checkpoints_path / f"{checkpoint_id}.json"
        
        checkpoint_data = {
            "id": checkpoint_id,
            "created_at": time.time(),
            "created_at_iso": datetime.now().isoformat(),
            "memory_export": self.export(),
            "file_snapshots": {}
        }
        
        # Optionally snapshot files
        if include_files:
            for file_path in include_files:
                try:
                    path = Path(file_path)
                    if path.exists() and path.is_file():
                        checkpoint_data["file_snapshots"][file_path] = path.read_text(encoding="utf-8")
                except Exception as e:
                    self._log(f"Could not snapshot file {file_path}: {e}", logging.WARNING)
        
        self._write_json(checkpoint_file, checkpoint_data)
        self._log(f"Created checkpoint '{checkpoint_id}'")
        
        return checkpoint_id
    
    def restore_checkpoint(self, checkpoint_id: str, restore_files: bool = False) -> bool:
        """
        Restore memory state from a checkpoint.
        
        Args:
            checkpoint_id: Checkpoint ID to restore
            restore_files: Whether to restore file snapshots
            
        Returns:
            True if restored successfully
        """
        checkpoints_path = self.user_path / "checkpoints"
        checkpoint_file = checkpoints_path / f"{checkpoint_id}.json"
        
        if not checkpoint_file.exists():
            self._log(f"Checkpoint '{checkpoint_id}' not found", logging.ERROR)
            return False
        
        checkpoint_data = self._read_json(checkpoint_file, {})
        
        # Restore memory
        if "memory_export" in checkpoint_data:
            self.import_data(checkpoint_data["memory_export"])
        
        # Optionally restore files
        if restore_files and "file_snapshots" in checkpoint_data:
            for file_path, content in checkpoint_data["file_snapshots"].items():
                try:
                    Path(file_path).write_text(content, encoding="utf-8")
                    self._log(f"Restored file: {file_path}")
                except Exception as e:
                    self._log(f"Could not restore file {file_path}: {e}", logging.WARNING)
        
        self._log(f"Restored checkpoint '{checkpoint_id}'")
        return True
    
    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all checkpoints."""
        checkpoints_path = self.user_path / "checkpoints"
        
        if not checkpoints_path.exists():
            return []
        
        checkpoints = []
        for checkpoint_file in checkpoints_path.glob("*.json"):
            try:
                data = self._read_json(checkpoint_file, {})
                checkpoints.append({
                    "id": data.get("id", checkpoint_file.stem),
                    "created_at": data.get("created_at_iso", ""),
                    "has_file_snapshots": len(data.get("file_snapshots", {})) > 0,
                    "file_path": str(checkpoint_file)
                })
            except Exception:
                continue
        
        # Sort by created_at descending
        checkpoints.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return checkpoints
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        checkpoints_path = self.user_path / "checkpoints"
        checkpoint_file = checkpoints_path / f"{checkpoint_id}.json"
        
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            self._log(f"Deleted checkpoint '{checkpoint_id}'")
            return True
        return False
    
    # -------------------------------------------------------------------------
    #                          Memory Commands (Slash Commands)
    # -------------------------------------------------------------------------
    
    def handle_command(self, command: str) -> Dict[str, Any]:
        """
        Handle slash commands like /memory show, /memory add, etc.
        
        Similar to Gemini CLI's /memory commands.
        
        Args:
            command: Full command string (e.g., "/memory show" or "/memory add User likes Python")
            
        Returns:
            Command result dict
        """
        parts = command.strip().split(maxsplit=2)
        
        if len(parts) < 2:
            return {"error": "Invalid command. Use: /memory <action> [args]"}
        
        action = parts[1].lower()
        args = parts[2] if len(parts) > 2 else ""
        
        if action == "show":
            return {
                "action": "show",
                "stats": self.get_stats(),
                "short_term": [item.content for item in self.get_short_term(limit=10)],
                "long_term": [item.content for item in self.get_long_term(limit=10)]
            }
        
        elif action == "add":
            if not args:
                return {"error": "Usage: /memory add <content>"}
            mem_id = self.add_long_term(args, importance=0.8)
            return {"action": "add", "id": mem_id, "content": args}
        
        elif action == "clear":
            target = args.lower() if args else "short"
            if target == "all":
                self.clear_all()
                return {"action": "clear", "target": "all"}
            elif target == "short":
                self.clear_short_term()
                return {"action": "clear", "target": "short_term"}
            else:
                return {"error": "Usage: /memory clear [short|all]"}
        
        elif action == "delete":
            if not args:
                return {"error": "Usage: /memory delete <id> or /memory delete --query <search_query>"}
            
            # Handle --query flag for bulk deletion
            if args.startswith("--query "):
                query = args[8:]  # Remove "--query " prefix
                if not query:
                    return {"error": "Usage: /memory delete --query <search_query>"}
                deleted = self.delete_memories_matching(query, limit=10)
                return {
                    "action": "delete", 
                    "type": "query", 
                    "query": query, 
                    "deleted_count": deleted
                }
            
            # Single ID deletion
            success = self.delete_memory(args)
            return {
                "action": "delete", 
                "type": "single",
                "id": args, 
                "success": success
            }
        
        elif action == "list":
            # List memories with IDs for easy deletion reference
            memory_type = args.lower() if args else "all"
            items = []
            
            if memory_type in ("all", "short", "short_term"):
                for item in self.get_short_term(limit=20):
                    items.append({
                        "type": "short_term",
                        "id": item.id,
                        "content": item.content[:100] + "..." if len(item.content) > 100 else item.content,
                        "importance": item.importance
                    })
            
            if memory_type in ("all", "long", "long_term"):
                for item in self.get_long_term(limit=20):
                    items.append({
                        "type": "long_term",
                        "id": item.id,
                        "content": item.content[:100] + "..." if len(item.content) > 100 else item.content,
                        "importance": item.importance
                    })
            
            if memory_type in ("all", "entity", "entities"):
                for name, entity in self._entities.items():
                    items.append({
                        "type": "entity",
                        "id": name,
                        "name": entity.name,
                        "entity_type": entity.entity_type
                    })
            
            return {"action": "list", "filter": memory_type, "items": items}
        
        elif action == "search":
            if not args:
                return {"error": "Usage: /memory search <query>"}
            results = self.search(args, limit=10)
            return {"action": "search", "query": args, "results": results}
        
        elif action == "save":
            if not args:
                return {"error": "Usage: /memory save <session_name>"}
            path = self.save_session(args)
            return {"action": "save", "session": args, "path": path}
        
        elif action == "resume":
            if not args:
                return {"error": "Usage: /memory resume <session_name>"}
            try:
                self.resume_session(args)
                return {"action": "resume", "session": args, "restored": True}
            except FileNotFoundError:
                return {"error": f"Session '{args}' not found"}
        
        elif action == "sessions":
            sessions = self.list_sessions()
            return {"action": "sessions", "sessions": sessions}
        
        elif action == "compress":
            summary = self.compress()
            return {"action": "compress", "summary": summary}
        
        elif action == "checkpoint":
            checkpoint_id = self.create_checkpoint(args if args else None)
            return {"action": "checkpoint", "id": checkpoint_id}
        
        elif action == "restore":
            if not args:
                return {"error": "Usage: /memory restore <checkpoint_id>"}
            success = self.restore_checkpoint(args)
            return {"action": "restore", "checkpoint": args, "success": success}
        
        elif action == "checkpoints":
            checkpoints = self.list_checkpoints()
            return {"action": "checkpoints", "checkpoints": checkpoints}
        
        elif action == "refresh":
            self._load_all()
            return {"action": "refresh", "message": "Memory reloaded from disk"}
        
        elif action == "help":
            return {
                "action": "help",
                "commands": {
                    "/memory show": "Display memory stats and recent items",
                    "/memory list [short|long|entity]": "List memories with IDs for deletion",
                    "/memory add <content>": "Add to long-term memory",
                    "/memory delete <id>": "Delete a specific memory by ID",
                    "/memory delete --query <q>": "Delete memories matching query",
                    "/memory clear [short|all]": "Clear all memory (bulk)",
                    "/memory search <query>": "Search memories",
                    "/memory save <name>": "Save session",
                    "/memory resume <name>": "Resume session",
                    "/memory sessions": "List saved sessions",
                    "/memory compress": "Compress short-term memory",
                    "/memory checkpoint [name]": "Create checkpoint",
                    "/memory restore <id>": "Restore checkpoint",
                    "/memory checkpoints": "List checkpoints",
                    "/memory refresh": "Reload from disk"
                }
            }
        
        else:
            return {"error": f"Unknown action: {action}. Use /memory help for available commands."}


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
