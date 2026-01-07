"""
Tests for the Event Bus module.

TDD: Tests written before implementation verification.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from praisonaiagents.bus import EventBus, Event, EventType, get_default_bus, set_default_bus


class TestEvent:
    """Tests for the Event class."""
    
    def test_event_creation(self):
        """Test basic event creation."""
        event = Event(type="test.event", data={"key": "value"})
        
        assert event.type == "test.event"
        assert event.data == {"key": "value"}
        assert event.id is not None
        assert event.timestamp > 0
    
    def test_event_with_source(self):
        """Test event with source identifier."""
        event = Event(
            type=EventType.SESSION_CREATED.value,
            data={"session_id": "abc123"},
            source="agent_1"
        )
        
        assert event.source == "agent_1"
    
    def test_event_to_dict(self):
        """Test event serialization."""
        event = Event(
            type="test.event",
            data={"key": "value"},
            source="test"
        )
        
        d = event.to_dict()
        
        assert d["type"] == "test.event"
        assert d["data"] == {"key": "value"}
        assert d["source"] == "test"
        assert "id" in d
        assert "timestamp" in d
    
    def test_event_from_dict(self):
        """Test event deserialization."""
        d = {
            "type": "test.event",
            "data": {"key": "value"},
            "source": "test",
            "id": "test-id",
            "timestamp": 1234567890.0
        }
        
        event = Event.from_dict(d)
        
        assert event.type == "test.event"
        assert event.data == {"key": "value"}
        assert event.source == "test"
        assert event.id == "test-id"
        assert event.timestamp == 1234567890.0
    
    def test_event_to_sse(self):
        """Test SSE formatting."""
        event = Event(type="test.event", data={"key": "value"})
        
        sse = event.to_sse()
        
        assert f"id: {event.id}" in sse
        assert "event: test.event" in sse
        assert "data:" in sse


class TestEventBus:
    """Tests for the EventBus class."""
    
    def test_bus_creation(self):
        """Test basic bus creation."""
        bus = EventBus()
        
        assert bus.subscriber_count == 0
    
    def test_subscribe_and_publish(self):
        """Test basic subscribe and publish."""
        bus = EventBus()
        received = []
        
        def handler(event):
            received.append(event)
        
        bus.subscribe(handler)
        bus.publish("test.event", {"key": "value"})
        
        assert len(received) == 1
        assert received[0].type == "test.event"
        assert received[0].data == {"key": "value"}
    
    def test_subscribe_with_filter(self):
        """Test subscribing to specific event types."""
        bus = EventBus()
        received = []
        
        def handler(event):
            received.append(event)
        
        bus.subscribe(handler, event_types=["test.event"])
        
        bus.publish("test.event", {"key": "value"})
        bus.publish("other.event", {"key": "other"})
        
        assert len(received) == 1
        assert received[0].type == "test.event"
    
    def test_subscribe_multiple_types(self):
        """Test subscribing to multiple event types."""
        bus = EventBus()
        received = []
        
        def handler(event):
            received.append(event)
        
        bus.subscribe(handler, event_types=["type.a", "type.b"])
        
        bus.publish("type.a", {})
        bus.publish("type.b", {})
        bus.publish("type.c", {})
        
        assert len(received) == 2
    
    def test_unsubscribe(self):
        """Test unsubscribing."""
        bus = EventBus()
        received = []
        
        def handler(event):
            received.append(event)
        
        sub_id = bus.subscribe(handler)
        bus.publish("test.event", {})
        
        assert len(received) == 1
        
        result = bus.unsubscribe(sub_id)
        assert result is True
        
        bus.publish("test.event", {})
        assert len(received) == 1  # No new events
    
    def test_unsubscribe_invalid_id(self):
        """Test unsubscribing with invalid ID."""
        bus = EventBus()
        
        result = bus.unsubscribe("invalid-id")
        
        assert result is False
    
    def test_on_decorator(self):
        """Test the @bus.on() decorator."""
        bus = EventBus()
        received = []
        
        @bus.on(EventType.SESSION_CREATED)
        def handler(event):
            received.append(event)
        
        bus.publish(EventType.SESSION_CREATED, {"session_id": "abc"})
        
        assert len(received) == 1
    
    def test_on_decorator_multiple_types(self):
        """Test decorator with multiple event types."""
        bus = EventBus()
        received = []
        
        @bus.on(EventType.SESSION_CREATED, EventType.SESSION_UPDATED)
        def handler(event):
            received.append(event)
        
        bus.publish(EventType.SESSION_CREATED, {})
        bus.publish(EventType.SESSION_UPDATED, {})
        bus.publish(EventType.SESSION_DELETED, {})
        
        assert len(received) == 2
    
    def test_publish_returns_event(self):
        """Test that publish returns the event."""
        bus = EventBus()
        
        event = bus.publish("test.event", {"key": "value"})
        
        assert isinstance(event, Event)
        assert event.type == "test.event"
    
    def test_publish_with_enum(self):
        """Test publishing with EventType enum."""
        bus = EventBus()
        received = []
        
        bus.subscribe(lambda e: received.append(e))
        bus.publish(EventType.AGENT_STARTED, {"agent": "test"})
        
        assert len(received) == 1
        assert received[0].type == EventType.AGENT_STARTED.value
    
    def test_event_history(self):
        """Test event history tracking."""
        bus = EventBus()
        
        bus.publish("event.1", {})
        bus.publish("event.2", {})
        bus.publish("event.3", {})
        
        history = bus.get_history()
        
        assert len(history) == 3
        assert history[0].type == "event.1"
        assert history[2].type == "event.3"
    
    def test_event_history_with_filter(self):
        """Test filtered event history."""
        bus = EventBus()
        
        bus.publish("type.a", {})
        bus.publish("type.b", {})
        bus.publish("type.a", {})
        
        history = bus.get_history(event_type="type.a")
        
        assert len(history) == 2
    
    def test_event_history_limit(self):
        """Test event history limit."""
        bus = EventBus()
        
        for i in range(10):
            bus.publish(f"event.{i}", {})
        
        history = bus.get_history(limit=5)
        
        assert len(history) == 5
        assert history[0].type == "event.5"
    
    def test_clear_history(self):
        """Test clearing event history."""
        bus = EventBus()
        
        bus.publish("test.event", {})
        bus.clear_history()
        
        assert len(bus.get_history()) == 0
    
    def test_clear_subscribers(self):
        """Test clearing all subscribers."""
        bus = EventBus()
        
        bus.subscribe(lambda e: None)
        bus.subscribe(lambda e: None)
        
        assert bus.subscriber_count == 2
        
        bus.clear_subscribers()
        
        assert bus.subscriber_count == 0
    
    def test_subscriber_error_handling(self):
        """Test that subscriber errors don't break the bus."""
        bus = EventBus()
        received = []
        
        def bad_handler(event):
            raise ValueError("Test error")
        
        def good_handler(event):
            received.append(event)
        
        bus.subscribe(bad_handler)
        bus.subscribe(good_handler)
        
        # Should not raise
        bus.publish("test.event", {})
        
        # Good handler should still receive event
        assert len(received) == 1


class TestAsyncEventBus:
    """Tests for async event bus functionality."""
    
    @pytest.mark.asyncio
    async def test_async_subscriber(self):
        """Test async subscriber callback."""
        bus = EventBus()
        received = []
        
        async def async_handler(event):
            await asyncio.sleep(0.01)
            received.append(event)
        
        bus.subscribe(async_handler)
        await bus.publish_async("test.event", {"key": "value"})
        
        assert len(received) == 1
    
    @pytest.mark.asyncio
    async def test_mixed_sync_async_subscribers(self):
        """Test mix of sync and async subscribers."""
        bus = EventBus()
        sync_received = []
        async_received = []
        
        def sync_handler(event):
            sync_received.append(event)
        
        async def async_handler(event):
            await asyncio.sleep(0.01)
            async_received.append(event)
        
        bus.subscribe(sync_handler)
        bus.subscribe(async_handler)
        
        await bus.publish_async("test.event", {})
        
        assert len(sync_received) == 1
        assert len(async_received) == 1


class TestDefaultBus:
    """Tests for the global default bus."""
    
    def test_get_default_bus(self):
        """Test getting the default bus."""
        bus = get_default_bus()
        
        assert isinstance(bus, EventBus)
    
    def test_get_default_bus_singleton(self):
        """Test that default bus is a singleton."""
        bus1 = get_default_bus()
        bus2 = get_default_bus()
        
        assert bus1 is bus2
    
    def test_set_default_bus(self):
        """Test setting a custom default bus."""
        original = get_default_bus()
        custom = EventBus()
        
        set_default_bus(custom)
        
        assert get_default_bus() is custom
        
        # Restore original
        set_default_bus(original)


class TestEventType:
    """Tests for EventType enum."""
    
    def test_event_type_values(self):
        """Test that event types have correct values."""
        assert EventType.SESSION_CREATED.value == "session.created"
        assert EventType.MESSAGE_PART_UPDATED.value == "message.part.updated"
        assert EventType.PERMISSION_ASKED.value == "permission.asked"
    
    def test_event_type_in_subscribe(self):
        """Test using EventType in subscribe."""
        bus = EventBus()
        received = []
        
        bus.subscribe(
            lambda e: received.append(e),
            event_types=[EventType.SESSION_CREATED.value]
        )
        
        bus.publish(EventType.SESSION_CREATED, {})
        
        assert len(received) == 1
