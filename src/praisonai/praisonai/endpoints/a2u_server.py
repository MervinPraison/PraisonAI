"""
A2U (Agent-to-User) Event Stream Server

Provides SSE-based event streaming for agent-to-user communication.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class A2UEvent:
    """An event in the A2U stream."""
    event_type: str
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    
    def to_sse(self) -> str:
        """Convert to SSE format."""
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\nid: {self.event_id}\n\n"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }


@dataclass
class A2USubscription:
    """A subscription to an A2U event stream."""
    subscription_id: str
    stream_name: str
    filters: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def matches_event(self, event: A2UEvent) -> bool:
        """Check if event matches subscription filters."""
        if not self.filters:
            return True
        return event.event_type in self.filters


class A2UEventBus:
    """
    Event bus for A2U event distribution.
    
    Manages subscriptions and broadcasts events to subscribers.
    """
    
    def __init__(self):
        """Initialize the event bus."""
        self._subscriptions: Dict[str, A2USubscription] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._streams: Dict[str, Set[str]] = {}  # stream_name -> subscription_ids
    
    def subscribe(
        self,
        stream_name: str = "events",
        filters: Optional[List[str]] = None,
    ) -> A2USubscription:
        """
        Subscribe to an event stream.
        
        Args:
            stream_name: Name of the stream to subscribe to
            filters: Optional list of event types to filter
            
        Returns:
            A2USubscription object
        """
        subscription_id = f"sub-{uuid.uuid4().hex[:12]}"
        subscription = A2USubscription(
            subscription_id=subscription_id,
            stream_name=stream_name,
            filters=filters or [],
        )
        
        self._subscriptions[subscription_id] = subscription
        self._queues[subscription_id] = asyncio.Queue()
        
        if stream_name not in self._streams:
            self._streams[stream_name] = set()
        self._streams[stream_name].add(subscription_id)
        
        logger.debug(f"Created subscription {subscription_id} for stream {stream_name}")
        return subscription
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from an event stream.
        
        Args:
            subscription_id: ID of the subscription to remove
            
        Returns:
            True if unsubscribed, False if not found
        """
        if subscription_id not in self._subscriptions:
            return False
        
        subscription = self._subscriptions[subscription_id]
        
        # Remove from stream set
        if subscription.stream_name in self._streams:
            self._streams[subscription.stream_name].discard(subscription_id)
        
        # Clean up
        del self._subscriptions[subscription_id]
        del self._queues[subscription_id]
        
        logger.debug(f"Removed subscription {subscription_id}")
        return True
    
    async def publish(self, event: A2UEvent, stream_name: str = "events") -> int:
        """
        Publish an event to a stream.
        
        Args:
            event: Event to publish
            stream_name: Name of the stream
            
        Returns:
            Number of subscribers that received the event
        """
        if stream_name not in self._streams:
            return 0
        
        count = 0
        for sub_id in self._streams[stream_name]:
            subscription = self._subscriptions.get(sub_id)
            if subscription and subscription.matches_event(event):
                await self._queues[sub_id].put(event)
                count += 1
        
        logger.debug(f"Published event {event.event_type} to {count} subscribers")
        return count
    
    def publish_sync(self, event: A2UEvent, stream_name: str = "events") -> int:
        """
        Synchronously publish an event (creates event loop if needed).
        
        Args:
            event: Event to publish
            stream_name: Name of the stream
            
        Returns:
            Number of subscribers that received the event
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule in running loop
                asyncio.ensure_future(self.publish(event, stream_name))
                return len(self._streams.get(stream_name, set()))
            else:
                return loop.run_until_complete(self.publish(event, stream_name))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.publish(event, stream_name))
    
    async def get_events(
        self,
        subscription_id: str,
        timeout: float = 30.0,
    ):
        """
        Async generator for subscription events.
        
        Args:
            subscription_id: ID of the subscription
            timeout: Timeout for waiting for events
            
        Yields:
            A2UEvent objects
        """
        if subscription_id not in self._queues:
            return
        
        queue = self._queues[subscription_id]
        
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=timeout)
                yield event
            except asyncio.TimeoutError:
                # Send keepalive
                yield A2UEvent(event_type="keepalive", data={})


# Global event bus instance
_event_bus: Optional[A2UEventBus] = None


def get_event_bus() -> A2UEventBus:
    """Get or create the global event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = A2UEventBus()
    return _event_bus


def create_a2u_routes(app: Any, event_bus: Optional[A2UEventBus] = None) -> None:
    """
    Add A2U routes to a FastAPI/Starlette application.
    
    Args:
        app: FastAPI or Starlette application
        event_bus: Optional event bus (uses global if not provided)
    """
    bus = event_bus or get_event_bus()
    
    try:
        from starlette.responses import JSONResponse, StreamingResponse
        from starlette.routing import Route
    except ImportError:
        try:
            from fastapi.responses import JSONResponse, StreamingResponse
        except ImportError:
            raise ImportError("Starlette or FastAPI required for A2U routes")
    
    async def a2u_info(request):
        """GET /a2u/info - Get A2U server info."""
        return JSONResponse({
            "name": "A2U Event Stream",
            "version": "1.0.0",
            "streams": list(bus._streams.keys()) or ["events"],
            "event_types": [
                "agent.started",
                "agent.thinking",
                "agent.tool_call",
                "agent.response",
                "agent.completed",
                "agent.error",
            ],
        })
    
    async def a2u_subscribe(request):
        """POST /a2u/subscribe - Subscribe to an event stream."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        
        stream_name = body.get("stream", "events")
        filters = body.get("filters", [])
        
        subscription = bus.subscribe(stream_name, filters)
        
        base_url = str(request.url).rsplit("/", 1)[0]
        
        return JSONResponse({
            "subscription_id": subscription.subscription_id,
            "stream_name": subscription.stream_name,
            "stream_url": f"{base_url}/events/{subscription.subscription_id}",
            "created_at": subscription.created_at,
        })
    
    async def a2u_unsubscribe(request):
        """POST /a2u/unsubscribe - Unsubscribe from an event stream."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        
        subscription_id = body.get("subscription_id")
        if not subscription_id:
            return JSONResponse({"error": "subscription_id required"}, status_code=400)
        
        if bus.unsubscribe(subscription_id):
            return JSONResponse({"status": "unsubscribed"})
        else:
            return JSONResponse({"error": "Subscription not found"}, status_code=404)
    
    async def a2u_events_stream(request):
        """GET /a2u/events/{stream_name} - Stream events via SSE."""
        stream_name = request.path_params.get("stream_name", "events")
        
        # Create subscription for this stream
        subscription = bus.subscribe(stream_name)
        
        async def event_generator():
            try:
                async for event in bus.get_events(subscription.subscription_id):
                    yield event.to_sse()
            finally:
                bus.unsubscribe(subscription.subscription_id)
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    
    async def a2u_events_subscription(request):
        """GET /a2u/events/sub/{subscription_id} - Stream events for subscription."""
        subscription_id = request.path_params.get("subscription_id")
        
        if subscription_id not in bus._subscriptions:
            return JSONResponse({"error": "Subscription not found"}, status_code=404)
        
        async def event_generator():
            async for event in bus.get_events(subscription_id):
                yield event.to_sse()
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    
    async def a2u_health(request):
        """GET /a2u/health - A2U health check."""
        return JSONResponse({
            "status": "healthy",
            "active_subscriptions": len(bus._subscriptions),
            "active_streams": len(bus._streams),
        })
    
    # Add routes based on app type
    if hasattr(app, 'add_api_route'):
        # FastAPI
        app.add_api_route("/a2u/info", a2u_info, methods=["GET"])
        app.add_api_route("/a2u/subscribe", a2u_subscribe, methods=["POST"])
        app.add_api_route("/a2u/unsubscribe", a2u_unsubscribe, methods=["POST"])
        app.add_api_route("/a2u/events/{stream_name}", a2u_events_stream, methods=["GET"])
        app.add_api_route("/a2u/events/sub/{subscription_id}", a2u_events_subscription, methods=["GET"])
        app.add_api_route("/a2u/health", a2u_health, methods=["GET"])
    elif hasattr(app, 'routes'):
        # Starlette
        app.routes.extend([
            Route("/a2u/info", a2u_info, methods=["GET"]),
            Route("/a2u/subscribe", a2u_subscribe, methods=["POST"]),
            Route("/a2u/unsubscribe", a2u_unsubscribe, methods=["POST"]),
            Route("/a2u/events/{stream_name}", a2u_events_stream, methods=["GET"]),
            Route("/a2u/events/sub/{subscription_id}", a2u_events_subscription, methods=["GET"]),
            Route("/a2u/health", a2u_health, methods=["GET"]),
        ])


# Helper functions for publishing events
def emit_agent_event(
    event_type: str,
    data: Dict[str, Any],
    agent_id: Optional[str] = None,
    stream_name: str = "events",
) -> None:
    """
    Emit an agent event to the A2U stream.
    
    Args:
        event_type: Type of event (e.g., "agent.started", "agent.response")
        data: Event data
        agent_id: Optional agent ID to include
        stream_name: Stream to publish to
    """
    if agent_id:
        data["agent_id"] = agent_id
    
    event = A2UEvent(event_type=event_type, data=data)
    get_event_bus().publish_sync(event, stream_name)


def emit_agent_started(agent_id: str, agent_name: str, **kwargs) -> None:
    """Emit agent.started event."""
    emit_agent_event("agent.started", {"agent_name": agent_name, **kwargs}, agent_id)


def emit_agent_thinking(agent_id: str, message: str = "", **kwargs) -> None:
    """Emit agent.thinking event."""
    emit_agent_event("agent.thinking", {"message": message, **kwargs}, agent_id)


def emit_agent_tool_call(agent_id: str, tool_name: str, arguments: Dict = None, **kwargs) -> None:
    """Emit agent.tool_call event."""
    emit_agent_event("agent.tool_call", {"tool_name": tool_name, "arguments": arguments or {}, **kwargs}, agent_id)


def emit_agent_response(agent_id: str, response: str, **kwargs) -> None:
    """Emit agent.response event."""
    emit_agent_event("agent.response", {"response": response, **kwargs}, agent_id)


def emit_agent_completed(agent_id: str, result: Any = None, **kwargs) -> None:
    """Emit agent.completed event."""
    emit_agent_event("agent.completed", {"result": result, **kwargs}, agent_id)


def emit_agent_error(agent_id: str, error: str, **kwargs) -> None:
    """Emit agent.error event."""
    emit_agent_event("agent.error", {"error": error, **kwargs}, agent_id)
