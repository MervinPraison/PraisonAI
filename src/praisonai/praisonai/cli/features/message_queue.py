"""
Message Queue for Interactive Mode.

Provides FIFO message queuing while the AI agent is processing,
inspired by Claude Code, Windsurf Cascade, Cursor, and Gemini CLI.

Features:
- Queue messages while agent is processing
- Auto-process queue when agent becomes idle
- Visual indicators for queue status
- Thread-safe operations
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional


# ============================================================================
# Enums
# ============================================================================

class ProcessingState(Enum):
    """State of the agent processing."""
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING_APPROVAL = "waiting_approval"


class MessagePriority(Enum):
    """Priority levels for queued messages."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class QueuedMessage:
    """A message in the queue with metadata."""
    content: str
    timestamp: float = field(default_factory=time.time)
    priority: MessagePriority = MessagePriority.NORMAL


# ============================================================================
# MessageQueue - Thread-safe FIFO queue
# ============================================================================

class MessageQueue:
    """
    Thread-safe FIFO message queue.
    
    Provides basic queue operations with thread safety for concurrent access.
    """
    
    def __init__(self):
        self._messages: List[str] = []
        self._lock = threading.Lock()
    
    @property
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        with self._lock:
            return len(self._messages) == 0
    
    @property
    def count(self) -> int:
        """Get number of messages in queue."""
        with self._lock:
            return len(self._messages)
    
    def add(self, message: str) -> bool:
        """
        Add a message to the end of the queue.
        
        Args:
            message: The message to add
            
        Returns:
            True if message was added, False if empty/whitespace
        """
        trimmed = message.strip() if message else ""
        if not trimmed:
            return False
        
        with self._lock:
            self._messages.append(trimmed)
        return True
    
    def pop(self) -> Optional[str]:
        """
        Remove and return the first message (FIFO).
        
        Returns:
            The first message, or None if queue is empty
        """
        with self._lock:
            if self._messages:
                return self._messages.pop(0)
            return None
    
    def peek(self) -> Optional[str]:
        """
        View the first message without removing it.
        
        Returns:
            The first message, or None if queue is empty
        """
        with self._lock:
            if self._messages:
                return self._messages[0]
            return None
    
    def clear(self) -> None:
        """Remove all messages from the queue."""
        with self._lock:
            self._messages.clear()
    
    def get_all(self) -> List[str]:
        """
        Get all messages as a list (does not remove them).
        
        Returns:
            Copy of all messages in queue order
        """
        with self._lock:
            return self._messages.copy()
    
    def remove_at(self, index: int) -> Optional[str]:
        """
        Remove message at specific index.
        
        Args:
            index: The index to remove (0-based)
            
        Returns:
            The removed message, or None if index is invalid
        """
        with self._lock:
            if 0 <= index < len(self._messages):
                return self._messages.pop(index)
            return None


# ============================================================================
# StateManager - Processing state management
# ============================================================================

class StateManager:
    """
    Manages the processing state with optional callbacks.
    
    Tracks whether the agent is idle, processing, or waiting for approval.
    """
    
    def __init__(self, on_state_change: Optional[Callable[[ProcessingState, ProcessingState], None]] = None):
        self._state = ProcessingState.IDLE
        self._lock = threading.Lock()
        self._on_state_change = on_state_change
    
    @property
    def current_state(self) -> ProcessingState:
        """Get current processing state."""
        with self._lock:
            return self._state
    
    @property
    def is_idle(self) -> bool:
        """Check if currently idle."""
        return self.current_state == ProcessingState.IDLE
    
    @property
    def is_processing(self) -> bool:
        """Check if currently processing."""
        return self.current_state == ProcessingState.PROCESSING
    
    def set_state(self, new_state: ProcessingState) -> None:
        """
        Set the processing state.
        
        Args:
            new_state: The new state to set
        """
        with self._lock:
            old_state = self._state
            self._state = new_state
        
        # Call callback outside lock to prevent deadlock
        if self._on_state_change and old_state != new_state:
            self._on_state_change(old_state, new_state)


# ============================================================================
# QueueDisplay - Visual formatting
# ============================================================================

class QueueDisplay:
    """
    Formats queue and status for display.
    
    Provides visual indicators for queue status, inspired by Codex CLI.
    """
    
    def __init__(
        self,
        queue: MessageQueue,
        state_manager: Optional[StateManager] = None,
        max_message_length: int = 50
    ):
        self._queue = queue
        self._state_manager = state_manager
        self._max_length = max_message_length
    
    def format_queue(self) -> str:
        """
        Format queued messages for display.
        
        Returns:
            Formatted string with queued messages
        """
        messages = self._queue.get_all()
        if not messages:
            return ""
        
        lines = []
        for msg in messages:
            # Truncate long messages
            display_msg = msg
            if len(msg) > self._max_length:
                display_msg = msg[:self._max_length - 3] + "..."
            lines.append(f"  ↳ {display_msg}")
        
        return "\n".join(lines)
    
    def format_status(self) -> str:
        """
        Format current processing status.
        
        Returns:
            Status string (e.g., "⏳ Processing..." or "")
        """
        if not self._state_manager:
            return ""
        
        state = self._state_manager.current_state
        if state == ProcessingState.PROCESSING:
            return "⏳ Processing..."
        elif state == ProcessingState.WAITING_APPROVAL:
            return "🔒 Waiting for approval..."
        return ""
    
    def format_queue_count(self) -> str:
        """
        Format queue count indicator.
        
        Returns:
            Count string (e.g., "📋 Queued (2)")
        """
        count = self._queue.count
        if count == 0:
            return ""
        return f"📋 Queued ({count})"


# ============================================================================
# MessageQueueHandler - Main handler class
# ============================================================================

class MessageQueueHandler:
    """
    Main handler for message queue functionality.
    
    Coordinates queue, state, and processing.
    """
    
    def __init__(
        self,
        processor: Optional[Callable[[str], str]] = None,
        on_response: Optional[Callable[[str], None]] = None
    ):
        self._processor = processor
        self._on_response = on_response
        self._queue = MessageQueue()
        self._state_manager = StateManager(on_state_change=self._on_state_change)
        self._processing_lock = threading.Lock()
    
    @property
    def queue(self) -> MessageQueue:
        """Get the message queue."""
        return self._queue
    
    @property
    def state_manager(self) -> StateManager:
        """Get the state manager."""
        return self._state_manager
    
    def submit(self, message: str) -> bool:
        """
        Submit a message for processing.
        
        If idle, processes immediately. If processing, queues the message.
        
        Args:
            message: The message to submit
            
        Returns:
            True if processed/queued, False if empty message
        """
        trimmed = message.strip() if message else ""
        if not trimmed:
            return False
        
        if self._state_manager.is_idle:
            # Process immediately
            self._process_message(trimmed)
        else:
            # Queue for later
            self._queue.add(trimmed)
        
        return True
    
    def on_processing_complete(self) -> None:
        """
        Called when current processing completes.
        
        Sets state to idle and processes next queued message if any.
        """
        self._state_manager.set_state(ProcessingState.IDLE)
        self._process_next_in_queue()
    
    def get_status(self) -> dict:
        """
        Get current status.
        
        Returns:
            Dict with queue_count and state
        """
        return {
            'queue_count': self._queue.count,
            'state': self._state_manager.current_state.value,
            'messages': self._queue.get_all()
        }
    
    def clear_queue(self) -> None:
        """Clear all queued messages."""
        self._queue.clear()
    
    def _process_message(self, message: str) -> None:
        """Process a single message."""
        if not self._processor:
            return
        
        with self._processing_lock:
            self._state_manager.set_state(ProcessingState.PROCESSING)
            try:
                response = self._processor(message)
                if self._on_response and response:
                    self._on_response(response)
            finally:
                self._state_manager.set_state(ProcessingState.IDLE)
    
    def _process_next_in_queue(self) -> None:
        """Process the next message in queue if any."""
        next_msg = self._queue.pop()
        if next_msg:
            self._process_message(next_msg)
    
    def _on_state_change(self, old_state: ProcessingState, new_state: ProcessingState) -> None:
        """Handle state changes."""
        # Auto-process queue when becoming idle
        if new_state == ProcessingState.IDLE and old_state == ProcessingState.PROCESSING:
            # Don't auto-process here to avoid recursion
            # The on_processing_complete method handles this
            pass


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    'ProcessingState',
    'MessagePriority',
    'QueuedMessage',
    'MessageQueue',
    'StateManager',
    'QueueDisplay',
    'MessageQueueHandler',
]
