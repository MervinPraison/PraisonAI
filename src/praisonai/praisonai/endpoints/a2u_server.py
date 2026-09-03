"""
A2U (Agent-to-User) Event Stream Server

Provides SSE-based event streaming for agent-to-user communication.
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import threading
import uuid
import weakref
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Strong-enough references to in-flight publish tasks so CPython's GC cannot
# collect a fire-and-forget task before it runs. Entries drop out on completion.
_BACKGROUND_TASKS: "weakref.WeakSet" = weakref.WeakSet()

# Bound in-process state so an unauthenticated flood cannot exhaust memory.
def _positive_int_env(name: str, default: int) -> int:
    """Read a positive-int limit from the environment.

    ``asyncio.Queue(maxsize<=0)`` is *unbounded*, so a stray ``0``/``-1`` here
    would silently defeat the memory bound. Fall back to ``default`` on any
    non-positive or unparsable value rather than fail-open into an unbounded
    queue.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s must be a positive integer (got %d); using default %d", name, value, default)
        return default
    return value


_MAX_SUBS = _positive_int_env("PRAISONAI_A2U_MAX_SUBS", 1024)
_QUEUE_MAX = _positive_int_env("PRAISONAI_A2U_QUEUE_MAX", 1000)


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
        # publish_sync runs from *any* thread (see run_sync bridge), so guard the
        # shared dicts with a reentrant lock rather than an asyncio.Lock.
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, A2USubscription] = {}
        # subscription_id -> (queue, owning_loop). The owning loop is the loop
        # that first consumes the subscription (get_events); cross-loop delivery
        # goes through owning_loop.call_soon_threadsafe so an asyncio.Future is
        # only ever mutated on its own loop thread.
        self._queues: Dict[str, tuple] = {}
        # subscription_id -> bounded pre-bind buffer. Events published after
        # subscribe() but before a consumer binds a loop-owned queue (the
        # two-request POST /subscribe → GET /events/sub/{id} flow) land here
        # instead of being dropped, then drain into the queue on first consume.
        # Bounded by _QUEUE_MAX so an idle subscription can't grow without limit.
        self._pending: Dict[str, Deque[A2UEvent]] = {}
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

        with self._lock:
            if len(self._subscriptions) >= _MAX_SUBS:
                raise RuntimeError("A2U subscription limit reached")

            self._subscriptions[subscription_id] = subscription
            # The asyncio.Queue is created lazily in _bind_queue() (the consumer
            # path) — asyncio.Queue() needs a running loop at creation time on
            # Python 3.9, and we must record the *consumer's* loop for safe
            # cross-loop delivery. Until then, a bounded pre-bind buffer holds
            # events so nothing published in the subscribe→consume gap is lost.
            self._pending[subscription_id] = deque(maxlen=_QUEUE_MAX)
            self._streams.setdefault(stream_name, set()).add(subscription_id)
        
        logger.debug(f"Created subscription {subscription_id} for stream {stream_name}")
        return subscription
    
    def _bind_queue(self, subscription_id: str, loop: "asyncio.AbstractEventLoop") -> asyncio.Queue:
        """Get or create the queue for a subscription, binding its owning loop.

        Called only from the consumer path (``get_events``) where a running loop
        exists. The queue and the loop that awaits it are stored together so
        publishers on other threads can hand events over via
        ``call_soon_threadsafe`` instead of mutating a foreign loop's Future.
        Deferred creation also keeps Python 3.9 compatibility (``asyncio.Queue``
        needs a loop at creation time there).
        """
        with self._lock:
            entry = self._queues.get(subscription_id)
            if entry is None:
                queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
                # Drain any events buffered before a consumer attached so the
                # subscribe→consume gap loses nothing. put_nowait is safe here:
                # we hold the running loop (get_events) and the deque is capped
                # at the same bound as the queue.
                pending = self._pending.pop(subscription_id, None)
                if pending:
                    while pending:
                        event = pending.popleft()
                        try:
                            queue.put_nowait(event)
                        except asyncio.QueueFull:
                            logger.warning(
                                "A2U queue full draining buffer for %s — "
                                "dropping event %s",
                                subscription_id, event.event_type,
                            )
                            break
                entry = (queue, loop)
                self._queues[subscription_id] = entry
            return entry[0]
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from an event stream.
        
        Args:
            subscription_id: ID of the subscription to remove
            
        Returns:
            True if unsubscribed, False if not found
        """
        with self._lock:
            subscription = self._subscriptions.pop(subscription_id, None)
            if subscription is None:
                return False

            # Remove from stream set
            self._streams.get(subscription.stream_name, set()).discard(subscription_id)
            self._queues.pop(subscription_id, None)  # May not exist due to lazy creation
            self._pending.pop(subscription_id, None)  # Discard any undrained buffer
        
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
        # Snapshot the target subscriptions + their bound queues under the lock,
        # then deliver outside it so put_nowait cannot race against
        # subscribe/unsubscribe. Buffering into the pre-bind deque happens under
        # the lock so a concurrent _bind_queue drain can't lose the event.
        deferred: List["concurrent.futures.Future"] = []
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        with self._lock:
            sub_ids = list(self._streams.get(stream_name, ()))
            snapshot = {
                sid: (self._subscriptions.get(sid), self._queues.get(sid))
                for sid in sub_ids
            }

            count = 0
            for sub_id, (subscription, entry) in snapshot.items():
                if not (subscription and subscription.matches_event(event)):
                    continue
                if entry is None:
                    # No consumer has bound a loop-owned queue yet. Buffer into
                    # the bounded pre-bind deque so the subscribe→consume gap
                    # loses nothing; _bind_queue drains it on first consume.
                    pending = self._pending.get(sub_id)
                    if pending is not None:
                        pending.append(event)  # deque(maxlen) drops oldest if full
                        count += 1
                    continue
                queue, owner_loop = entry
                if running_loop is owner_loop:
                    # Same loop as the consumer: mutate the Future directly.
                    try:
                        # Non-blocking put with a bounded queue: a slow/stalled
                        # consumer drops events instead of growing memory without
                        # bound (which would let one hung socket OOM the process).
                        queue.put_nowait(event)
                        count += 1
                    except asyncio.QueueFull:
                        logger.warning(
                            "A2U queue full for %s — dropping event %s",
                            sub_id, event.event_type,
                        )
                else:
                    # Cross-loop / cross-thread delivery: schedule the put on the
                    # queue's owning loop so its internal Future is only ever
                    # set_result()'d on its own loop thread. A bare put_nowait
                    # here would call _wakeup_next on a foreign loop's waiter and
                    # either lose the event or raise InvalidStateError.
                    #
                    # A completion Future carries the real outcome back so the
                    # returned count reflects events actually enqueued, not merely
                    # scheduled — a deferred put can still hit QueueFull.
                    done: "concurrent.futures.Future" = concurrent.futures.Future()

                    def _put(q=queue, e=event, sid=sub_id, fut=done):
                        try:
                            q.put_nowait(e)
                            fut.set_result(True)
                        except asyncio.QueueFull:
                            logger.warning(
                                "A2U queue full for %s — dropping event %s",
                                sid, e.event_type,
                            )
                            fut.set_result(False)
                        except BaseException as exc:  # pragma: no cover - defensive
                            fut.set_exception(exc)

                    try:
                        owner_loop.call_soon_threadsafe(_put)
                        deferred.append(done)
                    except RuntimeError:
                        # Owning loop is closed/stopped — consumer is gone.
                        logger.debug("A2U owning loop unavailable for %s", sub_id)

        # Resolve deferred cross-loop puts (outside the lock) so the count is
        # accurate. Wrapping each concurrent.futures.Future keeps publish()
        # non-blocking on its own loop while the puts complete on their owners'.
        for done in deferred:
            try:
                if await asyncio.wrap_future(done):
                    count += 1
            except Exception:
                logger.debug("A2U deferred delivery failed", exc_info=True)

        logger.debug(f"Published event {event.event_type} to {count} subscribers")
        return count
    
    def publish_sync(self, event: A2UEvent, stream_name: str = "events") -> int:
        """
        Synchronously publish an event.

        - Inside a running loop: schedules a *tracked* task (so it cannot be
          GC'd before it runs and its exceptions are not silently lost) and
          returns the number of subscribers targeted. The coroutine's result is
          available via ``last_publish_task()`` for callers needing the real
          delivered count.
        - Outside a loop: blocks until publication completes via the async
          bridge and returns the actual delivered count.

        Args:
            event: Event to publish
            stream_name: Name of the stream

        Returns:
            Number of subscribers (targeted under a running loop, delivered
            otherwise).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — run to completion synchronously via the bridge.
            from .._async_bridge import run_sync
            return run_sync(self.publish(event, stream_name))

        # Running-loop path: schedule + track so the task cannot be GC'd before
        # it runs, and its exceptions cannot be silently lost.
        task = loop.create_task(self.publish(event, stream_name))
        _BACKGROUND_TASKS.add(task)

        def _report(t: "asyncio.Task") -> None:
            _BACKGROUND_TASKS.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.error("A2U publish failed", exc_info=exc)

        task.add_done_callback(_report)
        self._last_publish_task = task
        with self._lock:
            return len(self._streams.get(stream_name, set()))

    def last_publish_task(self) -> Optional["asyncio.Task"]:
        """Return the task from the most recent running-loop publish_sync call."""
        return getattr(self, "_last_publish_task", None)
    
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
        if subscription_id not in self._subscriptions:
            return
        
        queue = self._bind_queue(subscription_id, asyncio.get_running_loop())
        
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=timeout)
                yield event
            except asyncio.TimeoutError:
                # Send keepalive
                yield A2UEvent(event_type="keepalive", data={})


# Global event bus instance
_event_bus_lock = threading.Lock()
_event_bus: Optional[A2UEventBus] = None


def get_event_bus() -> A2UEventBus:
    """Get or create the global event bus."""
    global _event_bus
    if _event_bus is None:
        with _event_bus_lock:
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
    
    def _authenticate_request(request) -> Optional[JSONResponse]:
        """Check bearer token auth when A2U_AUTH_TOKEN is configured.
        
        Returns None if authenticated, or a 401/403 JSONResponse otherwise.
        """
        auth_token = os.environ.get("A2U_AUTH_TOKEN")
        if not auth_token:
            # No token configured. Allow only loopback binds (development);
            # refuse to serve unauthenticated traffic on any public bind so a
            # forgotten env var cannot silently expose the live event stream.
            #
            # The unified server records its chosen bind address in
            # ``PRAISONAI_CALL_BIND_HOST``; honour an explicit
            # ``PRAISONAI_A2U_BIND_HOST`` override first. When neither is set the
            # bind host is unknown — fail closed rather than assuming loopback.
            bind_host = (
                os.getenv("PRAISONAI_A2U_BIND_HOST")
                or os.getenv("PRAISONAI_CALL_BIND_HOST")
            )
            if bind_host is None or bind_host not in {"127.0.0.1", "::1", "localhost"}:
                return JSONResponse(
                    {"error": "A2U_AUTH_TOKEN not configured; "
                              "refusing non-loopback traffic"},
                    status_code=503,
                )
            return None
        
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Authentication required. Set Authorization: Bearer <token>"},
                status_code=401,
            )
        
        import hmac
        provided = auth_header[7:]  # strip "Bearer "
        if not hmac.compare_digest(provided, auth_token):
            return JSONResponse(
                {"error": "Invalid authentication token"},
                status_code=403,
            )
    
    async def a2u_info(request):
        """GET /a2u/info - Get A2U server info."""
        auth_error = _authenticate_request(request)
        if auth_error:
            return auth_error
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
        auth_error = _authenticate_request(request)
        if auth_error:
            return auth_error
        try:
            body = await request.json()
        except Exception:
            body = {}
        
        stream_name = body.get("stream", "events")
        filters = body.get("filters", [])
        
        try:
            subscription = bus.subscribe(stream_name, filters)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=429)
        
        base_url = str(request.url).rsplit("/", 1)[0]
        
        return JSONResponse({
            "subscription_id": subscription.subscription_id,
            "stream_name": subscription.stream_name,
            "stream_url": f"{base_url}/events/{subscription.subscription_id}",
            "created_at": subscription.created_at,
        })
    
    async def a2u_unsubscribe(request):
        """POST /a2u/unsubscribe - Unsubscribe from an event stream."""
        auth_error = _authenticate_request(request)
        if auth_error:
            return auth_error
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
        auth_error = _authenticate_request(request)
        if auth_error:
            return auth_error
        stream_name = request.path_params.get("stream_name", "events")
        
        # Create subscription for this stream
        try:
            subscription = bus.subscribe(stream_name)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=429)
        
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
        auth_error = _authenticate_request(request)
        if auth_error:
            return auth_error
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
        auth_error = _authenticate_request(request)
        if auth_error:
            return auth_error
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
