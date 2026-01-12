"""
LearnManager - Central manager for continuous learning capabilities.

Coordinates all learning stores and provides a unified interface for
capturing and retrieving learned information.
"""

from typing import Any, Dict, List, Optional

from ...config.feature_configs import LearnConfig, LearnScope
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
    ):
        self.config = config or LearnConfig()
        self.user_id = user_id or "default"
        self.store_path = store_path or self.config.store_path
        
        scope = self.config.scope
        if isinstance(scope, LearnScope):
            scope = scope.value
        
        self._stores: Dict[str, Any] = {}
        
        if self.config.persona:
            self._stores["persona"] = PersonaStore(
                store_path=self._get_store_path("persona"),
                user_id=self.user_id,
                scope=scope,
            )
        
        if self.config.insights:
            self._stores["insights"] = InsightStore(
                store_path=self._get_store_path("insights"),
                user_id=self.user_id,
                scope=scope,
            )
        
        if self.config.thread:
            self._stores["threads"] = ThreadStore(
                store_path=self._get_store_path("threads"),
                user_id=self.user_id,
                scope=scope,
            )
        
        if self.config.patterns:
            self._stores["patterns"] = PatternStore(
                store_path=self._get_store_path("patterns"),
                user_id=self.user_id,
                scope=scope,
            )
        
        if self.config.decisions:
            self._stores["decisions"] = DecisionStore(
                store_path=self._get_store_path("decisions"),
                user_id=self.user_id,
                scope=scope,
            )
        
        if self.config.feedback:
            self._stores["feedback"] = FeedbackStore(
                store_path=self._get_store_path("feedback"),
                user_id=self.user_id,
                scope=scope,
            )
        
        if self.config.improvements:
            self._stores["improvements"] = ImprovementStore(
                store_path=self._get_store_path("improvements"),
                user_id=self.user_id,
                scope=scope,
            )
    
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
    
    def to_system_prompt_context(self) -> str:
        """
        Generate context suitable for injection into system prompt.
        
        Returns a formatted string with relevant learnings.
        """
        parts = []
        
        if "persona" in self._stores:
            personas = self.get_persona_context(limit=5)
            if personas:
                parts.append("User Preferences:")
                for p in personas:
                    parts.append(f"- {p}")
        
        if "insights" in self._stores:
            insights = self.get_insights_context(limit=5)
            if insights:
                parts.append("\nLearned Insights:")
                for i in insights:
                    parts.append(f"- {i}")
        
        return "\n".join(parts) if parts else ""
