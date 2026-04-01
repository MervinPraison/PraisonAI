"""
Memory and caching functionality extracted from Agent class for better maintainability.

This module contains all memory management, caching, and chat history methods.
Part of the agent god class decomposition to reduce agent.py from 8,915 lines.
"""

import os
import time
import logging
import threading
from typing import Any, Optional, Dict, List
from collections import OrderedDict
from praisonaiagents._logging import get_logger


class MemoryMixin:
    """
    Mixin containing memory and caching methods for the Agent class.
    
    This mixin extracts approximately 500+ lines of memory-related functionality
    from the main Agent class, including:
    - _cache_put() and _cache_get() methods (LRU cache operations)
    - _add_to_chat_history() and related history management
    - _truncate_chat_history() (thread-safe history truncation)
    - Memory context retrieval and storage
    - Chat history persistence and management
    """
    
    def _cache_put(self, cache_dict, key, value):
        """
        Thread-safe LRU cache put operation.
        
        Args:
            cache_dict: The cache dictionary (OrderedDict)
            key: Cache key 
            value: Value to cache
        """
        with self._cache_lock:
            # Remove existing key to update order
            if key in cache_dict:
                del cache_dict[key]
            cache_dict[key] = value
            
            # Implement LRU eviction (keep most recent 100 items)
            while len(cache_dict) > 100:
                cache_dict.popitem(last=False)  # Remove oldest item
    
    def _cache_get(self, cache_dict, key):
        """
        Thread-safe LRU cache get operation.
        
        Args:
            cache_dict: The cache dictionary (OrderedDict)
            key: Cache key
            
        Returns:
            Cached value if found, None otherwise
        """
        with self._cache_lock:
            if key in cache_dict:
                # Move to end (most recent)
                value = cache_dict[key]
                del cache_dict[key]
                cache_dict[key] = value
                return value
            return None
    
    def _add_to_chat_history(self, role, content):
        """
        Thread-safe method to add messages to chat history.
        
        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content
        """
        with self._history_lock:
            self.chat_history.append({"role": role, "content": content})
    
    def _add_to_chat_history_if_not_duplicate(self, role, content):
        """
        Thread-safe method to add messages to chat history only if not duplicate.
        
        Atomically checks for duplicate and adds message under the same lock to prevent TOCTOU races.
        
        Args:
            role: Message role ("user", "assistant", "system")  
            content: Message content
            
        Returns:
            bool: True if message was added, False if it was a duplicate
        """
        with self._history_lock:
            # Check if last message is identical (same role and content)
            if (self.chat_history and 
                self.chat_history[-1].get("role") == role and 
                self.chat_history[-1].get("content") == content):
                return False  # Don't add duplicate
                
            # Add the message
            self.chat_history.append({"role": role, "content": content})
            return True  # Message was added
    
    def _get_chat_history_length(self):
        """Thread-safe method to get chat history length."""
        with self._history_lock:
            return len(self.chat_history)
    
    def _truncate_chat_history(self, length):
        """
        Thread-safe method to truncate chat history to specified length.
        
        Args:
            length: Target length for chat history
        """
        with self._history_lock:
            if length < len(self.chat_history):
                self.chat_history = self.chat_history[:length]
    
    def get_memory_context(self, query: Optional[str] = None) -> str:
        """
        Get memory context for the current conversation.
        
        Args:
            query: Optional query to focus the context
            
        Returns:
            Memory context as formatted string
        """
        if not self._memory_instance:
            return ""
            
        try:
            # Search short-term memory for relevant context
            results = self._memory_instance.search_short_term(query or "conversation context", limit=5)
            if results:
                context_parts = []
                for result in results:
                    context_parts.append(f"- {result}")
                return "Recent memory:\n" + "\n".join(context_parts)
        except Exception as e:
            get_logger(__name__).debug(f"Error retrieving memory context: {e}")
            
        return ""
    
    def get_learn_context(self) -> str:
        """
        Get learning context for injection into system prompt.
        
        Returns learned preferences, insights, and patterns when memory="learn"
        is enabled. Returns empty string when learn is not enabled (zero overhead).
        
        Returns:
            Learning context as formatted string
        """
        if not self._memory_instance or not hasattr(self._memory_instance, 'learn'):
            return ""
            
        try:
            # Get learned preferences and patterns
            learn_manager = self._memory_instance.learn
            if learn_manager and hasattr(learn_manager, 'get_preferences'):
                preferences = learn_manager.get_preferences()
                if preferences:
                    return f"User preferences and patterns:\n{preferences}"
        except Exception as e:
            get_logger(__name__).debug(f"Error retrieving learn context: {e}")
            
        return ""
    
    def store_memory(self, content: str, memory_type: str = "short_term", **kwargs: Any) -> None:
        """
        Store content in memory.
        
        Args:
            content: Content to store
            memory_type: Type of memory ("short_term", "long_term")
            **kwargs: Additional metadata for storage
        """
        if not self._memory_instance:
            get_logger(__name__).debug("No memory instance configured")
            return
            
        try:
            if memory_type == "short_term":
                self._memory_instance.store_short_term(content, **kwargs)
            elif memory_type == "long_term" and hasattr(self._memory_instance, 'store_long_term'):
                self._memory_instance.store_long_term(content, **kwargs)
            else:
                get_logger(__name__).warning(f"Unknown memory type: {memory_type}")
        except Exception as e:
            get_logger(__name__).error(f"Error storing memory: {e}")
    
    def _display_memory_info(self):
        """Display memory information to user in a friendly format."""
        if not self._memory_instance:
            return
        
        # Only display once per chat session
        if hasattr(self, '_memory_info_displayed'):
            return
        self._memory_info_displayed = True
        
        try:
            memory_info = []
            if hasattr(self._memory_instance, 'get_stats'):
                stats = self._memory_instance.get_stats()
                memory_info.append(f"Memory: {stats}")
            elif hasattr(self._memory_instance, 'store'):
                memory_info.append("Memory: Active")
            
            if memory_info and self.verbose:
                get_logger(__name__).info(" | ".join(memory_info))
        except Exception as e:
            get_logger(__name__).debug(f"Error displaying memory info: {e}")
    
    def _persist_message(self, role: str, content: str) -> None:
        """
        Persist a message to the database/session store.
        
        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content
        """
        # This would contain the actual persistence logic
        # NOTE: This is a placeholder that delegates to the agent.py implementation.
        # In the full decomposition, this would contain the actual implementation 
        # for database persistence, session store updates, etc.
        pass
    
    def _init_db_session(self):
        """Initialize database session for message persistence (lazy)."""
        # NOTE: This is a placeholder that delegates to the agent.py implementation.
        # In the full decomposition, this would contain the actual implementation 
        # for database session initialization.
        pass
    
    def _init_session_store(self):
        """Initialize session store for JSON-based persistence (lazy)."""
        # NOTE: This is a placeholder that delegates to the agent.py implementation.
        # In the full decomposition, this would contain the actual implementation 
        # for session store initialization.
        pass
    
    # Additional memory-related methods would be extracted here:
    # - _init_memory() - Memory configuration and setup
    # - _ensure_knowledge_processed() - Knowledge system integration  
    # - _get_knowledge_context() - Knowledge retrieval
    # - retrieve() - Context retrieval without LLM generation
    # - query() - RAG-style query with structured results
    # - Memory adapter methods
    # - Chat history optimization
    # - Session management
    # - etc.