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

from .._lazy import create_lazy_getattr

__all__ = [
    "EventBus",
    "Event",
    "EventType",
    "Subscriber",
    "get_default_bus",
    "set_default_bus",
    "EventLogProtocol",
    "SqliteEventLog",
]

_LAZY_IMPORTS = {
    "EventBus": ("praisonaiagents.bus.bus", "EventBus"),
    "Event": ("praisonaiagents.bus.event", "Event"),
    "EventType": ("praisonaiagents.bus.event", "EventType"),
    "Subscriber": ("praisonaiagents.bus.bus", "Subscriber"),
    "get_default_bus": ("praisonaiagents.bus.bus", "get_default_bus"),
    "set_default_bus": ("praisonaiagents.bus.bus", "set_default_bus"),
    "EventLogProtocol": ("praisonaiagents.bus.event_log", "EventLogProtocol"),
    "SqliteEventLog": ("praisonaiagents.bus.event_log", "SqliteEventLog"),
}

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)
