"""
Event Bus Module for PraisonAI Agents.

Provides a typed publish/subscribe event system for real-time communication
between components. Extends the existing hooks system with a more general
event-driven architecture.

Features:
- Typed event definitions with dataclass payloads
- Sync and async subscribers
- Event filtering by type
- Global and scoped event buses
- SSE-compatible event streaming

Zero Performance Impact:
- All imports are lazy loaded
- No overhead when not subscribed
- Optional dependency for server features

Usage:
    from praisonaiagents.bus import EventBus, Event
    
    # Create event bus
    bus = EventBus()
    
    # Subscribe to events
    @bus.on("session.created")
    def handle_session(event):
        print(f"Session created: {event.data}")
    
    # Publish events
    bus.publish("session.created", {"session_id": "abc123"})
"""

__all__ = [
    "EventBus",
    "Event",
    "EventType",
    "Subscriber",
    "get_default_bus",
    "set_default_bus",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name == "EventBus":
        from .bus import EventBus
        return EventBus
    
    if name == "Event":
        from .event import Event
        return Event
    
    if name == "EventType":
        from .event import EventType
        return EventType
    
    if name == "Subscriber":
        from .bus import Subscriber
        return Subscriber
    
    if name == "get_default_bus":
        from .bus import get_default_bus
        return get_default_bus
    
    if name == "set_default_bus":
        from .bus import set_default_bus
        return set_default_bus
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
