"""
Message Queue for PraisonAI Agents.

Provides queuing for agent prompts when agent is busy.
Thread-safe implementation for concurrent access.
"""

import threading
import heapq
import time
import logging
from typing import Optional, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """Message priority levels."""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass(order=True)
class QueuedMessage:
    """A message in the queue with priority and timestamp."""
    priority: int
    timestamp: float = field(compare=False)
    content: Any = field(compare=False)
    metadata: dict = field(default_factory=dict, compare=False)
    
    def __post_init__(self):
        # Negate priority for max-heap behavior (higher priority = lower number in heap)
        self.priority = -self.priority


class AgentMessageQueue:
    """
    Thread-safe message queue for agent prompts.
    
    Supports priority-based ordering and FIFO within same priority.
    
    Usage:
        queue = AgentMessageQueue()
        queue.enqueue("Hello", priority=5)
        queue.enqueue("Urgent!", priority=10)
        
        msg = queue.dequeue()  # Returns "Urgent!" first
    """
    
    def __init__(self, max_size: int = 100):
        """
        Initialize message queue.
        
        Args:
            max_size: Maximum number of messages in queue (0 = unlimited)
        """
        self._queue: List[QueuedMessage] = []
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        self._max_size = max_size
        self._message_count = 0
        
    def enqueue(
        self,
        content: Any,
        priority: int = MessagePriority.NORMAL.value,
        metadata: Optional[dict] = None
    ) -> bool:
        """
        Add a message to the queue.
        
        Args:
            content: Message content
            priority: Message priority (higher = more urgent)
            metadata: Optional metadata dict
            
        Returns:
            True if message was added, False if queue is full
        """
        with self._lock:
            if self._max_size > 0 and len(self._queue) >= self._max_size:
                logger.warning(f"Message queue full (max_size={self._max_size})")
                return False
                
            message = QueuedMessage(
                priority=priority,
                timestamp=time.time(),
                content=content,
                metadata=metadata or {}
            )
            
            heapq.heappush(self._queue, message)
            self._message_count += 1
            self._not_empty.notify()
            
            logger.debug(f"Message enqueued (priority={priority}, queue_size={len(self._queue)})")
            return True
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Any]:
        """
        Remove and return the highest priority message.
        
        Args:
            timeout: Maximum time to wait for a message (None = don't wait)
            
        Returns:
            Message content or None if queue is empty
        """
        with self._not_empty:
            if not self._queue:
                if timeout is not None:
                    self._not_empty.wait(timeout)
                    
            if not self._queue:
                return None
                
            message = heapq.heappop(self._queue)
            logger.debug(f"Message dequeued (queue_size={len(self._queue)})")
            return message.content
    
    def peek(self) -> Optional[Any]:
        """Return the highest priority message without removing it."""
        with self._lock:
            if not self._queue:
                return None
            return self._queue[0].content
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        with self._lock:
            return len(self._queue) == 0
    
    def size(self) -> int:
        """Get current queue size."""
        with self._lock:
            return len(self._queue)
    
    def clear(self) -> int:
        """Clear all messages from queue. Returns number of cleared messages."""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count
    
    def get_all(self) -> List[Any]:
        """Get all messages in priority order without removing them."""
        with self._lock:
            # Sort by priority (remember priority is negated)
            sorted_queue = sorted(self._queue)
            return [msg.content for msg in sorted_queue]
    
    @property
    def total_messages_processed(self) -> int:
        """Total number of messages ever enqueued."""
        return self._message_count


class AsyncAgentMessageQueue:
    """
    Async-compatible message queue for agent prompts.
    
    Wraps AgentMessageQueue with async interface.
    """
    
    def __init__(self, max_size: int = 100):
        self._sync_queue = AgentMessageQueue(max_size=max_size)
        
    async def enqueue(
        self,
        content: Any,
        priority: int = MessagePriority.NORMAL.value,
        metadata: Optional[dict] = None
    ) -> bool:
        """Async enqueue."""
        return self._sync_queue.enqueue(content, priority, metadata)
    
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[Any]:
        """Async dequeue."""
        import asyncio
        
        if timeout is None:
            return self._sync_queue.dequeue(timeout=0)
            
        # Poll with async sleep for timeout
        start = time.time()
        while time.time() - start < timeout:
            result = self._sync_queue.dequeue(timeout=0)
            if result is not None:
                return result
            await asyncio.sleep(0.01)
            
        return None
    
    def is_empty(self) -> bool:
        return self._sync_queue.is_empty()
    
    def size(self) -> int:
        return self._sync_queue.size()
