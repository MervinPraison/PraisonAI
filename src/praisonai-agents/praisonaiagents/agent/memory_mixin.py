"""
Memory, caching, and session persistence mixin for the Agent class.

Contains all methods for chat history management, caching, session
persistence, auto-memory, and auto-learning. Extracted from agent.py
for maintainability.
"""

import os
import logging
from praisonaiagents._logging import get_logger

# Fallback helpers to avoid circular imports
def _get_console():
    from rich.console import Console
    return Console

def _get_live():
    from rich.live import Live
    return Live

def _get_display_functions():
    from ..main import (
        display_error, display_instruction, display_interaction,
        display_generating, display_self_reflection, ReflectionOutput,
        adisplay_instruction, execute_sync_callback
    )
    return {
        'display_error': display_error,
        'display_instruction': display_instruction,
        'display_interaction': display_interaction,
        'display_generating': display_generating,
        'display_self_reflection': display_self_reflection,
        'ReflectionOutput': ReflectionOutput,
        'adisplay_instruction': adisplay_instruction,
        'execute_sync_callback': execute_sync_callback,
    }

logger = logging.getLogger(__name__)



import contextlib
from typing import List, Optional, Any, Dict, Generator, TYPE_CHECKING
from collections import OrderedDict

if TYPE_CHECKING:
    pass


class MemoryMixin:
    """Mixin providing memory methods for the Agent class."""

    def _cache_put(self, cache_dict, key, value):
        """Thread-safe LRU cache put operation.
        
        Args:
            cache_dict: The cache dictionary (OrderedDict)
            key: Cache key 
            value: Value to cache
        """
        with self._cache_lock:
            # Move to end if already exists (LRU update)
            if key in cache_dict:
                del cache_dict[key]
            
            # Add new entry
            cache_dict[key] = value
            
            # Evict oldest if over limit
            while len(cache_dict) > self._max_cache_size:
                cache_dict.popitem(last=False)  # Remove oldest (FIFO)

    def _add_to_chat_history(self, role, content):
        """Thread-safe method to add messages to chat history.
        
        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content
        """
        with self._history_lock:
            self.chat_history.append({"role": role, "content": content})

    def _add_to_chat_history_if_not_duplicate(self, role, content):
        """Thread-safe method to add messages to chat history only if not duplicate.
        
        Atomically checks for duplicate and adds message under the same lock to prevent TOCTOU races.
        
        Args:
            role: Message role ("user", "assistant", "system") 
            content: Message content
            
        Returns:
            bool: True if message was added, False if duplicate was detected
        """
        with self._history_lock:
            # Check for duplicate within the same critical section
            if (self.chat_history and 
                self.chat_history[-1].get("role") == role and 
                self.chat_history[-1].get("content") == content):
                return False
            
            # Not a duplicate, add the message
            self.chat_history.append({"role": role, "content": content})
            return True

    def _get_chat_history_length(self):
        """Thread-safe method to get chat history length."""
        with self._history_lock:
            return len(self.chat_history)

    def _truncate_chat_history(self, length):
        """Thread-safe method to truncate chat history to specified length.
        
        Args:
            length: Target length for chat history
        """
        with self._history_lock:
            self.chat_history = self.chat_history[:length]

    def _cache_get(self, cache_dict, key):
        """Thread-safe LRU cache get operation.
        
        Args:
            cache_dict: The cache dictionary (OrderedDict)
            key: Cache key
        
        Returns:
            Value if found, None otherwise
        """
        with self._cache_lock:
            if key not in cache_dict:
                return None
            
            # Move to end (mark as recently used)
            value = cache_dict[key]
            del cache_dict[key]
            cache_dict[key] = value
            return value

    def clear_history(self):
        """Clear all chat history.
        
        Also resets _auto_save_last_index to prevent silent message loss
        when auto_save is enabled.
        """
        self.chat_history = []
        # Reset auto-save index to prevent stale index causing message loss
        self._auto_save_last_index = 0

    def prune_history(self, keep_last: int = 5) -> int:
        """
        Prune chat history to keep only the last N messages.
        
        Useful for cleaning up large history after image analysis sessions
        to prevent context window saturation.
        
        Args:
            keep_last: Number of recent messages to keep
            
        Returns:
            Number of messages deleted
        """
        with self._history_lock:
            if len(self.chat_history) <= keep_last:
                return 0
            
            deleted_count = len(self.chat_history) - keep_last
            self.chat_history = self.chat_history[-keep_last:]
            # Reset auto-save index to match new history length
            self._auto_save_last_index = len(self.chat_history)
            return deleted_count

    def delete_history(self, index: int) -> bool:
        """
        Delete a specific message from chat history by index.
        
        Supports negative indexing (-1 for last message, etc.).
        
        Args:
            index: Message index (0-based, supports negative indexing)
            
        Returns:
            True if deleted, False if index out of range
        """
        with self._history_lock:
            try:
                del self.chat_history[index]
                # Adjust auto-save index if deletion affects saved range
                if hasattr(self, '_auto_save_last_index'):
                    self._auto_save_last_index = min(
                        self._auto_save_last_index,
                        len(self.chat_history)
                    )
                return True
            except IndexError:
                return False

    def delete_history_matching(self, pattern: str) -> int:
        """
        Delete all messages matching a pattern.
        
        Useful for removing all image-related messages after processing.
        
        Args:
            pattern: Substring to match in message content
            
        Returns:
            Number of messages deleted
        """
        with self._history_lock:
            original_len = len(self.chat_history)
            self.chat_history = [
                msg for msg in self.chat_history
                if pattern.lower() not in msg.get("content", "").lower()
            ]
            deleted_count = original_len - len(self.chat_history)
            # Adjust auto-save index if deletion affects saved range
            if deleted_count > 0 and hasattr(self, '_auto_save_last_index'):
                self._auto_save_last_index = min(
                    self._auto_save_last_index,
                    len(self.chat_history)
                )
            return deleted_count

    def get_history_size(self) -> int:
        """Get the current number of messages in chat history."""
        return len(self.chat_history)

    @contextlib.contextmanager
    def ephemeral(self) -> Generator[None, None, None]:
        """
        Context manager for ephemeral conversations.
        
        Messages within this block are NOT permanently stored in chat_history.
        History is restored to pre-block state after exiting.
        
        Example:
            with agent.ephemeral():
                response = agent.chat("[IMAGE] Analyze this")
                # After block, history is restored - image NOT persisted
        """
        # Save current history state
        with self._history_lock:
            saved_history = self.chat_history.copy()
        
        try:
            yield
        finally:
            # Restore history to pre-block state
            with self._history_lock:
                self.chat_history = saved_history

    def _init_db_session(self):
        """Initialize DB session if db adapter is provided (lazy, first chat only)."""
        if self._db is None or self._db_initialized:
            return
        
        # Generate session_id if not provided: default to per-hour ID (YYYYMMDDHH-agentname)
        if self._session_id is None:
            import hashlib
            from datetime import datetime, timezone
            # Per-hour session ID: YYYYMMDDHH (UTC) + agent name hash for uniqueness
            hour_str = datetime.now(timezone.utc).strftime("%Y%m%d%H")
            agent_hash = hashlib.md5((self.name or "agent").encode()).hexdigest()[:6]
            self._session_id = f"{hour_str}-{agent_hash}"
        
        # Call db adapter's on_agent_start to get previous messages
        try:
            history = self._db.on_agent_start(
                agent_name=self.name,
                session_id=self._session_id,
                user_id=self.user_id,
                metadata={"role": self.role, "goal": self.goal}
            )
            
            # Restore chat history from previous session
            if history:
                for msg in history:
                    self.chat_history.append({
                        "role": msg.role,
                        "content": msg.content
                    })
                logging.info(f"Resumed session {self._session_id} with {len(history)} messages")
        except Exception as e:
            logging.warning(f"Failed to initialize DB session: {e}")
        
        self._db_initialized = True
        self._current_run_id = None  # Track current run

    def _init_session_store(self):
        """
        Initialize session store for JSON-based persistence (lazy, first chat only).
        
        This is used when session_id is provided but no DB adapter.
        Enables automatic session persistence with zero configuration.
        """
        if self._session_store_initialized:
            return
        
        # Only initialize if session_id is provided and no DB adapter
        if self._session_id is None or self._db is not None:
            self._session_store_initialized = True
            return
        
        try:
            from ..session import get_default_session_store
            self._session_store = get_default_session_store()
            
            # Restore chat history from previous session
            history = self._session_store.get_chat_history(self._session_id)
            if history:
                # Only restore if chat_history is empty (avoid duplicates)
                if not self.chat_history:
                    for msg in history:
                        self.chat_history.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                    logging.info(f"Restored session {self._session_id} with {len(history)} messages from JSON store")
            
            # Set agent info
            self._session_store.set_agent_info(
                self._session_id,
                agent_name=self.name,
                user_id=self.user_id,
            )
        except Exception as e:
            logging.warning(f"Failed to initialize session store: {e}")
            self._session_store = None
        
        self._session_store_initialized = True

    def _start_run(self, input_content: str):
        """Start a new run (turn) for persistence tracking."""
        if self._db is None:
            return
        
        import uuid
        self._current_run_id = f"run-{uuid.uuid4().hex[:12]}"
        
        try:
            if hasattr(self._db, 'on_run_start'):
                self._db.on_run_start(
                    session_id=self._session_id,
                    run_id=self._current_run_id,
                    input_content=input_content,
                    metadata={"agent_name": self.name}
                )
        except Exception as e:
            logging.warning(f"Failed to start run: {e}")

    def _end_run(self, output_content: str, status: str = "completed", metrics: dict = None):
        """End the current run (turn)."""
        if self._db is None or self._current_run_id is None:
            return
        
        try:
            if hasattr(self._db, 'on_run_end'):
                self._db.on_run_end(
                    session_id=self._session_id,
                    run_id=self._current_run_id,
                    output_content=output_content,
                    status=status,
                    metrics=metrics or {},
                    metadata={"agent_name": self.name}
                )
        except Exception as e:
            logging.warning(f"Failed to end run: {e}")
        
        self._current_run_id = None

    def _persist_message(self, role: str, content: str):
        """Persist a message to the DB or session store."""
        # Try DB adapter first
        if self._db is not None:
            try:
                if role == "user":
                    self._db.on_user_message(self._session_id, content)
                elif role == "assistant":
                    self._db.on_agent_message(self._session_id, content)
            except Exception as e:
                logging.warning(f"Failed to persist message to DB: {e}")
            return
        
        # Fall back to session store (JSON-based)
        if self._session_store is not None and self._session_id is not None:
            try:
                if role == "user":
                    self._session_store.add_user_message(self._session_id, content)
                elif role == "assistant":
                    self._session_store.add_assistant_message(self._session_id, content)
            except Exception as e:
                logging.warning(f"Failed to persist message to session store: {e}")

    def session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._session_id

    def _load_history_context(self):
        """Load history from past sessions into context.
        
        Note: This functionality is now handled via context= param with ManagerConfig.
        This method is kept for backward compatibility but is a no-op.
        Use context=ManagerConfig(history_sessions=N) to load past sessions.
        """
        pass

    def _process_auto_memory(self, user_message: str, assistant_response: str):
        """Process auto-memory extraction after agent response.
        
        Called after each agent response when auto_memory=True in MemoryConfig.
        Uses AutoMemory to extract and store memorable content (names, preferences,
        facts) from the conversation. No-op when auto_memory is disabled.
        
        Args:
            user_message: The user's input message
            assistant_response: The agent's response
        """
        if not self._auto_memory or not self._memory_instance:
            return
        
        try:
            from ..memory.auto_memory import AutoMemory
            # Lazy-create AutoMemory wrapper on first use
            if not hasattr(self, '_auto_memory_instance') or self._auto_memory_instance is None:
                self._auto_memory_instance = AutoMemory(
                    self._memory_instance,
                    enabled=True,
                    verbose=1 if getattr(self, 'verbose', False) else 0
                )
            self._auto_memory_instance.process_interaction(
                user_message=str(user_message),
                assistant_response=str(assistant_response),
            )
        except Exception as e:
            logging.debug(f"Auto-memory extraction failed: {e}")

    def _process_auto_learning(self):
        """Process auto-learning extraction after agent response.
        
        Called after each agent response when LearnMode.AGENTIC is set.
        Uses LearnManager.process_conversation() to extract and store learnings
        (persona, insights, patterns) from the conversation. No-op when learning
        is disabled or mode is not AGENTIC.
        """
        # Quick exit if no learn config or mode is not AGENTIC
        if not self._learn_config:
            return
        
        # Check if mode is AGENTIC (auto-extract learnings)
        from ..memory.learn.protocols import LearnMode
        mode = getattr(self._learn_config, 'mode', None)
        
        # Handle PROPOSE mode — extract but store as pending for user approval
        if (isinstance(mode, LearnMode) and mode == LearnMode.PROPOSE) or \
           (isinstance(mode, str) and mode == 'propose'):
            learn_manager = None
            if self._memory_instance and hasattr(self._memory_instance, 'learn'):
                learn_manager = self._memory_instance.learn
            if learn_manager:
                try:
                    recent_messages = self.chat_history[-2:] if len(self.chat_history) >= 2 else self.chat_history
                    if recent_messages:
                        # Use same extraction as AGENTIC, but don't auto-store
                        result = learn_manager.process_conversation(
                            messages=recent_messages,
                            llm=getattr(self._learn_config, 'llm', None) or self.llm,
                            extract_only=True,
                        )
                        # Move extracted items to pending queue
                        if result:
                            for p in result.get("persona", []):
                                if p:
                                    learn_manager.add_pending(p, category="persona")
                            for i in result.get("insights", []):
                                if i:
                                    learn_manager.add_pending(i, category="insights")
                            for pt in result.get("patterns", []):
                                if pt:
                                    learn_manager.add_pending(pt, category="patterns")
                except Exception as e:
                    logging.debug(f"PROPOSE mode learning extraction failed: {e}")
            return
        
        if mode is None or (isinstance(mode, LearnMode) and mode != LearnMode.AGENTIC):
            return
        if isinstance(mode, str) and mode != 'agentic':
            return
        
        # Get LearnManager from memory instance
        learn_manager = None
        if self._memory_instance and hasattr(self._memory_instance, 'learn'):
            learn_manager = self._memory_instance.learn
        
        if not learn_manager:
            return
        
        try:
            # Process recent conversation (last 2 messages: user + assistant)
            recent_messages = self.chat_history[-2:] if len(self.chat_history) >= 2 else self.chat_history
            if recent_messages:
                learn_manager.process_conversation(
                    messages=recent_messages,
                    llm=getattr(self._learn_config, 'llm', None) or self.llm,
                )
        except Exception as e:
            logging.debug(f"Auto-learning extraction failed: {e}")

    def _auto_save_session(self):
        """Auto-save session if auto_save is enabled.
        
        G-1 FIX: Routes to SessionStore instead of Memory.save_session() to
        maintain clean separation between conversation history (SessionStore)
        and semantic memory (Memory).
        
        Issue 1 FIX: Track last saved index to avoid duplicate insertion when
        called multiple times in the same session.
        """
        if not self.auto_save:
            return
        
        try:
            # Filter out history markers before saving
            clean_history = [
                {k: v for k, v in msg.items() if k != "_from_history"}
                for msg in self.chat_history
            ]
            
            # Issue 1 FIX: Only save NEW messages since last save
            # Track last saved index to avoid duplicates
            last_saved = getattr(self, '_auto_save_last_index', 0)
            new_messages = clean_history[last_saved:]
            
            if not new_messages:
                return  # Nothing new to save
            
            # G-1 FIX: Use SessionStore for conversation history persistence
            # This maintains clean separation: Memory = facts, SessionStore = turns
            if self._session_store is not None:
                # Persist only NEW messages to SessionStore
                for msg in new_messages:
                    self._session_store.add_message(
                        self.auto_save,  # Use auto_save name as session_id
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                    )
                # Update last saved index
                self._auto_save_last_index = len(clean_history)
                logging.debug(f"Auto-saved {len(new_messages)} new messages to SessionStore: {self.auto_save}")
            elif self._memory_instance and hasattr(self._memory_instance, 'save_session'):
                # Fallback to Memory.save_session() for backward compatibility
                # Memory.save_session() replaces entire history, so no duplicate issue
                self._memory_instance.save_session(
                    name=self.auto_save,
                    conversation_history=clean_history,
                    metadata={"agent_name": self.name, "user_id": self.user_id}
                )
                logging.debug(f"Auto-saved session to Memory: {self.auto_save}")
        except Exception as e:
            logging.debug(f"Error auto-saving session: {e}")

    def _save_output_to_file(self, content: str) -> bool:
        """Save agent output to file if output_file is configured.
        
        Args:
            content: The response content to save
            
        Returns:
            True if file was saved, False otherwise
        """
        if not self._output_file:
            return False
        
        try:
            import os
            
            # Expand user home directory and resolve path
            file_path = os.path.expanduser(self._output_file)
            file_path = os.path.abspath(file_path)
            
            # Create parent directories if they don't exist
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            # Write content to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(content))
            
            # Print success message to terminal
            print(f"✅ Output saved to {file_path}")
            logging.debug(f"Output saved to file: {file_path}")
            return True
            
        except Exception as e:
            logging.warning(f"Failed to save output to file '{self._output_file}': {e}")
            print(f"⚠️ Failed to save output to {self._output_file}: {e}")
            return False

