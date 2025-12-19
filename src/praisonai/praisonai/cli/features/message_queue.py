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
# AsyncProcessor - Background processing
# ============================================================================

class AsyncProcessor:
    """
    Runs work functions in background threads.
    
    Allows agent processing to happen asynchronously while
    the main thread remains responsive for user input.
    """
    
    def __init__(
        self,
        on_complete: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        self._on_complete = on_complete
        self._on_status = on_status
        self._on_error = on_error
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
    
    @property
    def is_running(self) -> bool:
        """Check if currently processing."""
        with self._lock:
            return self._running
    
    def start(self, work_fn: Callable[[], str]) -> None:
        """
        Start processing work in background thread.
        
        Args:
            work_fn: Function to execute (should return result string)
        """
        def _worker():
            try:
                with self._lock:
                    self._running = True
                
                result = work_fn()
                
                with self._lock:
                    self._running = False
                
                if self._on_complete:
                    self._on_complete(result)
            except Exception as e:
                with self._lock:
                    self._running = False
                if self._on_error:
                    self._on_error(e)
        
        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()
    
    def update_status(self, status: str) -> None:
        """Update status (can be called from work function)."""
        if self._on_status:
            self._on_status(status)


# ============================================================================
# LiveStatusDisplay - Real-time status display
# ============================================================================

class LiveStatusDisplay:
    """
    Tracks and displays real-time status during processing.
    
    Shows tool calls, command executions, and current status.
    """
    
    def __init__(self):
        self._status = ""
        self._tool_calls: List[dict] = []
        self._commands: List[str] = []
        self._lock = threading.Lock()
    
    @property
    def current_status(self) -> str:
        """Get current status message."""
        with self._lock:
            return self._status
    
    @property
    def tool_calls(self) -> List[dict]:
        """Get list of tool calls."""
        with self._lock:
            return self._tool_calls.copy()
    
    @property
    def commands(self) -> List[str]:
        """Get list of commands executed."""
        with self._lock:
            return self._commands.copy()
    
    def update_status(self, status: str) -> None:
        """Update current status message."""
        with self._lock:
            self._status = status
    
    def add_tool_call(self, name: str, args: dict) -> None:
        """Add a tool call to the display."""
        with self._lock:
            self._tool_calls.append({
                'name': name,
                'args': args,
                'timestamp': time.time()
            })
    
    def add_command(self, command: str) -> None:
        """Add a command execution to the display."""
        with self._lock:
            self._commands.append(command)
    
    def format(self) -> str:
        """Format current status for display."""
        lines = []
        
        with self._lock:
            if self._status:
                lines.append(f"⏳ {self._status}")
            
            for tool in self._tool_calls[-3:]:  # Show last 3 tools
                lines.append(f"  🔧 {tool['name']}")
            
            for cmd in self._commands[-2:]:  # Show last 2 commands
                display_cmd = cmd[:40] + "..." if len(cmd) > 40 else cmd
                lines.append(f"  💻 {display_cmd}")
        
        return "\n".join(lines)
    
    def clear(self) -> None:
        """Clear all status."""
        with self._lock:
            self._status = ""
            self._tool_calls.clear()
            self._commands.clear()


# ============================================================================
# NonBlockingInput - Async input handling
# ============================================================================

class NonBlockingInput:
    """
    Handles user input asynchronously.
    
    Allows users to type new messages while processing is ongoing.
    """
    
    def __init__(self):
        self._queue = MessageQueue()
    
    @property
    def has_pending(self) -> bool:
        """Check if there are pending inputs."""
        return not self._queue.is_empty
    
    @property
    def pending_count(self) -> int:
        """Get number of pending inputs."""
        return self._queue.count
    
    def submit(self, message: str) -> bool:
        """Submit a new input message."""
        return self._queue.add(message)
    
    def pop(self) -> Optional[str]:
        """Get next pending input."""
        return self._queue.pop()
    
    def peek(self) -> Optional[str]:
        """View next pending input without removing."""
        return self._queue.peek()
    
    def get_all(self) -> List[str]:
        """Get all pending inputs."""
        return self._queue.get_all()
    
    def clear(self) -> None:
        """Clear all pending inputs."""
        self._queue.clear()


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
    'AsyncProcessor',
    'LiveStatusDisplay',
    'NonBlockingInput',
]
