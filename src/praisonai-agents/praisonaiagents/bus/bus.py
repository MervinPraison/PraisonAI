"""
Event Bus implementation for PraisonAI Agents.

Provides publish/subscribe functionality for typed events.
"""

import asyncio
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set, Union
from dataclasses import dataclass, field
from .event import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class Subscriber:
    """
    A subscriber to the event bus.
    
    Attributes:
        callback: Function to call when event is received
        event_types: Set of event types to subscribe to (None = all)
        is_async: Whether the callback is async
        id: Unique subscriber identifier
    """
    callback: Callable[[Event], Any]
    event_types: Optional[Set[str]] = None
    is_async: bool = False
    id: str = field(default_factory=lambda: str(__import__("uuid").uuid4()))
    
    def matches(self, event_type: str) -> bool:
        """Check if subscriber should receive this event type."""
        if self.event_types is None:
            return True
        return event_type in self.event_types


class EventBus:
    """
    Event bus for publish/subscribe communication.
    
    Thread-safe implementation supporting both sync and async subscribers.
    
    Example:
        bus = EventBus()
        
        # Subscribe with decorator
        @bus.on(EventType.SESSION_CREATED)
        def handle_session(event):
            print(f"Session: {event.data}")
        
        # Subscribe to all events
        bus.subscribe(lambda e: print(e))
        
        # Publish event
        bus.publish(EventType.SESSION_CREATED, {"session_id": "abc"})
    """
    
    def __init__(self):
        """Initialize the event bus."""
        self._subscribers: List[Subscriber] = []
        self._lock = threading.RLock()
        self._event_history: List[Event] = []
        self._max_history = 1000
    
    def subscribe(
        self,
        callback: Callable[[Event], Any],
        event_types: Optional[Union[str, List[str], Set[str]]] = None,
    ) -> str:
        """
        Subscribe to events.
        
        Args:
            callback: Function to call when event is received
            event_types: Optional event type(s) to filter by
            
        Returns:
            Subscriber ID for unsubscribing
        """
        # Normalize event_types to a set
        if event_types is None:
            types_set = None
        elif isinstance(event_types, str):
            types_set = {event_types}
        else:
            types_set = set(event_types)
        
        # Check if callback is async
        is_async = asyncio.iscoroutinefunction(callback)
        
        subscriber = Subscriber(
            callback=callback,
            event_types=types_set,
            is_async=is_async,
        )
        
        with self._lock:
            self._subscribers.append(subscriber)
        
        logger.debug(f"Subscribed {subscriber.id} to {types_set or 'all events'}")
        return subscriber.id
    
    def unsubscribe(self, subscriber_id: str) -> bool:
        """
        Unsubscribe from events.
        
        Args:
            subscriber_id: The subscriber ID returned from subscribe()
            
        Returns:
            True if found and removed, False otherwise
        """
        with self._lock:
            for i, sub in enumerate(self._subscribers):
                if sub.id == subscriber_id:
                    self._subscribers.pop(i)
                    logger.debug(f"Unsubscribed {subscriber_id}")
                    return True
        return False
    
    def on(
        self,
        *event_types: Union[str, EventType],
    ) -> Callable:
        """
        Decorator to subscribe a function to events.
        
        Args:
            event_types: Event type(s) to subscribe to
            
        Returns:
            Decorator function
            
        Example:
            @bus.on(EventType.SESSION_CREATED)
            def handle_session(event):
                print(event.data)
        """
        # Convert EventType enums to strings
        types = {
            t.value if isinstance(t, EventType) else t
            for t in event_types
        } if event_types else None
        
        def decorator(func: Callable[[Event], Any]) -> Callable:
            self.subscribe(func, types)
            return func
        
        return decorator
    
    def publish(
        self,
        event_type: Union[str, EventType],
        data: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """
        Publish an event to all matching subscribers.
        
        Args:
            event_type: The event type
            data: Event payload data
            source: Optional source identifier
            metadata: Optional additional metadata
            
        Returns:
            The published Event object
        """
        # Convert EventType enum to string
        type_str = event_type.value if isinstance(event_type, EventType) else event_type
        
        event = Event(
            type=type_str,
            data=data or {},
            source=source,
            metadata=metadata or {},
        )
        
        return self.publish_event(event)
    
    def publish_event(self, event: Event) -> Event:
        """
        Publish a pre-constructed event.
        
        Args:
            event: The event to publish
            
        Returns:
            The published event
        """
        logger.debug(f"Publishing event: {event.type}")
        
        # Store in history
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            
            # Get matching subscribers
            subscribers = [
                sub for sub in self._subscribers
                if sub.matches(event.type)
            ]
        
        # Dispatch to subscribers
        for sub in subscribers:
            try:
                if sub.is_async:
                    # Schedule async callback
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(sub.callback(event))
                    except RuntimeError:
                        # No running loop, run synchronously
                        asyncio.run(sub.callback(event))
                else:
                    sub.callback(event)
            except Exception as e:
                logger.error(f"Error in subscriber {sub.id}: {e}")
        
        return event
    
    async def publish_async(
        self,
        event_type: Union[str, EventType],
        data: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """
        Async version of publish that awaits all async subscribers.
        
        Args:
            event_type: The event type
            data: Event payload data
            source: Optional source identifier
            metadata: Optional additional metadata
            
        Returns:
            The published Event object
        """
        type_str = event_type.value if isinstance(event_type, EventType) else event_type
        
        event = Event(
            type=type_str,
            data=data or {},
            source=source,
            metadata=metadata or {},
        )
        
        logger.debug(f"Publishing async event: {event.type}")
        
        # Store in history
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            
            subscribers = [
                sub for sub in self._subscribers
                if sub.matches(event.type)
            ]
        
        # Dispatch to subscribers
        tasks = []
        for sub in subscribers:
            try:
                if sub.is_async:
                    tasks.append(sub.callback(event))
                else:
                    sub.callback(event)
            except Exception as e:
                logger.error(f"Error in subscriber {sub.id}: {e}")
        
        # Await all async tasks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return event
    
    def get_history(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """
        Get recent event history.
        
        Args:
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        with self._lock:
            events = self._event_history.copy()
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        return events[-limit:]
    
    def clear_history(self):
        """Clear the event history."""
        with self._lock:
            self._event_history.clear()
    
    def clear_subscribers(self):
        """Remove all subscribers."""
        with self._lock:
            self._subscribers.clear()
    
    @property
    def subscriber_count(self) -> int:
        """Get the number of subscribers."""
        with self._lock:
            return len(self._subscribers)
    
    def __repr__(self) -> str:
        return f"EventBus(subscribers={self.subscriber_count})"


# Global default bus
_default_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_default_bus() -> EventBus:
    """Get the default global event bus."""
    global _default_bus
    with _bus_lock:
        if _default_bus is None:
            _default_bus = EventBus()
        return _default_bus


def set_default_bus(bus: EventBus):
    """Set the default global event bus."""
    global _default_bus
    with _bus_lock:
        _default_bus = bus
