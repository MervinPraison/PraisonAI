"""
Context Store Implementation for PraisonAI Agents.

Implements the ContextStore, ContextView, and ContextMutator protocols
with support for:
- Per-agent isolation with scoped views
- Delta buffering with commit/rollback
- Non-destructive truncation/condensation
- Observation masking
- Token estimation caching
- Thread-safe operations

Zero Performance Impact:
- Lazy initialization
- No overhead when not used
- Efficient structural sharing
"""

import threading
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .protocols import (
    ContextView, ContextMutator,
    get_effective_history, cleanup_orphaned_parents,
    validate_message_schema,
)
from .tokens import estimate_tokens_heuristic

logger = logging.getLogger(__name__)


@dataclass
class AgentBudget:
    """Per-agent token budget configuration."""
    max_tokens: int = 0  # 0 = no limit
    history_ratio: float = 0.6
    output_reserve: int = 8000
    compact_threshold: float = 0.8
    
    def get_history_budget(self) -> int:
        if self.max_tokens <= 0:
            return 0
        return int((self.max_tokens - self.output_reserve) * self.history_ratio)


class ContextViewImpl:
    """
    Read-only view of context for an agent.
    
    Provides filtered, budget-aware access to messages.
    Thread-safe via parent store's lock.
    """
    
    def __init__(
        self,
        store: "ContextStoreImpl",
        agent_id: str,
    ):
        self._store = store
        self._agent_id = agent_id
    
    def get_messages(self, max_tokens: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get messages within optional token limit."""
        with self._store._lock:
            messages = self._store._get_agent_messages(self._agent_id)
            
            if max_tokens is None or max_tokens <= 0:
                return [self._strip_internal_metadata(m) for m in messages]
            
            # Apply token limit from end
            result = []
            total_tokens = 0
            
            for msg in reversed(messages):
                tokens = self._store._get_cached_tokens(msg)
                if total_tokens + tokens > max_tokens:
                    break
                result.insert(0, self._strip_internal_metadata(msg))
                total_tokens += tokens
            
            return result
    
    def get_effective_messages(self) -> List[Dict[str, Any]]:
        """Get messages filtered by condense/truncation parents."""
        with self._store._lock:
            messages = self._store._get_agent_messages(self._agent_id)
            effective = get_effective_history(messages)
            return [self._strip_internal_metadata(m) for m in effective]
    
    def get_token_count(self) -> int:
        """Get total token count of visible messages."""
        with self._store._lock:
            messages = self._store._get_agent_messages(self._agent_id)
            effective = get_effective_history(messages)
            return sum(self._store._get_cached_tokens(m) for m in effective)
    
    def get_budget_remaining(self) -> int:
        """Get remaining token budget."""
        with self._store._lock:
            budget = self._store._agent_budgets.get(self._agent_id)
            if not budget or budget.max_tokens <= 0:
                return 0
            
            used = self.get_token_count()
            history_budget = budget.get_history_budget()
            return max(0, history_budget - used)
    
    def get_utilization(self) -> float:
        """Get current utilization (0.0 to 1.0+)."""
        with self._store._lock:
            budget = self._store._agent_budgets.get(self._agent_id)
            if not budget or budget.max_tokens <= 0:
                return 0.0
            
            used = self.get_token_count()
            history_budget = budget.get_history_budget()
            if history_budget <= 0:
                return 0.0
            
            return used / history_budget
    
    def _strip_internal_metadata(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Remove internal metadata from message for API calls."""
        result = msg.copy()
        result.pop("_metadata", None)
        result.pop("_token_cache", None)
        return result


class ContextMutatorImpl:
    """
    Mutation interface for context changes.
    
    Supports delta buffering with commit/rollback.
    Thread-safe via parent store's lock.
    """
    
    def __init__(
        self,
        store: "ContextStoreImpl",
        agent_id: str,
    ):
        self._store = store
        self._agent_id = agent_id
        self._delta: List[Dict[str, Any]] = []
        self._turn_counter = 0
    
    def append(self, message: Dict[str, Any]) -> None:
        """Append message to delta buffer."""
        # Validate schema if enabled
        if self._store._validate_schema:
            is_valid, error = validate_message_schema(message, strict=False)
            if not is_valid:
                logger.warning(f"Message schema validation: {error}")
        
        # Add metadata
        msg_copy = message.copy()
        if "_metadata" not in msg_copy:
            msg_copy["_metadata"] = {}
        
        msg_copy["_metadata"]["agent_id"] = self._agent_id
        msg_copy["_metadata"]["turn_id"] = self._turn_counter
        self._turn_counter += 1
        
        self._delta.append(msg_copy)
    
    def commit(self) -> None:
        """Commit delta buffer to store."""
        if not self._delta:
            return
        
        with self._store._lock:
            agent_messages = self._store._agent_messages.setdefault(self._agent_id, [])
            agent_messages.extend(self._delta)
            
            # Invalidate token cache for new messages
            for msg in self._delta:
                self._store._invalidate_token_cache(msg)
        
        self._delta = []
    
    def rollback(self) -> None:
        """Discard delta buffer."""
        self._delta = []
    
    def tag_for_condensation(self, message_indices: List[int], summary_id: str) -> None:
        """Tag messages as condensed (non-destructive)."""
        with self._store._lock:
            messages = self._store._agent_messages.get(self._agent_id, [])
            
            for idx in message_indices:
                if 0 <= idx < len(messages):
                    msg = messages[idx]
                    if "_metadata" not in msg:
                        msg["_metadata"] = {}
                    msg["_metadata"]["condense_parent"] = summary_id
    
    def tag_for_truncation(self, message_indices: List[int], truncation_id: str) -> None:
        """Tag messages as truncated (non-destructive)."""
        with self._store._lock:
            messages = self._store._agent_messages.get(self._agent_id, [])
            
            for idx in message_indices:
                if 0 <= idx < len(messages):
                    msg = messages[idx]
                    if "_metadata" not in msg:
                        msg["_metadata"] = {}
                    msg["_metadata"]["truncation_parent"] = truncation_id
    
    def mask_observation(self, message_index: int, preview: str = "") -> None:
        """Mask a message's content with a preview."""
        with self._store._lock:
            messages = self._store._agent_messages.get(self._agent_id, [])
            
            if 0 <= message_index < len(messages):
                msg = messages[message_index]
                if "_metadata" not in msg:
                    msg["_metadata"] = {}
                
                # Store original token count before masking
                original_tokens = self._store._get_cached_tokens(msg)
                msg["_metadata"]["original_token_count"] = original_tokens
                msg["_metadata"]["is_masked"] = True
                
                # Generate preview if not provided
                if not preview:
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        preview = content[:100] + "..." if len(content) > 100 else content
                    else:
                        preview = "[masked multimodal content]"
                
                msg["_metadata"]["masked_preview"] = preview
                
                # Replace content with placeholder
                msg["content"] = f"[Output masked: {preview}]"
                
                # Invalidate token cache
                self._store._invalidate_token_cache(msg)
    
    def insert_summary(
        self,
        summary_content: str,
        summary_id: str,
        insert_index: int,
    ) -> None:
        """Insert a summary message at the specified index."""
        with self._store._lock:
            messages = self._store._agent_messages.get(self._agent_id, [])
            
            summary_msg = {
                "role": "assistant",
                "content": summary_content,
                "_metadata": {
                    "agent_id": self._agent_id,
                    "is_summary": True,
                    "summary_id": summary_id,
                },
            }
            
            if 0 <= insert_index <= len(messages):
                messages.insert(insert_index, summary_msg)
    
    def insert_truncation_marker(
        self,
        truncation_id: str,
        messages_hidden: int,
        insert_index: int,
    ) -> None:
        """Insert a truncation marker at the specified index."""
        with self._store._lock:
            messages = self._store._agent_messages.get(self._agent_id, [])
            
            marker_msg = {
                "role": "user",
                "content": f"[Sliding window truncation: {messages_hidden} messages hidden to reduce context]",
                "_metadata": {
                    "agent_id": self._agent_id,
                    "is_truncation_marker": True,
                    "truncation_id": truncation_id,
                },
            }
            
            if 0 <= insert_index <= len(messages):
                messages.insert(insert_index, marker_msg)


class ContextStoreImpl:
    """
    Global context store implementation.
    
    Manages per-agent views and shared context with:
    - Thread-safe operations
    - Token estimation caching
    - Non-destructive truncation/condensation
    - Observation masking
    """
    
    def __init__(
        self,
        validate_schema: bool = False,
        cache_max_size: int = 1000,
    ):
        self._lock = threading.RLock()
        self._validate_schema = validate_schema
        
        # Per-agent message storage
        self._agent_messages: Dict[str, List[Dict[str, Any]]] = {}
        
        # Per-agent budgets
        self._agent_budgets: Dict[str, AgentBudget] = {}
        
        # Shared context (visible to all agents)
        self._shared_context: List[Dict[str, Any]] = []
        
        # Token estimation cache (content_hash -> token_count)
        self._token_cache: Dict[str, int] = {}
        self._cache_max_size = cache_max_size
        
        # Views and mutators (cached)
        self._views: Dict[str, ContextViewImpl] = {}
        self._mutators: Dict[str, ContextMutatorImpl] = {}
    
    def get_view(self, agent_id: str) -> ContextView:
        """Get read-only view for agent."""
        with self._lock:
            if agent_id not in self._views:
                self._views[agent_id] = ContextViewImpl(self, agent_id)
            return self._views[agent_id]
    
    def get_mutator(self, agent_id: str) -> ContextMutator:
        """Get mutator for agent."""
        with self._lock:
            if agent_id not in self._mutators:
                self._mutators[agent_id] = ContextMutatorImpl(self, agent_id)
            return self._mutators[agent_id]
    
    def get_shared_context(self) -> List[Dict[str, Any]]:
        """Get shared context across agents."""
        with self._lock:
            return [m.copy() for m in self._shared_context]
    
    def add_shared_context(self, message: Dict[str, Any]) -> None:
        """Add message to shared context."""
        with self._lock:
            self._shared_context.append(message.copy())
    
    def set_agent_budget(self, agent_id: str, budget: AgentBudget) -> None:
        """Set budget for an agent."""
        with self._lock:
            self._agent_budgets[agent_id] = budget
    
    def snapshot(self) -> bytes:
        """Serialize store state."""
        with self._lock:
            state = {
                "agent_messages": self._agent_messages,
                "agent_budgets": {
                    k: {
                        "max_tokens": v.max_tokens,
                        "history_ratio": v.history_ratio,
                        "output_reserve": v.output_reserve,
                        "compact_threshold": v.compact_threshold,
                    }
                    for k, v in self._agent_budgets.items()
                },
                "shared_context": self._shared_context,
            }
            return json.dumps(state).encode()
    
    def restore(self, data: bytes) -> None:
        """Restore store from serialized state."""
        with self._lock:
            state = json.loads(data.decode())
            self._agent_messages = state.get("agent_messages", {})
            self._shared_context = state.get("shared_context", [])
            
            # Restore budgets
            for agent_id, budget_dict in state.get("agent_budgets", {}).items():
                self._agent_budgets[agent_id] = AgentBudget(**budget_dict)
            
            # Clear caches
            self._token_cache.clear()
            self._views.clear()
            self._mutators.clear()
    
    def _get_agent_messages(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get messages for agent (internal, assumes lock held)."""
        return self._agent_messages.get(agent_id, [])
    
    def _get_cached_tokens(self, message: Dict[str, Any]) -> int:
        """Get token count with caching."""
        # Check for cached value in message
        if "_token_cache" in message:
            return message["_token_cache"]
        
        # Compute hash of content
        content = message.get("content", "")
        if isinstance(content, str):
            content_hash = hash(content)
        else:
            content_hash = hash(json.dumps(content, sort_keys=True))
        
        # Check cache
        cache_key = str(content_hash)
        if cache_key in self._token_cache:
            tokens = self._token_cache[cache_key]
            message["_token_cache"] = tokens
            return tokens
        
        # Estimate tokens
        if isinstance(content, str):
            tokens = estimate_tokens_heuristic(content)
        else:
            # Multimodal: estimate each part
            tokens = 0
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    tokens += estimate_tokens_heuristic(part["text"])
                elif isinstance(part, dict) and part.get("type") == "image_url":
                    tokens += 85  # Base image tokens
        
        # Add role tokens
        tokens += 4  # Role overhead
        
        # Cache result
        if len(self._token_cache) < self._cache_max_size:
            self._token_cache[cache_key] = tokens
        
        message["_token_cache"] = tokens
        return tokens
    
    def _invalidate_token_cache(self, message: Dict[str, Any]) -> None:
        """Invalidate cached token count for message."""
        message.pop("_token_cache", None)
    
    def cleanup_agent(self, agent_id: str) -> None:
        """Clean up orphaned parents for an agent."""
        with self._lock:
            if agent_id in self._agent_messages:
                self._agent_messages[agent_id] = cleanup_orphaned_parents(
                    self._agent_messages[agent_id]
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        with self._lock:
            return {
                "agent_count": len(self._agent_messages),
                "total_messages": sum(len(msgs) for msgs in self._agent_messages.values()),
                "shared_context_size": len(self._shared_context),
                "token_cache_size": len(self._token_cache),
                "agents": {
                    agent_id: {
                        "message_count": len(msgs),
                        "effective_count": len(get_effective_history(msgs)),
                    }
                    for agent_id, msgs in self._agent_messages.items()
                },
            }


# Singleton store instance (lazy)
_global_store: Optional[ContextStoreImpl] = None
_store_lock = threading.Lock()


def get_global_store(validate_schema: bool = False) -> ContextStoreImpl:
    """Get or create global context store."""
    global _global_store
    
    with _store_lock:
        if _global_store is None:
            _global_store = ContextStoreImpl(validate_schema=validate_schema)
        return _global_store


def reset_global_store() -> None:
    """Reset global store (for testing)."""
    global _global_store
    
    with _store_lock:
        _global_store = None
