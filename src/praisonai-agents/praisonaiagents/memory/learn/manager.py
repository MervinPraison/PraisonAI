"""
LearnManager - Central manager for continuous learning capabilities.

Coordinates all learning stores and provides a unified interface for
capturing and retrieving learned information.
"""

from typing import Any, Dict, List, Optional
import logging

from ...config.feature_configs import LearnConfig, LearnScope, LearnBackend
from .stores import (
    PersonaStore,
    InsightStore,
    ThreadStore,
    PatternStore,
    DecisionStore,
    FeedbackStore,
    ImprovementStore,
    LearnEntry,
)


class LearnManager:
    """
    Central manager for continuous learning within the memory system.
    
    Coordinates all learning stores based on LearnConfig settings.
    
    Usage:
        config = LearnConfig(persona=True, insights=True)
        manager = LearnManager(config, user_id="alice")
        
        # Capture learning
        manager.capture_persona("User prefers concise responses")
        manager.capture_insight("User works in data science")
        
        # Retrieve learnings
        context = manager.get_learning_context()
    """
    
    def __init__(
        self,
        config: Optional[LearnConfig] = None,
        user_id: Optional[str] = None,
        store_path: Optional[str] = None,
        custom_stores: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize LearnManager.
        
        Args:
            config: LearnConfig for enabling/disabling learning capabilities
            user_id: User identifier for scoping learnings
            store_path: Custom path for storing learning data
            custom_stores: Optional dict of custom store implementations.
                          Keys are store names (e.g., "domain", "skills").
                          Values must implement LearnProtocol (add, search, list_all, etc.)
                          
        Example:
            ```python
            class MyDomainStore:
                def add(self, content, metadata=None): ...
                def search(self, query, limit=10): ...
                def list_all(self, limit=100): ...
                def get(self, entry_id): ...
                def update(self, entry_id, content, metadata=None): ...
                def delete(self, entry_id): ...
                def clear(self): ...
            
            manager = LearnManager(
                config=LearnConfig(persona=True),
                custom_stores={"domain": MyDomainStore()}
            )
            ```
        """
        self.config = config or LearnConfig()
        self.user_id = user_id or "default"
        self.store_path = store_path or self.config.store_path
        
        # Resolve backend from config
        self._backend = self._create_backend()
        if self._backend is not None:
            logging.info(
                f"LearnManager using {self.config.backend} backend"
            )
        
        scope = self.config.scope
        if isinstance(scope, LearnScope):
            scope = scope.value
        
        self._stores: Dict[str, Any] = {}
        self._custom_stores = custom_stores or {}
        
        # Built-in stores are added first, custom stores can override them
        if self.config.persona and "persona" not in self._custom_stores:
            self._stores["persona"] = PersonaStore(
                store_path=self._get_store_path("persona"),
                user_id=self.user_id,
                scope=scope,
                backend=self._backend,
            )
        
        if self.config.insights and "insights" not in self._custom_stores:
            self._stores["insights"] = InsightStore(
                store_path=self._get_store_path("insights"),
                user_id=self.user_id,
                scope=scope,
                backend=self._backend,
            )
        
        if self.config.thread and "threads" not in self._custom_stores:
            self._stores["threads"] = ThreadStore(
                store_path=self._get_store_path("threads"),
                user_id=self.user_id,
                scope=scope,
                backend=self._backend,
            )
        
        if self.config.patterns and "patterns" not in self._custom_stores:
            self._stores["patterns"] = PatternStore(
                store_path=self._get_store_path("patterns"),
                user_id=self.user_id,
                scope=scope,
                backend=self._backend,
            )
        
        if self.config.decisions and "decisions" not in self._custom_stores:
            self._stores["decisions"] = DecisionStore(
                store_path=self._get_store_path("decisions"),
                user_id=self.user_id,
                scope=scope,
                backend=self._backend,
            )
        
        if self.config.feedback and "feedback" not in self._custom_stores:
            self._stores["feedback"] = FeedbackStore(
                store_path=self._get_store_path("feedback"),
                user_id=self.user_id,
                scope=scope,
                backend=self._backend,
            )
        
        if self.config.improvements and "improvements" not in self._custom_stores:
            self._stores["improvements"] = ImprovementStore(
                store_path=self._get_store_path("improvements"),
                user_id=self.user_id,
                scope=scope,
                backend=self._backend,
            )
        
        # Add custom stores last (they override built-in stores)
        if self._custom_stores:
            for name, store in self._custom_stores.items():
                self._stores[name] = store
        
        # PROPOSE mode: pending learnings queue
        self._pending: List[LearnEntry] = []
    
    def _create_backend(self) -> Any:
        """Create a storage backend from config.
        
        Returns backend instance or None for FILE (default) backend.
        Falls back to None (FILE) on error.
        """
        backend = self.config.backend
        backend_str = backend.value if isinstance(backend, LearnBackend) else str(backend)
        
        if backend_str == "file":
            return None  # FILE uses BaseJSONStore default
        
        if backend_str == "sqlite":
            try:
                from ...storage.backends import SQLiteBackend
                db_path = self.config.db_url or f"{self.store_path or 'learn'}/learn.db"
                # Strip sqlite:/// prefix if present
                if db_path.startswith("sqlite:///"):
                    db_path = db_path[len("sqlite:///"):]
                return SQLiteBackend(db_path=db_path, table_name="learn_store")
            except Exception as e:
                logging.warning(f"Failed to create SQLite backend: {e}. Falling back to FILE.")
                return None
        
        if backend_str == "redis":
            try:
                from ...storage.backends import RedisBackend
                url = self.config.db_url or "redis://localhost:6379"
                return RedisBackend(url=url, prefix="praison:learn:")
            except Exception as e:
                logging.warning(f"Failed to create Redis backend: {e}. Falling back to FILE.")
                return None
        
        if backend_str == "mongodb":
            try:
                from ...storage.backends import MongoDBBackend
                url = self.config.db_url or "mongodb://localhost:27017/"
                return MongoDBBackend(url=url, collection="praison_learn")
            except Exception as e:
                logging.warning(f"Failed to create MongoDB backend: {e}. Falling back to FILE.")
                return None
        
        logging.warning(f"Unknown learn backend '{backend_str}'. Falling back to FILE.")
        return None
    
    def _get_store_path(self, store_name: str) -> Optional[str]:
        """Get path for a specific store."""
        if self.store_path:
            return f"{self.store_path}/{store_name}.json"
        return None
    
    def capture_persona(self, content: str, category: str = "general") -> Optional[LearnEntry]:
        """Capture user preference or profile information."""
        if "persona" in self._stores:
            return self._stores["persona"].add_preference(content, category)
        return None
    
    def capture_insight(self, content: str, source: str = "interaction") -> Optional[LearnEntry]:
        """Capture an observation or learning."""
        if "insights" in self._stores:
            return self._stores["insights"].add_insight(content, source)
        return None
    
    def capture_thread(self, summary: str, thread_id: str) -> Optional[LearnEntry]:
        """Capture thread/session context."""
        if "threads" in self._stores:
            return self._stores["threads"].add_thread_summary(summary, thread_id)
        return None
    
    def capture_pattern(self, pattern: str, pattern_type: str = "general") -> Optional[LearnEntry]:
        """Capture a reusable knowledge pattern."""
        if "patterns" in self._stores:
            return self._stores["patterns"].add_pattern(pattern, pattern_type)
        return None
    
    def capture_decision(
        self,
        decision: str,
        reasoning: str = "",
        outcome: str = "",
    ) -> Optional[LearnEntry]:
        """Capture a decision record."""
        if "decisions" in self._stores:
            return self._stores["decisions"].add_decision(decision, reasoning, outcome)
        return None
    
    def capture_feedback(
        self,
        feedback: str,
        rating: Optional[int] = None,
        source: str = "user",
    ) -> Optional[LearnEntry]:
        """Capture feedback."""
        if "feedback" in self._stores:
            return self._stores["feedback"].add_feedback(feedback, rating, source)
        return None
    
    def capture_improvement(
        self,
        proposal: str,
        area: str = "general",
        priority: str = "medium",
    ) -> Optional[LearnEntry]:
        """Capture an improvement proposal."""
        if "improvements" in self._stores:
            return self._stores["improvements"].add_improvement(proposal, area, priority)
        return None
    
    def get_learning_context(self, limit_per_store: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get learning context from all enabled stores.
        
        Returns a dictionary with entries from each store, suitable for
        injection into agent context.
        """
        context = {}
        for store_name, store in self._stores.items():
            entries = store.list_all(limit=limit_per_store)
            context[store_name] = [e.to_dict() for e in entries]
        return context
    
    def search(self, query: str, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Search across all enabled stores."""
        results = {}
        for store_name, store in self._stores.items():
            entries = store.search(query, limit=limit)
            if entries:
                results[store_name] = [e.to_dict() for e in entries]
        return results
    
    def get_persona_context(self, limit: int = 10) -> List[str]:
        """Get persona entries as context strings."""
        if "persona" not in self._stores:
            return []
        entries = self._stores["persona"].list_all(limit=limit)
        return [e.content for e in entries]
    
    def get_insights_context(self, limit: int = 10) -> List[str]:
        """Get insight entries as context strings."""
        if "insights" not in self._stores:
            return []
        entries = self._stores["insights"].list_all(limit=limit)
        return [e.content for e in entries]
    
    def clear_all(self) -> Dict[str, int]:
        """Clear all stores."""
        cleared = {}
        for store_name, store in self._stores.items():
            cleared[store_name] = store.clear()
        return cleared
    
    def get_stats(self) -> Dict[str, int]:
        """Get entry counts for all stores."""
        return {
            store_name: len(store._entries)
            for store_name, store in self._stores.items()
        }
    
    @property
    def pending_learnings(self) -> List[LearnEntry]:
        """Get list of pending learnings awaiting approval (PROPOSE mode)."""
        return list(self._pending)
    
    def add_pending(
        self,
        content: str,
        category: str = "persona",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LearnEntry:
        """Add a learning to the pending queue for user approval.
        
        Args:
            content: The learning content
            category: Store category (persona, insights, patterns, etc.)
            metadata: Optional metadata
            
        Returns:
            The pending LearnEntry
        """
        from datetime import datetime
        entry_id = f"pending_{category}_{len(self._pending)}_{datetime.utcnow().timestamp()}"
        entry = LearnEntry(
            id=entry_id,
            content=content,
            metadata={**(metadata or {}), "category": category, "status": "pending"},
        )
        self._pending.append(entry)
        return entry
    
    def approve_learning(self, entry_id: str) -> bool:
        """Approve a pending learning — move it to the appropriate store.
        
        Args:
            entry_id: ID of the pending learning to approve
            
        Returns:
            True if approved and stored, False if not found
        """
        for i, entry in enumerate(self._pending):
            if entry.id == entry_id:
                category = entry.metadata.get("category", "persona")
                # Route to appropriate store
                if category in self._stores:
                    self._stores[category].add(entry.content, entry.metadata)
                elif "persona" in self._stores:
                    self._stores["persona"].add(entry.content, entry.metadata)
                self._pending.pop(i)
                return True
        return False
    
    def reject_learning(self, entry_id: str) -> bool:
        """Reject a pending learning — discard it.
        
        Args:
            entry_id: ID of the pending learning to reject
            
        Returns:
            True if found and rejected, False if not found
        """
        for i, entry in enumerate(self._pending):
            if entry.id == entry_id:
                self._pending.pop(i)
                return True
        return False
    
    def approve_all_learnings(self) -> int:
        """Approve all pending learnings at once.
        
        Returns:
            Number of learnings approved
        """
        count = 0
        while self._pending:
            entry = self._pending[0]
            if self.approve_learning(entry.id):
                count += 1
            else:
                break  # Safety
        return count
    
    def to_system_prompt_context(self) -> str:
        """
        Generate context suitable for injection into system prompt.
        
        Returns a formatted string with relevant learnings from all enabled stores.
        """
        parts = []
        
        # 1. Persona - User preferences and profile
        if "persona" in self._stores:
            personas = self.get_persona_context(limit=5)
            if personas:
                parts.append("User Preferences:")
                for p in personas:
                    parts.append(f"- {p}")
        
        # 2. Insights - Observations and learnings
        if "insights" in self._stores:
            insights = self.get_insights_context(limit=5)
            if insights:
                parts.append("\nLearned Insights:")
                for i in insights:
                    parts.append(f"- {i}")
        
        # 3. Patterns - Reusable knowledge patterns
        if "patterns" in self._stores:
            entries = self._stores["patterns"].list_all(limit=3)
            if entries:
                parts.append("\nKnown Patterns:")
                for e in entries:
                    parts.append(f"- {e.content}")
        
        # 4. Decisions - Past decision records (for consistency)
        if "decisions" in self._stores:
            entries = self._stores["decisions"].list_all(limit=3)
            if entries:
                parts.append("\nPast Decisions:")
                for e in entries:
                    parts.append(f"- {e.content}")
        
        # 5. Feedback - User feedback signals
        if "feedback" in self._stores:
            entries = self._stores["feedback"].list_all(limit=3)
            if entries:
                parts.append("\nUser Feedback:")
                for e in entries:
                    parts.append(f"- {e.content}")
        
        # 6. Improvements - Self-improvement proposals
        if "improvements" in self._stores:
            entries = self._stores["improvements"].list_all(limit=3)
            if entries:
                parts.append("\nImprovement Areas:")
                for e in entries:
                    parts.append(f"- {e.content}")
        
        # Note: threads are session-specific and not included in system prompt
        
        return "\n".join(parts) if parts else ""
    
    def process_conversation(
        self,
        messages: List[Dict[str, Any]],
        llm: Optional[str] = None,
        extract_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Process a conversation to extract learnings automatically.
        
        Uses LLM to analyze the conversation and extract:
        - User preferences (persona)
        - Insights and observations
        - Patterns in user behavior
        
        Args:
            messages: Conversation messages (list of {"role": ..., "content": ...})
            llm: Optional LLM model to use for extraction (defaults to gpt-4o-mini)
            
        Returns:
            Dictionary with extracted learnings:
            {
                "persona": [...],
                "insights": [...],
                "patterns": [...],
                "stored": {"persona": N, "insights": N, "patterns": N}
            }
        """
        if not messages:
            return {"persona": [], "insights": [], "patterns": [], "improvements": [], "stored": {}}
        
        # Build conversation text
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages
        ])
        
        # Use LLM to extract learnings
        extraction_prompt = f"""Analyze this conversation and extract learnings.

CONVERSATION:
{conversation_text}

Extract the following (if present):
1. USER PREFERENCES: Things the user likes, dislikes, prefers, or their style
2. INSIGHTS: Observations about the user's domain, work, or context
3. PATTERNS: Recurring behaviors or request patterns
4. IMPROVEMENTS: Concrete proposals to improve future responses

Return JSON:
{{
    "persona": ["preference 1", "preference 2"],
    "insights": ["insight 1", "insight 2"],
    "patterns": ["pattern 1", "pattern 2"],
    "improvements": ["improvement 1", "improvement 2"]
}}

Only include items that are clearly evident from the conversation.
Return empty arrays if nothing is found for a category."""

        try:
            # Lazy import to avoid circular dependency
            from ...llm import LLM
            import json
            
            model = llm or "gpt-4o-mini"
            llm_instance = LLM(model=model)
            response = llm_instance.get_response(
                prompt=extraction_prompt,
                output_json=True,
            )
            
            # Parse response - handle both string and dict responses
            if isinstance(response, str):
                extracted = json.loads(response)
            elif isinstance(response, dict):
                extracted = response
            else:
                extracted = {"persona": [], "insights": [], "patterns": [], "improvements": []}
            
            # Store extracted learnings (unless extract_only)
            stored = {"persona": 0, "insights": 0, "patterns": 0, "improvements": 0}
            
            if not extract_only:
                for preference in extracted.get("persona", []):
                    if preference and "persona" in self._stores:
                        self.capture_persona(preference)
                        stored["persona"] += 1
                
                for insight in extracted.get("insights", []):
                    if insight and "insights" in self._stores:
                        self.capture_insight(insight, source="auto_extraction")
                        stored["insights"] += 1
                
                for pattern in extracted.get("patterns", []):
                    if pattern and "patterns" in self._stores:
                        self.capture_pattern(pattern, pattern_type="auto_extracted")
                        stored["patterns"] += 1
                
                for improvement in extracted.get("improvements", []):
                    if improvement and "improvements" in self._stores:
                        self.capture_improvement(improvement, source="auto_extraction")
                        stored["improvements"] += 1
            
            return {
                "persona": extracted.get("persona", []),
                "insights": extracted.get("insights", []),
                "patterns": extracted.get("patterns", []),
                "improvements": extracted.get("improvements", []),
                "stored": stored,
            }
            
        except Exception as e:
            import logging
            logging.warning(f"Failed to extract learnings: {e}")
            return {"persona": [], "insights": [], "patterns": [], "improvements": [], "stored": {}, "error": str(e)}
    
    async def aprocess_conversation(
        self,
        messages: List[Dict[str, Any]],
        llm: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Async version of process_conversation.
        
        Args:
            messages: Conversation messages
            llm: Optional LLM model
            
        Returns:
            Dictionary with extracted learnings
        """
        if not messages:
            return {"persona": [], "insights": [], "patterns": [], "stored": {}}
        
        # Build conversation text
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages
        ])
        
        extraction_prompt = f"""Analyze this conversation and extract learnings.

CONVERSATION:
{conversation_text}

Extract the following (if present):
1. USER PREFERENCES: Things the user likes, dislikes, prefers, or their style
2. INSIGHTS: Observations about the user's domain, work, or context
3. PATTERNS: Recurring behaviors or request patterns

Return JSON:
{{
    "persona": ["preference 1", "preference 2"],
    "insights": ["insight 1", "insight 2"],
    "patterns": ["pattern 1", "pattern 2"]
}}

Only include items that are clearly evident from the conversation.
Return empty arrays if nothing is found for a category."""

        try:
            # Lazy import to avoid circular dependency
            from ...llm import LLM
            import json
            import asyncio
            
            model = llm or "gpt-4o-mini"
            llm_instance = LLM(model=model)
            
            # Run sync LLM call in executor for async compatibility
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: llm_instance.get_response(
                    prompt=extraction_prompt,
                    output_json=True,
                )
            )
            
            # Parse response - handle both string and dict responses
            if isinstance(response, str):
                extracted = json.loads(response)
            elif isinstance(response, dict):
                extracted = response
            else:
                extracted = {"persona": [], "insights": [], "patterns": []}
            
            stored = {"persona": 0, "insights": 0, "patterns": 0}
            
            for preference in extracted.get("persona", []):
                if preference and "persona" in self._stores:
                    self.capture_persona(preference)
                    stored["persona"] += 1
            
            for insight in extracted.get("insights", []):
                if insight and "insights" in self._stores:
                    self.capture_insight(insight, source="auto_extraction")
                    stored["insights"] += 1
            
            for pattern in extracted.get("patterns", []):
                if pattern and "patterns" in self._stores:
                    self.capture_pattern(pattern, pattern_type="auto_extracted")
                    stored["patterns"] += 1
            
            return {
                "persona": extracted.get("persona", []),
                "insights": extracted.get("insights", []),
                "patterns": extracted.get("patterns", []),
                "stored": stored,
            }
            
        except Exception as e:
            import logging
            logging.warning(f"Failed to extract learnings: {e}")
            return {"persona": [], "insights": [], "patterns": [], "improvements": [], "stored": {}, "error": str(e)}
