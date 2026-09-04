"""
Gateway Protocols for PraisonAI Agents.

Defines the interfaces for gateway/control plane implementations.
These protocols enable multi-agent coordination, session management,
and real-time communication.

All implementations live in the ``praisonai-bot`` package (``praisonai_bot.gateway``).
The ``praisonai`` wrapper provides backward-compatible shims.
"""

from __future__ import annotations

import math
import time
import uuid
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    contextmanager,
)
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterator,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    TypedDict,
    Union,
    runtime_checkable,
)

# Gateway protocol versioning constants
GATEWAY_PROTOCOL_VERSION = 1
MIN_CLIENT_PROTOCOL_VERSION = 1

if TYPE_CHECKING:
    import asyncio
    from praisonai.gateway.pairing import PairedChannel
    from ..agent import Agent
    from ..bots.presentation import MessagePresentation
    from ..scheduler.models import DeliveryTarget


class ConnectErrorCode(str, Enum):
    """Structured error codes for connection failures."""
    AUTH_REQUIRED = "auth_required"
    AUTH_UNAUTHORIZED = "auth_unauthorized"
    PROTOCOL_UNSUPPORTED = "protocol_unsupported"
    PAIRING_REQUIRED = "pairing_required"
    AGENT_NOT_FOUND = "agent_not_found"
    RATE_LIMITED = "rate_limited"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"
    CONFIGURATION_ERROR = "configuration_error"


class GatewayCloseCode(str, Enum):
    """Structured, machine-readable reasons for a server-initiated close.

    Distinct from :class:`ConnectErrorCode` (which describes why a *connection*
    was rejected at/handshake time), these describe why an already-established
    connection is being torn down by the server mid-session.

    Codes:
        SLOW_CONSUMER: The client's outbound buffer exceeded the gateway's
            advertised ``max_buffered_bytes`` policy (a genuinely slow/stalled
            consumer). The server evicts it so its backlog cannot grow without
            bound or stall delivery to healthy clients.
        CREDENTIALS_ROTATED: The shared gateway secret this session
            authenticated under is no longer the active secret (an operator
            rotated ``auth_token`` and hot-reloaded, or otherwise revoked it).
            The server force-closes every session stamped with a stale secret
            so a leaked/revoked credential stops working within one reload
            cycle, without a full process restart. Clients should
            re-authenticate (see :attr:`ConnectRecoveryStep.REAUTHENTICATE`)
            and reconnect with fresh credentials rather than backing off as if
            the server were down.
        LIVENESS_TIMEOUT: The connection missed too many application-level
            heartbeats (see :class:`LivenessPolicy`): its ``last_activity``
            exceeded ``interval_ms × missed_beats_before_reap``, so the server
            treats it as a dead/half-open peer and reaps it, releasing the
            session/presence/queue state deterministically. Half-open sockets
            behind NAT/proxies/mobile networks — where the peer has vanished
            but no FIN/RST ever arrives — are the motivating case. Clients
            should reconnect (their own watchdog typically force-reconnects
            first) rather than treating this as a fatal error.
    """

    SLOW_CONSUMER = "slow_consumer"
    CREDENTIALS_ROTATED = "credentials_rotated"
    LIVENESS_TIMEOUT = "liveness_timeout"


class ConnectRecoveryStep(str, Enum):
    """Machine-readable recovery hint for a connection rejection.

    Clients branch on ``(code, next_step)`` to implement deterministic,
    uniform reconnect behaviour without parsing free-text reasons:

        REAUTHENTICATE: Obtain fresh credentials, then reconnect.
        REPAIR:         Re-run the device pairing flow, then reconnect.
        UPGRADE_CLIENT: The client protocol is too old; update the client.
        DOWNGRADE_CLIENT: The client protocol is newer than the server
            supports; use an older client or wait for a server upgrade.
        WAIT_THEN_RETRY: Back off (see ``retry_after_seconds``) then reconnect.
        DO_NOT_RETRY:   The rejection is terminal; reconnecting will not help.
    """

    REAUTHENTICATE = "reauthenticate"
    REPAIR = "repair"
    UPGRADE_CLIENT = "upgrade_client"
    DOWNGRADE_CLIENT = "downgrade_client"
    WAIT_THEN_RETRY = "wait_then_retry"
    DO_NOT_RETRY = "do_not_retry"


# Connect-error codes that are terminal for an auto-reconnecting client: the
# gateway will never accept the same client until an operator intervenes
# (re-auth, re-pair, upgrade), so a reconnect loop must pause rather than
# hammer the server with backoff forever. Everything else is treated as
# transient/recoverable (back off and retry).
_NON_RECOVERABLE_CONNECT_CODES = frozenset({
    ConnectErrorCode.AUTH_REQUIRED,
    ConnectErrorCode.AUTH_UNAUTHORIZED,
    ConnectErrorCode.PROTOCOL_UNSUPPORTED,
    ConnectErrorCode.PAIRING_REQUIRED,
    ConnectErrorCode.AGENT_NOT_FOUND,
    ConnectErrorCode.ORIGIN_NOT_ALLOWED,
    ConnectErrorCode.CONFIGURATION_ERROR,
})


def is_recoverable(code: "ConnectErrorCode | str") -> bool:
    """Classify a connect-error code as recoverable (transient) or terminal.

    A single source of truth shared by the bundled gateway client and any
    alternative client so terminal-versus-transient handling stays consistent.

    Args:
        code: A :class:`ConnectErrorCode` or its string value.

    Returns:
        ``True`` when an auto-reconnecting client should back off and retry
        (e.g. ``RATE_LIMITED``, or an unknown/future code — fail open to
        retry). ``False`` for terminal auth/pairing/protocol/origin/config
        failures (and ``AGENT_NOT_FOUND``, which the server emits with a
        do-not-retry recovery step) where reconnecting will not help until
        an operator intervenes.
    """
    if not isinstance(code, ConnectErrorCode):
        try:
            code = ConnectErrorCode(code)
        except ValueError:
            # Unknown/future codes: fail open so a new terminal code does not
            # silently strand a client — better to retry than to stop wrongly.
            return True
    return code not in _NON_RECOVERABLE_CONNECT_CODES


class EventType(str, Enum):
    """Standard gateway event types."""
    
    # Connection events
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"
    
    # Session events
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_UPDATE = "session_update"
    
    # Agent events
    AGENT_REGISTER = "agent_register"
    AGENT_UNREGISTER = "agent_unregister"
    AGENT_STATUS = "agent_status"
    
    # Message events
    MESSAGE = "message"
    MESSAGE_ACK = "message_ack"
    MESSAGE_ABORT = "message_abort"
    TYPING = "typing"
    
    # Streaming events (relayed from agent's StreamEventEmitter)
    TOKEN_STREAM = "token_stream"
    TOOL_CALL_STREAM = "tool_call_stream"
    REASONING_STREAM = "reasoning_stream"
    TOOL_PROGRESS_STREAM = "tool_progress_stream"
    STREAM_ERROR = "stream_error"
    STREAM_END = "stream_end"
    MODEL_FALLBACK_STREAM = "model_fallback_stream"
    RETRY_STREAM = "retry_stream"
    TODO_STREAM = "todo_stream"
    TOOL_RESULT_STREAM = "tool_result_stream"
    
    # System events
    HEALTH = "health"
    ERROR = "error"
    BROADCAST = "broadcast"

    # Liveness events (application-level heartbeat, transport-agnostic)
    PING = "ping"
    PONG = "pong"
    
    # Push channel events
    CHANNEL_SUBSCRIBE = "channel_subscribe"
    CHANNEL_UNSUBSCRIBE = "channel_unsubscribe"
    CHANNEL_MESSAGE = "channel_message"
    CHANNEL_CREATED = "channel_created"
    CHANNEL_DELETED = "channel_deleted"
    
    # Presence events
    PRESENCE_JOIN = "presence_join"
    PRESENCE_LEAVE = "presence_leave"
    PRESENCE_UPDATE = "presence_update"
    
    # Delivery events
    MESSAGE_NACK = "message_nack"
    DELIVERY_RETRY = "delivery_retry"
    
    # Polling events
    POLL_REQUEST = "poll_request"
    POLL_RESPONSE = "poll_response"
    
    # Handshake events
    HELLO = "hello"
    HELLO_OK = "hello_ok"
    HELLO_ERROR = "hello_error"


class OperatorScope(str, Enum):
    """Operator authorisation scopes for multi-operator Gateway access control.

    These describe *what an authenticated operator is allowed to do*, layered on
    top of (and orthogonal to) authentication. The vocabulary lives in the core
    SDK so that protocol clients and the wrapper Gateway share the same names;
    enforcement happens in the wrapper where requests are dispatched.

    Scopes:
        READ:      View dashboard / receive session transcripts and status.
        WRITE:     Send messages as the agent.
        APPROVALS: Resolve tool-execution approvals (security-sensitive).
        PAIRING:   Approve / revoke device pairing.
        ADMIN:     Channel control (pause / resume / reconnect) and management.
    """

    READ = "read"
    WRITE = "write"
    APPROVALS = "approvals"
    PAIRING = "pairing"
    ADMIN = "admin"

    @classmethod
    def all(cls) -> "List[OperatorScope]":
        """Return every scope (granted by default when no policy is configured)."""
        return list(cls)


@dataclass
class HelloParams:
    """Parameters for initiating a versioned handshake.
    
    Attributes:
        agent_id: The agent to connect to
        protocol_min: Minimum protocol version the client supports
        protocol_max: Maximum protocol version the client supports
        capabilities: Optional list of capability tokens the client supports
        session_id: Optional session to resume
        since: Optional cursor for event replay
    """
    agent_id: str
    protocol_min: int
    protocol_max: int
    capabilities: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    since: Optional[int] = None

    type: str = field(default="hello", init=False)


@dataclass
class HelloResult:
    """Result of a successful handshake negotiation.
    
    Attributes:
        protocol: The negotiated protocol version
        features: Supported methods and events
        policy: Gateway policy limits (max_payload, heartbeat_ms, etc.)
        session_id: The session ID for this connection
        resumed: Whether an existing session was resumed
        cursor: Current event cursor position
    """
    protocol: int
    features: Dict[str, List[str]]  # {"methods": [...], "events": [...]}
    policy: Dict[str, int]  # {"max_payload": ..., "heartbeat_ms": ...}
    session_id: str
    resumed: bool
    cursor: int


@dataclass
class HelloError:
    """Structured connect-rejection envelope.

    Emitted from *every* connection rejection path — both pre-handshake
    transport checks (auth/origin/rate-limit) and handshake negotiation —
    so clients can implement deterministic reconnect logic by branching on
    ``(code, next_step)`` instead of string-matching close reasons.

    Attributes:
        code: Structured, machine-readable error code.
        message: Human-readable error message (display only).
        next_step: Machine-readable recovery hint telling the client what to
            do next (re-authenticate, re-pair, upgrade, wait then retry, ...).
        retry_after_seconds: Optional backoff hint (rate limiting / transient
            unavailability). Only meaningful with ``WAIT_THEN_RETRY``.
        next_action: Deprecated free-text hint, retained for backward
            compatibility. Prefer ``next_step``.
    """
    code: ConnectErrorCode
    message: str
    next_step: Optional[ConnectRecoveryStep] = None
    retry_after_seconds: Optional[int] = None
    next_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a ``hello_error`` wire frame.

        The ``next`` key is preserved for backward compatibility with existing
        clients; ``next_step`` and ``retry_after_seconds`` are the structured
        recovery fields new clients should branch on.
        """
        frame: Dict[str, Any] = {
            "type": "hello_error",
            "code": self.code.value,
            "message": self.message,
        }
        if self.next_step is not None:
            frame["next_step"] = self.next_step.value
        if self.retry_after_seconds is not None:
            frame["retry_after_seconds"] = self.retry_after_seconds
        # Backward-compatible legacy field: fall back to next_step's value.
        # Omitted entirely when there is no recovery hint so clients using
        # strict schema validation or ``if frame["next"]`` are not tripped by
        # an explicit ``null``.
        legacy_next = self.next_action
        if legacy_next is None and self.next_step is not None:
            legacy_next = self.next_step.value
        if legacy_next is not None:
            frame["next"] = legacy_next
        return frame


# ---------------------------------------------------------------------------
# Schema-validated inbound frame codec (Issue #2831)
#
# The gateway is the externally reachable control plane for an agent, yet every
# WebSocket handler used to re-parse raw client frames by hand (``data.get(...)``
# with ad-hoc ``isinstance`` guards). That left malformed/hostile frames handled
# inconsistently, the typed frame contract decorative on inbound, and no single
# source of truth a first-/third-party client SDK could be validated against.
#
# This codec is the missing *validating decode step* at the WebSocket boundary:
# a small, dependency-free validator (no pydantic/jsonschema — core keeps its
# no-heavy-import rule) that turns a raw inbound frame into a typed, discriminated
# object (``HelloParams``/``MessageParams``/``LeaveParams``/``JoinParams``) or
# rejects it deterministically with the existing structured ``HelloError``
# envelope (``code``/``next_step``/``retry_after_seconds``). Handlers then receive
# already-validated objects and stop re-implementing defensive parsing.
#
# It is intentionally *additive*: the wrapper server may migrate to
# ``decode_client_frame`` at its own pace; existing hand-parsers keep working.
# ---------------------------------------------------------------------------


class FrameDecodeError(Exception):
    """Raised when a raw inbound frame fails schema validation.

    Carries a structured :class:`HelloError` so the transport can reject the
    frame deterministically with the existing ``(code, next_step,
    retry_after_seconds)`` contract instead of a per-handler ``try/except`` and
    ad-hoc ``isinstance`` checks. The wrapper server maps ``error.to_dict()``
    onto the outbound ``hello_error`` (or ``error``) frame.

    Attributes:
        error: The structured rejection envelope to send back to the client.
    """

    def __init__(self, error: "HelloError"):
        self.error = error
        super().__init__(error.message)


def _coerce_int(value: Any, *, field_name: str, default: Optional[int] = None) -> int:
    """Coerce a wire value to ``int`` or raise a structured decode error.

    Accepts real integers and integral strings/floats (``"1"``, ``1.0``) since
    JSON transports and hand-rolled clients differ; rejects booleans and
    non-integral values so a malformed frame cannot slip through as ``True``/``1``.
    ``None`` falls back to ``default`` when one is provided.
    """
    if value is None and default is not None:
        return default
    # bool is an int subclass; a boolean protocol version is a malformed frame.
    if isinstance(value, bool):
        raise FrameDecodeError(
            HelloError(
                code=ConnectErrorCode.CONFIGURATION_ERROR,
                message=f"Field '{field_name}' must be an integer, got a boolean",
                next_step=ConnectRecoveryStep.DO_NOT_RETRY,
            )
        )
    try:
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError
            return int(value)
        return int(value)
    except (TypeError, ValueError):
        raise FrameDecodeError(
            HelloError(
                code=ConnectErrorCode.CONFIGURATION_ERROR,
                message=f"Field '{field_name}' must be an integer, got {value!r}",
                next_step=ConnectRecoveryStep.DO_NOT_RETRY,
            )
        ) from None


def _coerce_str_list(value: Any) -> List[str]:
    """Coerce an optional wire value into a ``List[str]``.

    ``None`` / missing becomes an empty list; a non-list (or a list with
    non-string members) is normalised leniently to strings so a slightly
    off-shape ``capabilities`` array never rejects an otherwise valid frame.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _require_str(value: Any, *, field_name: str) -> str:
    """Return ``value`` as a non-empty string or raise a structured error."""
    if not isinstance(value, str) or not value:
        raise FrameDecodeError(
            HelloError(
                code=ConnectErrorCode.CONFIGURATION_ERROR,
                message=f"Field '{field_name}' is required and must be a non-empty string",
                next_step=ConnectRecoveryStep.DO_NOT_RETRY,
            )
        )
    return value


@dataclass
class MessageParams:
    """Validated ``message`` frame — a client turn sent to the agent.

    Completes the typed contract for the advertised ``message`` method so it
    is no longer hand-parsed per handler.

    Attributes:
        content: The message body (text, or a structured payload).
        session_id: Optional session the message belongs to.
        message_id: Optional client-supplied idempotency/correlation id.
        metadata: Optional additional message metadata.
    """

    content: Union[str, Dict[str, Any]]
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    type: str = field(default="message", init=False)

    @classmethod
    def from_frame(cls, data: Dict[str, Any]) -> "MessageParams":
        """Validate a raw ``message`` frame into typed params."""
        content = data.get("content", data.get("text"))
        if content is None or (isinstance(content, str) and content == ""):
            raise FrameDecodeError(
                HelloError(
                    code=ConnectErrorCode.CONFIGURATION_ERROR,
                    message="Field 'content' is required for a 'message' frame",
                    next_step=ConnectRecoveryStep.DO_NOT_RETRY,
                )
            )
        if not isinstance(content, (str, dict)):
            raise FrameDecodeError(
                HelloError(
                    code=ConnectErrorCode.CONFIGURATION_ERROR,
                    message="Field 'content' must be a string or object",
                    next_step=ConnectRecoveryStep.DO_NOT_RETRY,
                )
            )
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return cls(
            content=content,
            session_id=_as_opt_str(data.get("session_id")),
            message_id=_as_opt_str(data.get("message_id")),
            metadata=metadata,
        )


@dataclass
class LeaveParams:
    """Validated ``leave`` frame — a client ending its participation.

    Completes the typed contract for the advertised ``leave`` method.

    Attributes:
        session_id: Optional session the client is leaving.
        reason: Optional human-readable reason (display / logging only).
    """

    session_id: Optional[str] = None
    reason: Optional[str] = None

    type: str = field(default="leave", init=False)

    @classmethod
    def from_frame(cls, data: Dict[str, Any]) -> "LeaveParams":
        """Validate a raw ``leave`` frame into typed params."""
        return cls(
            session_id=_as_opt_str(data.get("session_id")),
            reason=_as_opt_str(data.get("reason")),
        )


@dataclass
class JoinParams:
    """Validated legacy ``join`` frame — the pre-``hello`` handshake.

    Retained so the legacy path shares the same single validating decode step
    instead of its own separate hand-written guards.

    Attributes:
        agent_id: The agent to connect to.
        min_version: Minimum protocol version the client supports.
        max_version: Maximum protocol version the client supports.
        session_id: Optional session to resume.
    """

    agent_id: str
    min_version: int
    max_version: int
    session_id: Optional[str] = None

    type: str = field(default="join", init=False)

    @classmethod
    def from_frame(cls, data: Dict[str, Any]) -> "JoinParams":
        """Validate a raw ``join`` frame into typed params."""
        agent_id = _require_str(data.get("agent_id"), field_name="agent_id")
        min_version = _coerce_int(
            data.get("min_version"), field_name="min_version",
            default=MIN_CLIENT_PROTOCOL_VERSION,
        )
        max_version = _coerce_int(
            data.get("max_version"), field_name="max_version",
            default=GATEWAY_PROTOCOL_VERSION,
        )
        if min_version > max_version:
            raise FrameDecodeError(
                HelloError(
                    code=ConnectErrorCode.PROTOCOL_UNSUPPORTED,
                    message=(
                        f"Invalid version range: min_version ({min_version}) "
                        f"> max_version ({max_version})"
                    ),
                    next_step=ConnectRecoveryStep.UPGRADE_CLIENT,
                )
            )
        return cls(
            agent_id=agent_id,
            min_version=min_version,
            max_version=max_version,
            session_id=_as_opt_str(data.get("session_id")),
        )


def _decode_hello(data: Dict[str, Any]) -> "HelloParams":
    """Validate a raw ``hello`` frame into :class:`HelloParams`.

    Supports both the ``HelloParams`` wire shape (``protocol_min``/``protocol_max``
    as direct fields) and the legacy nested ``protocol: {min, max}`` shape, plus
    the ``capabilities``/``caps`` alias, coercing/validating each once here so
    handlers never re-implement the dual-format branch.
    """
    agent_id = _require_str(data.get("agent_id"), field_name="agent_id")

    if "protocol_min" in data or "protocol_max" in data:
        client_min = _coerce_int(
            data.get("protocol_min"), field_name="protocol_min",
            default=MIN_CLIENT_PROTOCOL_VERSION,
        )
        client_max = _coerce_int(
            data.get("protocol_max"), field_name="protocol_max",
            default=GATEWAY_PROTOCOL_VERSION,
        )
    else:
        protocol_info = data.get("protocol")
        if isinstance(protocol_info, dict):
            client_min = _coerce_int(
                protocol_info.get("min"), field_name="protocol.min",
                default=MIN_CLIENT_PROTOCOL_VERSION,
            )
            client_max = _coerce_int(
                protocol_info.get("max"), field_name="protocol.max",
                default=GATEWAY_PROTOCOL_VERSION,
            )
        else:
            client_min = MIN_CLIENT_PROTOCOL_VERSION
            client_max = GATEWAY_PROTOCOL_VERSION

    if client_min > client_max:
        raise FrameDecodeError(
            HelloError(
                code=ConnectErrorCode.PROTOCOL_UNSUPPORTED,
                message=(
                    f"Invalid version range: protocol_min ({client_min}) "
                    f"> protocol_max ({client_max})"
                ),
                next_step=ConnectRecoveryStep.UPGRADE_CLIENT,
            )
        )

    capabilities = _coerce_str_list(data.get("capabilities", data.get("caps")))

    since = data.get("since")
    if since is not None:
        since = _coerce_int(since, field_name="since")

    return HelloParams(
        agent_id=agent_id,
        protocol_min=client_min,
        protocol_max=client_max,
        capabilities=capabilities,
        session_id=_as_opt_str(data.get("session_id")),
        since=since,
    )


# Discriminated union of the validated inbound frame types the gateway accepts.
ClientFrame = Union["HelloParams", MessageParams, LeaveParams, JoinParams]


def decode_client_frame(data: Dict[str, Any]) -> ClientFrame:
    """Validate a raw inbound frame into a typed, discriminated client frame.

    This is the single source of truth for the gateway wire contract: it
    decodes every advertised inbound method (``hello``, ``message``, ``leave``)
    and the legacy ``join`` handshake into a validated dataclass, or raises
    :class:`FrameDecodeError` carrying a structured :class:`HelloError` for the
    transport to reject with. Field coercion/validation happens once, here, at
    the WebSocket boundary — handlers receive already-typed objects.

    Args:
        data: The raw, JSON-decoded inbound frame (discriminated on ``type``).

    Returns:
        A validated :class:`HelloParams`, :class:`MessageParams`,
        :class:`LeaveParams`, or :class:`JoinParams`.

    Raises:
        FrameDecodeError: When ``data`` is not a mapping, carries an unknown /
            missing ``type``, or fails per-frame validation. The attached
            :class:`HelloError` is safe to serialise straight back to the client.
    """
    if not isinstance(data, dict):
        raise FrameDecodeError(
            HelloError(
                code=ConnectErrorCode.CONFIGURATION_ERROR,
                message="Inbound frame must be a JSON object",
                next_step=ConnectRecoveryStep.DO_NOT_RETRY,
            )
        )

    msg_type = data.get("type")
    if not isinstance(msg_type, str) or not msg_type:
        raise FrameDecodeError(
            HelloError(
                code=ConnectErrorCode.CONFIGURATION_ERROR,
                message="Frame 'type' is required and must be a non-empty string",
                next_step=ConnectRecoveryStep.DO_NOT_RETRY,
            )
        )

    if msg_type == "hello":
        return _decode_hello(data)
    if msg_type == "message":
        return MessageParams.from_frame(data)
    if msg_type == "leave":
        return LeaveParams.from_frame(data)
    if msg_type == "join":
        return JoinParams.from_frame(data)

    raise FrameDecodeError(
        HelloError(
            code=ConnectErrorCode.CONFIGURATION_ERROR,
            message=f"Unknown frame type: {msg_type!r}",
            next_step=ConnectRecoveryStep.DO_NOT_RETRY,
        )
    )


@dataclass
class GatewayEvent:
    """A gateway event with metadata.
    
    Attributes:
        type: The event type
        data: Event payload
        event_id: Unique event identifier
        timestamp: Event creation time
        source: Source identifier (agent_id, client_id, etc.)
        target: Target identifier (optional, for directed events)
        sequence: Monotonic sequence number for gap detection (optional)
    
    Wire Protocol Extensions:
        When events are sent over the gateway, additional fields are added:
        - seq: Top-level monotonic sequence number for gap detection
        - cursor: Event cursor position (also stored in data['cursor'])
        
    Resume Protocol:
        The 'joined' acknowledgment includes:
        - cursor: Current head cursor position
        - oldest_cursor: Oldest event still in buffer
        - resync_required: True if requested 'since' is below oldest_cursor
        
        When resync_required=true, a 'snapshot' message follows with full state.
    """
    
    type: Union[EventType, str]
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    target: Optional[str] = None
    sequence: Optional[int] = None  # Monotonic sequence for gap detection
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "data": self.data,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "target": self.target,
        }
        if self.sequence is not None:
            result["sequence"] = self.sequence
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayEvent":
        """Create from dictionary."""
        event_type = data.get("type", "message")
        try:
            event_type = EventType(event_type)
        except ValueError:
            pass  # Keep as string for custom event types
        
        return cls(
            type=event_type,
            data=data.get("data", {}),
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            source=data.get("source"),
            target=data.get("target"),
            sequence=data.get("sequence"),
        )


@dataclass
class GatewayMessage:
    """A message sent through the gateway.
    
    Attributes:
        content: Message content (text or structured data)
        sender_id: Sender identifier
        session_id: Session this message belongs to
        message_id: Unique message identifier
        timestamp: Message creation time
        metadata: Additional message metadata
        reply_to: ID of message being replied to (optional)
        presentation: Optional interactive presentation (buttons, menus, etc.)
    """
    
    content: Union[str, Dict[str, Any]]
    sender_id: str
    session_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None
    presentation: Optional["MessagePresentation"] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {
            "content": self.content,
            "sender_id": self.sender_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "reply_to": self.reply_to,
        }
        if self.presentation is not None:
            data["presentation"] = self.presentation.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayMessage":
        """Create from dictionary."""
        from ..bots.presentation import MessagePresentation
        
        presentation = None
        raw_presentation = data.get("presentation")
        if isinstance(raw_presentation, dict):
            presentation = MessagePresentation.from_dict(raw_presentation)
        
        return cls(
            content=data.get("content", ""),
            sender_id=data.get("sender_id", "unknown"),
            session_id=data.get("session_id", "default"),
            message_id=data.get("message_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            reply_to=data.get("reply_to"),
            presentation=presentation,
        )


@runtime_checkable
class GatewaySessionProtocol(Protocol):
    """Protocol for gateway session management.
    
    Sessions track conversations between clients and agents,
    maintaining state and message history.
    """
    
    @property
    def session_id(self) -> str:
        """Unique session identifier."""
        ...
    
    @property
    def agent_id(self) -> Optional[str]:
        """ID of the agent handling this session."""
        ...
    
    @property
    def client_id(self) -> Optional[str]:
        """ID of the client in this session."""
        ...
    
    @property
    def is_active(self) -> bool:
        """Whether the session is currently active."""
        ...
    
    @property
    def created_at(self) -> float:
        """Session creation timestamp."""
        ...
    
    @property
    def last_activity(self) -> float:
        """Last activity timestamp."""
        ...
    
    def get_state(self) -> Dict[str, Any]:
        """Get session state."""
        ...
    
    def set_state(self, key: str, value: Any) -> None:
        """Set a session state value."""
        ...
    
    def add_message(self, message: GatewayMessage) -> None:
        """Add a message to the session history."""
        ...
    
    def get_messages(self, limit: Optional[int] = None) -> List[GatewayMessage]:
        """Get session message history."""
        ...
    
    def close(self) -> None:
        """Close the session."""
        ...


@runtime_checkable
class GatewayClientProtocol(Protocol):
    """Protocol for gateway client connections.
    
    Clients are external connections (WebSocket, HTTP, etc.)
    that communicate with agents through the gateway.
    """
    
    @property
    def client_id(self) -> str:
        """Unique client identifier."""
        ...
    
    @property
    def is_connected(self) -> bool:
        """Whether the client is currently connected."""
        ...
    
    @property
    def connected_at(self) -> float:
        """Connection timestamp."""
        ...
    
    async def send(self, event: GatewayEvent) -> None:
        """Send an event to the client."""
        ...
    
    async def receive(self) -> GatewayEvent:
        """Receive an event from the client."""
        ...
    
    async def close(self) -> None:
        """Close the client connection."""
        ...


@runtime_checkable
class GatewayProtocol(Protocol):
    """Protocol for gateway/control plane implementations.
    
    The gateway coordinates communication between clients and agents,
    manages sessions, and provides health/presence tracking.
    
    Example usage (implementation in praisonai_bot.gateway):
        from praisonai.gateway import WebSocketGateway
        
        gateway = WebSocketGateway(port=8765)
        gateway.register_agent(my_agent)
        await gateway.start()
    """
    
    @property
    def is_running(self) -> bool:
        """Whether the gateway is currently running."""
        ...
    
    @property
    def port(self) -> int:
        """Port the gateway is listening on."""
        ...
    
    @property
    def host(self) -> str:
        """Host the gateway is bound to."""
        ...
    
    # Lifecycle methods
    async def start(self) -> None:
        """Start the gateway server."""
        ...
    
    async def stop(self) -> None:
        """Stop the gateway server."""
        ...
    
    # Agent management
    def register_agent(self, agent: "Agent", agent_id: Optional[str] = None) -> str:
        """Register an agent with the gateway.
        
        Args:
            agent: The agent to register
            agent_id: Optional custom agent ID
            
        Returns:
            The agent ID (generated if not provided)
        """
        ...
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the gateway.
        
        Args:
            agent_id: The agent ID to unregister
            
        Returns:
            True if agent was unregistered, False if not found
        """
        ...
    
    def get_agent(self, agent_id: str) -> Optional["Agent"]:
        """Get a registered agent by ID."""
        ...
    
    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        ...
    
    # Session management
    def create_session(
        self,
        agent_id: str,
        client_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GatewaySessionProtocol:
        """Create a new session.
        
        Args:
            agent_id: The agent to handle this session
            client_id: Optional client ID
            session_id: Optional custom session ID
            
        Returns:
            The created session
        """
        ...
    
    def get_session(self, session_id: str) -> Optional[GatewaySessionProtocol]:
        """Get a session by ID."""
        ...
    
    def close_session(self, session_id: str) -> bool:
        """Close a session.
        
        Args:
            session_id: The session ID to close
            
        Returns:
            True if session was closed, False if not found
        """
        ...
    
    def list_sessions(self, agent_id: Optional[str] = None) -> List[str]:
        """List session IDs, optionally filtered by agent."""
        ...
    
    # Event handling
    def on_event(self, event_type: Union[EventType, str]) -> Callable:
        """Decorator to register an event handler.
        
        Example:
            @gateway.on_event(EventType.MESSAGE)
            async def handle_message(event: GatewayEvent):
                print(f"Message: {event.data}")
        """
        ...
    
    async def emit(self, event: GatewayEvent) -> None:
        """Emit an event to registered handlers."""
        ...
    
    async def broadcast(
        self,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Broadcast an event to all connected clients.
        
        Args:
            event: The event to broadcast
            exclude: Optional list of client IDs to exclude
        """
        ...
    
    # Health and status
    def health(self) -> Dict[str, Any]:
        """Get gateway health status.
        
        Returns:
            Health information including:
            - status: "healthy" or "unhealthy"
            - uptime: Seconds since start
            - agents: Number of registered agents
            - sessions: Number of active sessions
            - clients: Number of connected clients
            - reload: Optional :class:`ReloadStatus` dict (config hot-reload
              outcome + watcher liveness), when the gateway runs from a config
              file. See :class:`ReloadStatus`.
            - applied_config_revision: Optional stable revision id (see
              :func:`compute_config_revision`) of the config the gateway is
              *actually running*, comparable against the on-disk revision to
              detect drift.
            - pressure: Optional :class:`HealthPressure` dict (admission /
              inbound / outbound backlog + event-loop lag and a derived
              ``pressure`` classification), when the gateway runs back-pressure
              machinery. See :class:`HealthPressure` and :func:`evaluate_pressure`.
        """
        ...


# ---------------------------------------------------------------------------
# Config hot-reload observability (Issue #3049)
#
# The gateway supports diff-driven hot-reload of ``gateway.yaml`` (config
# watcher, SIGHUP, selective restart, drain), but the *outcome* of a reload is
# invisible to operators: a failed reload is swallowed into a log line, the
# watcher can silently degrade, and there is no applied-config revision to
# compare against what is on disk. This is the small, canonical contract that
# both the SDK's ``gateway.health()`` and the bot's ``/health`` populate so
# reload outcome and config drift are first-class, observable signals rather
# than log-scraping. Core owns only the *shape* (a frozen dataclass) and a
# pure, deterministic revision hash; the wrapper server records the outcome and
# computes the revision.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReloadStatus:
    """Observable outcome of the gateway's config hot-reload machinery.

    Populated by the running gateway and surfaced in :meth:`GatewayProtocol.health`
    so an operator can ask "did my last config edit take effect, and is
    hot-reload still working?" without restarting or scraping logs.

    Attributes:
        watcher: ``"active"`` while the config watcher is running (event-driven
            or polling), ``"disabled"`` once it has genuinely given up — so
            silent degradation is detectable rather than assumed-working.
        last_result: Outcome of the most recent reload attempt — ``"ok"``,
            ``"failed"``, ``"no_changes"``, or ``"never"`` (no reload attempted
            yet this run).
        last_at: Unix timestamp of the last reload attempt, or ``None`` when
            none has occurred.
        changed_paths: The config paths that changed on the last successful
            reload (empty otherwise).
        error: On ``"failed"``, the human-readable reason the edit was
            rejected; ``None`` otherwise.
    """

    watcher: Literal["active", "disabled"] = "disabled"
    last_result: Literal["ok", "failed", "no_changes", "never"] = "never"
    last_at: Optional[float] = None
    changed_paths: Tuple[str, ...] = ()
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict for the health surface."""
        return {
            "watcher": self.watcher,
            "last_result": self.last_result,
            "last_at": self.last_at,
            "changed_paths": list(self.changed_paths),
            "error": self.error,
        }


def compute_config_revision(config: Optional[Dict[str, Any]]) -> str:
    """Return a stable, short revision id for a gateway config mapping.

    Deterministic hash over the *canonical* form of ``config`` (keys sorted,
    whitespace-insensitive) so the same logical config always yields the same
    revision regardless of key ordering or formatting. Comparing the revision
    of the running config against the revision of what is on disk gives a
    first-class config-drift signal ("did my change take effect / is a restart
    still owed?").

    Pure and dependency-free (stdlib ``json`` + ``hashlib``) so it lives in
    core and is reused by both the SDK and the bot without divergence.

    Args:
        config: The parsed gateway config mapping (or ``None``/empty).

    Returns:
        A 12-character hex revision id; a stable sentinel for an empty config.
    """
    import hashlib
    import json

    if not config:
        return "0" * 12
    try:
        canonical = json.dumps(
            config, sort_keys=True, separators=(",", ":"), default=str
        )
    except (TypeError, ValueError):
        # Fall back to a repr so an un-JSON-able config still hashes stably
        # rather than raising into the reload/health path.
        canonical = repr(config)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Saturation / back-pressure observability (Issue #4265)
#
# The always-on gateway already *enforces* back-pressure — a concurrency
# ceiling with a bounded fair wait-queue (``AdmissionGate``), a durable
# outbound outbox with a dead-letter tier (``OutboundQueue``), and an
# event-loop wedge watchdog (``LoopWatchdog``) — but it exposes no saturation
# *telemetry*. The health surface reports liveness and config drift, yet never
# reports how close the gateway is to its limits, so the first signal an
# operator gets is dropped work (shed turns / stalled outbound) rather than a
# forward warning. This is the small, canonical contract — mirroring
# ``ReloadStatus`` exactly — that both the SDK's ``gateway.health()`` and the
# bot's ``/health`` populate so saturation is a first-class, observable signal.
# Core owns only the *shape* (a frozen dataclass) and a pure, deterministic
# classification helper; the wrapper reads back the facts the enforcement layer
# already computes and fills the block.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthPressure:
    """Observable saturation snapshot of the gateway's back-pressure machinery.

    Populated by the running gateway and surfaced in
    :meth:`GatewayProtocol.health` so an operator (or an autoscaler / a
    ``/ready``-driven load balancer) can ask "is the gateway backing up?"
    *before* admission starts shedding turns — rather than inferring overload
    post-mortem from shed-load log lines.

    Attributes:
        admission_max: Configured concurrency ceiling (``0`` when unbounded).
        admission_in_flight: Turns currently running.
        admission_queued: Turns currently waiting for a slot.
        admission_shed_total: Cumulative turns shed since start.
        inbox_pending: Aggregate pending inbound queue depth across sessions.
        outbox_pending: Durable outbound backlog awaiting delivery.
        outbox_dead_letter: Durable outbound entries in the dead-letter tier.
        event_loop_lag_p99_ms: Recent event-loop scheduling lag (ms).
        pressure: Single derived classification — ``"nominal"``,
            ``"elevated"`` or ``"saturated"`` (closed vocabulary) — so an
            orchestrator can branch on one field.
    """

    admission_max: int = 0
    admission_in_flight: int = 0
    admission_queued: int = 0
    admission_shed_total: int = 0
    inbox_pending: int = 0
    outbox_pending: int = 0
    outbox_dead_letter: int = 0
    event_loop_lag_p99_ms: float = 0.0
    pressure: Literal["nominal", "elevated", "saturated"] = "nominal"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict for the health surface."""
        return {
            "admission_max": self.admission_max,
            "admission_in_flight": self.admission_in_flight,
            "admission_queued": self.admission_queued,
            "admission_shed_total": self.admission_shed_total,
            "inbox_pending": self.inbox_pending,
            "outbox_pending": self.outbox_pending,
            "outbox_dead_letter": self.outbox_dead_letter,
            "event_loop_lag_p99_ms": self.event_loop_lag_p99_ms,
            "pressure": self.pressure,
        }


def evaluate_pressure(
    *,
    admission: Optional[Dict[str, Any]] = None,
    inbox_pending: int = 0,
    outbox_pending: int = 0,
    outbox_dead_letter: int = 0,
    loop_lag_p99_ms: float = 0.0,
) -> HealthPressure:
    """Pure, deterministic classification of gateway load. No I/O.

    Reads back facts the enforcement layer already computes
    (``AdmissionGate.stats()``, the outbox ``status`` counts, the watchdog's
    measured lag) and folds them into a single :class:`HealthPressure`. Lives
    in core — like :func:`compute_config_revision` — so the SDK and the bot
    classify identically without divergence.

    Classification (highest wins):

    * ``"saturated"`` — admission is full *and* work is queuing, the outbound
      dead-letter tier is non-empty, or the event loop is lagging badly
      (``>= 500 ms``): shed / stall is imminent or occurring.
    * ``"elevated"`` — admission is highly utilised (``>= 80 %``), the inbound
      or outbound backlog is building, or the loop is lagging (``>= 100 ms``).
    * ``"nominal"`` — none of the above.

    Args:
        admission: An :meth:`AdmissionGate.stats` snapshot (or ``None``).
        inbox_pending: Aggregate pending inbound queue depth.
        outbox_pending: Durable outbound backlog.
        outbox_dead_letter: Durable outbound dead-letter depth.
        loop_lag_p99_ms: Recent event-loop scheduling lag in ms.

    Returns:
        A frozen :class:`HealthPressure` ready for the health surface.
    """
    stats = admission or {}

    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    admission_max = _int(stats.get("max_concurrent_runs"))
    in_flight = _int(stats.get("in_flight"))
    queued = _int(stats.get("queued"))
    shed_total = _int(stats.get("shed"))
    inbox = max(0, _int(inbox_pending))
    outbox = max(0, _int(outbox_pending))
    dead_letter = max(0, _int(outbox_dead_letter))
    try:
        lag = float(loop_lag_p99_ms or 0.0)
    except (TypeError, ValueError):
        lag = 0.0
    if lag < 0.0:
        lag = 0.0

    utilisation = (in_flight / admission_max) if admission_max > 0 else 0.0

    saturated = (
        (admission_max > 0 and in_flight >= admission_max and queued > 0)
        or dead_letter > 0
        or lag >= 500.0
    )
    elevated = (
        utilisation >= 0.8
        or queued > 0
        or inbox > 0
        or outbox > 0
        or lag >= 100.0
    )
    if saturated:
        pressure: Literal["nominal", "elevated", "saturated"] = "saturated"
    elif elevated:
        pressure = "elevated"
    else:
        pressure = "nominal"

    return HealthPressure(
        admission_max=admission_max,
        admission_in_flight=in_flight,
        admission_queued=queued,
        admission_shed_total=shed_total,
        inbox_pending=inbox,
        outbox_pending=outbox,
        outbox_dead_letter=dead_letter,
        event_loop_lag_p99_ms=lag,
        pressure=pressure,
    )


# ---------------------------------------------------------------------------
# Push notification dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ChannelInfo:
    """Metadata about a push channel/topic.
    
    Attributes:
        name: Channel name (unique identifier)
        created_at: Channel creation timestamp
        metadata: Arbitrary channel metadata
        subscriber_count: Current number of subscribers
    """
    
    name: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    subscriber_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "subscriber_count": self.subscriber_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChannelInfo":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
            subscriber_count=data.get("subscriber_count", 0),
        )


@dataclass
class PresenceInfo:
    """Presence information for a connected client.
    
    Attributes:
        client_id: Client identifier
        status: Presence status ("online", "idle", "offline")
        last_seen: Last heartbeat timestamp
        metadata: Client-provided metadata (e.g., display name)
        channels: Channels this client is subscribed to
    """
    
    client_id: str
    status: str = "online"
    last_seen: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    channels: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "client_id": self.client_id,
            "status": self.status,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
            "channels": self.channels,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresenceInfo":
        """Create from dictionary."""
        return cls(
            client_id=data.get("client_id", ""),
            status=data.get("status", "online"),
            last_seen=data.get("last_seen", time.time()),
            metadata=data.get("metadata", {}),
            channels=data.get("channels", []),
        )


# ---------------------------------------------------------------------------
# Push notification protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class PushChannelProtocol(Protocol):
    """Protocol for channel/topic-based push messaging.
    
    Channels group clients by interest. Messages published to a channel
    are delivered to all subscribed clients.
    """
    
    def add_channel(
        self, channel_name: str, metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a named channel.
        
        Args:
            channel_name: Unique channel name
            metadata: Optional channel metadata
            
        Returns:
            True if created, False if already exists
        """
        ...
    
    def remove_channel(self, channel_name: str) -> bool:
        """Delete a channel and unsubscribe all clients.
        
        Returns:
            True if removed, False if not found
        """
        ...
    
    def get_channel(self, channel_name: str) -> Optional[ChannelInfo]:
        """Get channel metadata."""
        ...
    
    def list_channels(self) -> List[str]:
        """List all active channel names."""
        ...
    
    def subscribe_client(self, client_id: str, channel_name: str) -> bool:
        """Subscribe a client to a channel.
        
        Returns:
            True if subscribed, False if already subscribed or channel missing
        """
        ...
    
    def unsubscribe_client(self, client_id: str, channel_name: str) -> bool:
        """Unsubscribe a client from a channel.
        
        Returns:
            True if unsubscribed, False if not subscribed
        """
        ...
    
    def get_subscribers(self, channel_name: str) -> List[str]:
        """List client IDs subscribed to a channel."""
        ...
    
    def get_client_channels(self, client_id: str) -> List[str]:
        """List channels a client is subscribed to."""
        ...
    
    async def publish_to_channel(
        self,
        channel_name: str,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> int:
        """Publish an event to all subscribers of a channel.
        
        Args:
            channel_name: Target channel
            event: The event to deliver
            exclude: Optional client IDs to skip
            
        Returns:
            Number of clients the event was sent to
        """
        ...


@runtime_checkable
class PresenceProtocol(Protocol):
    """Protocol for tracking client presence (online/idle/offline)."""
    
    async def track_presence(
        self,
        client_id: str,
        status: str = "online",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Set or update a client's presence status.
        
        Args:
            client_id: Client identifier
            status: Presence status ("online", "idle", "offline")
            metadata: Optional client metadata
        """
        ...
    
    async def remove_presence(self, client_id: str) -> None:
        """Remove a client's presence (on disconnect)."""
        ...
    
    def get_presence(self, client_id: str) -> Optional[PresenceInfo]:
        """Get a single client's presence info."""
        ...
    
    def get_all_presence(
        self, channel_name: Optional[str] = None,
    ) -> List[PresenceInfo]:
        """Get presence info, optionally filtered by channel.
        
        Args:
            channel_name: If provided, only return presence for channel members
        """
        ...
    
    def get_online_count(self, channel_name: Optional[str] = None) -> int:
        """Count online clients, optionally filtered by channel."""
        ...


@runtime_checkable
class DeliveryGuaranteeProtocol(Protocol):
    """Protocol for at-least-once message delivery.
    
    Messages are stored, tracked, and retried until acknowledged.
    """
    
    async def store_message(self, event: GatewayEvent) -> str:
        """Persist a message to the store.
        
        Returns:
            The event_id of the stored message
        """
        ...
    
    async def acknowledge(self, client_id: str, event_id: str) -> bool:
        """Mark a message as acknowledged by a client.
        
        Returns:
            True if found and acknowledged, False if not found
        """
        ...
    
    async def nack(self, client_id: str, event_id: str) -> None:
        """Negative acknowledge - request redelivery."""
        ...
    
    async def get_unacknowledged(
        self, client_id: str, limit: int = 100,
    ) -> List[GatewayEvent]:
        """Get pending unacknowledged messages for a client."""
        ...
    
    async def retry_unacknowledged(self, client_id: str) -> int:
        """Redeliver all unacknowledged messages to a client.
        
        Returns:
            Number of messages redelivered
        """
        ...
    
    async def purge_acknowledged(self, max_age_seconds: int = 86400) -> int:
        """Remove old acknowledged messages from the store.
        
        Returns:
            Number of messages purged
        """
        ...


@runtime_checkable
class OutboundDeliveryProtocol(Protocol):
    """Protocol for durable outbound message delivery.
    
    Ensures messages sent to external channels (Telegram, Slack, Discord, etc.)
    are persisted before sending and can be retried on failure. This provides
    crash-safe at-least-once delivery for channel replies.
    
    Example usage (implementation in praisonai_bot.gateway):
        from praisonai.bots import OutboundQueue
        
        outbox = OutboundQueue(path="~/.praisonai/state/outbox.sqlite")
        
        # Enqueue before sending
        key = await outbox.enqueue(
            idempotency_key="msg-123",
            target_channel="telegram:12345",
            payload={"text": "Hello", "metadata": {...}}
        )
        
        # Attempt delivery
        success = await deliver_with_retry(adapter, channel_id, payload)
        
        # Mark as sent only if successful
        if success:
            await outbox.mark_sent(key)
        
        # On restart, drain pending messages
        await outbox.drain(delivery_handler)
    """
    
    async def enqueue(
        self,
        idempotency_key: str,
        target: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist an outbound message for delivery.
        
        Args:
            idempotency_key: Unique key to prevent duplicate sends
            target: Target channel identifier (e.g., "telegram:12345")
            payload: Message payload to deliver
            metadata: Optional metadata for tracking/routing
            
        Returns:
            Unique entry key for tracking this message
        """
        ...
    
    async def mark_sent(self, key: str) -> bool:
        """Mark a message as successfully sent.
        
        Args:
            key: The entry key returned by enqueue()
            
        Returns:
            True if marked successfully, False if not found
        """
        ...
    
    async def mark_failed(
        self,
        key: str,
        error: str,
        permanent: bool = False,
    ) -> bool:
        """Mark a message as failed.
        
        Args:
            key: The entry key returned by enqueue()
            error: Error description
            permanent: If True, won't retry this message
            
        Returns:
            True if marked successfully, False if not found
        """
        ...
    
    async def drain(
        self,
        sender: Callable[[str, Dict[str, Any]], Awaitable[bool]],
        limit: Optional[int] = None,
    ) -> tuple[int, int]:
        """Process pending messages.
        
        Called on startup to retry unsent messages. Messages are processed
        oldest-first to maintain order.
        
        Args:
            sender: Async function that attempts delivery. Should return
                    True on success, False to retry later.
            limit: Optional max messages to process
            
        Returns:
            Tuple of (succeeded, failed) counts
        """
        ...
    
    def pending_count(self) -> int:
        """Get count of pending messages awaiting delivery."""
        ...
    
    def size(self) -> int:
        """Get total number of messages in queue."""
        ...
    
    async def purge_old(self, max_age_seconds: int = 86400 * 7) -> int:
        """Remove old sent messages.
        
        Args:
            max_age_seconds: Age threshold for removal
            
        Returns:
            Number of messages purged
        """
        ...


@runtime_checkable
class IdempotencyStoreProtocol(Protocol):
    """Protocol for inbound webhook/trigger delivery deduplication.

    The gateway's inbound HTTP hook surface must not start a second agent run
    for an event a provider re-delivers (webhook providers routinely retry for
    minutes to days). Deduplication is a three-step, restart-stable claim on the
    deterministic idempotency key (``compute_idempotency_key``):

      - ``reserve`` — atomically claim the key. Returns ``False`` when the key
        was already recorded *or* is currently in flight, so both a redelivery
        and a concurrent duplicate are rejected.
      - ``record`` — commit the key after a successful run so future
        redeliveries dedup.
      - ``release`` — drop an in-flight reservation after a failed run so the
        provider's retry can re-run.

    This mirrors :class:`CallbackPayloadStoreProtocol`: the contract lives in
    core so third-party gateways and a future ``redis`` backend interoperate;
    core ships the bounded in-memory default (:class:`InMemoryIdempotencyStore`)
    and the durable, restart-surviving SQLite backend lives in the
    ``praisonai-bot`` runtime (as the ingress journal and outbound queue do).
    """

    def reserve(self, key: str) -> bool:
        """Atomically claim ``key``; ``False`` if seen-or-in-flight."""
        ...

    def record(self, key: str) -> None:
        """Commit ``key`` as processed after a successful run."""
        ...

    def release(self, key: str) -> None:
        """Drop an in-flight reservation so a failed delivery can be retried."""
        ...


class InMemoryIdempotencyStore:
    """Bounded, zero-dependency in-memory :class:`IdempotencyStoreProtocol`.

    The default store for single-replica deployments — identical behaviour to
    the gateway's original per-process ``OrderedDict`` + in-flight ``set``. It
    is *not* durable: after a process restart the store is empty, so a durable
    backend (SQLite/redis) must be injected for the restart/multi-replica case.
    """

    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        ttl_seconds: float = 86_400.0,
    ) -> None:
        self._max_entries = max(1, int(max_entries))
        self._ttl_seconds = float(ttl_seconds)
        # key -> insertion time (seconds); insertion-ordered for FIFO eviction.
        self._seen: "Dict[str, float]" = {}
        self._inflight: Set[str] = set()

    def _purge_expired(self, now: float) -> None:
        if not self._seen:
            return
        expired = [k for k, ts in self._seen.items() if now - ts > self._ttl_seconds]
        for k in expired:
            self._seen.pop(k, None)

    def reserve(self, key: str) -> bool:
        now = time.time()
        self._purge_expired(now)
        if key in self._seen or key in self._inflight:
            return False
        self._inflight.add(key)
        return True

    def record(self, key: str) -> None:
        self._inflight.discard(key)
        self._seen[key] = time.time()
        while len(self._seen) > self._max_entries:
            oldest = next(iter(self._seen))
            self._seen.pop(oldest, None)

    def release(self, key: str) -> None:
        self._inflight.discard(key)


# ---------------------------------------------------------------------------
# Per-route, trust-tiered toolset scoping (Issue #2298)
# ---------------------------------------------------------------------------

# Conservative deny-list applied to ``trust: "untrusted"`` routes.  Inbound
# content from strangers / generic webhooks is the framework's largest
# prompt-injection surface, so dangerous tool *families* are never advertised
# to the model on these routes (shell, file mutation, delegation,
# self-scheduling).  Names are matched case-insensitively against substrings of
# the tool name so deployments do not have to enumerate every concrete tool.
UNTRUSTED_DENY_SUBSTRINGS: List[str] = [
    "shell",
    "exec",
    "command",
    "subprocess",
    "write_file",
    "edit_file",
    "delete_file",
    "rm_file",
    "delegate",
    "handoff",
    "cronjob",
    "schedule",
]

# Trust tiers, ordered from least to most privileged.
TRUST_TIERS: List[str] = ["untrusted", "standard", "trusted"]


@dataclass
class ToolPolicy:
    """Declarative, per-route scope applied to an agent's tool surface.

    Mirrors the scheduler's ``RunPolicy.filter_tools`` contract (wrapper layer)
    but lives in core so :class:`RouteBinding` can *declare* the scope without
    importing any heavy wrapper code.  The wrapper inbound path applies it via a
    small apply/restore helper, exactly as the scheduler already does for
    unattended runs.

    Attributes:
        allow_tools: If set, only tools whose name is in this set are kept;
            everything else is removed.  ``None`` means "allow all except
            ``deny_tools`` / the trust deny-list".
        deny_tools: Exact tool names removed before the run.
        deny_substrings: Case-insensitive substrings; a tool whose name
            contains any of them is removed (used by the ``untrusted`` tier).
    """

    allow_tools: Optional[Set[str]] = None
    deny_tools: Set[str] = field(default_factory=set)
    deny_substrings: List[str] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        """``True`` when the policy would never remove any tool."""
        return (
            self.allow_tools is None
            and not self.deny_tools
            and not self.deny_substrings
        )

    @staticmethod
    def _tool_name(tool: Any) -> str:
        """Best-effort name for a tool (matches Agent's own resolution)."""
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            return name
        dunder = getattr(tool, "__name__", None)
        if isinstance(dunder, str) and dunder:
            return dunder
        if isinstance(tool, dict):
            fn = tool.get("function")
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                return fn["name"]
            top = tool.get("name")
            if isinstance(top, str) and top:
                return top
        return str(tool)

    def is_tool_allowed(self, tool: Any) -> bool:
        """Return ``True`` if ``tool`` may be exposed on this route."""
        name = self._tool_name(tool)
        if name in self.deny_tools:
            return False
        lowered = name.lower()
        for needle in self.deny_substrings:
            if needle and needle.lower() in lowered:
                return False
        if self.allow_tools is not None and name not in self.allow_tools:
            return False
        return True

    def filter_tools(self, tools: Optional[List[Any]]) -> List[Any]:
        """Return a copy of ``tools`` with denied/disallowed tools removed."""
        if not tools:
            return []
        return [tool for tool in tools if self.is_tool_allowed(tool)]


# ---------------------------------------------------------------------------
# Inbound route binding (Issue #2225)
# ---------------------------------------------------------------------------

@dataclass
class RouteBinding:
    """A single declarative inbound-routing rule.

    A binding maps a set of optional inbound conditions to a handling agent.
    Bindings are evaluated most-specific-first so operators get deterministic,
    debuggable routing across a fleet of agents behind one gateway.

    All condition fields are optional; ``None`` means "do not constrain on this
    field". A binding matches a set of :class:`RouteFacts` only when *every*
    non-``None`` condition equals the corresponding fact.

    Attributes:
        agent: The agent id to route to when this binding matches.
        chat_type: Chat type ("dm" | "group" | "channel").
        peer: Sender/user id (most specific).
        role: Role / guild-role membership of the sender.
        channel_id: Specific chat/channel id. Also matches a message whose
            parent channel is this id (a thread/forum-post under it), so a
            channel-level route naturally covers the threads beneath it
            without listing each thread by hand (Issue #4839).
        thread_id: Specific thread / forum-post id (most specific unit — one
            triage-spun support thread can route to a specialist agent,
            Issue #4839).
        guild_id: Server / workspace id. One rule covers every current and
            future channel in the guild, so an operator can multiplex by the
            tenant boundary they actually think in (Issue #4839).
        account: Receiving bot account (for multi-account channels).
        priority: Higher wins; ties are broken by specificity then order.
        trust: Optional trust tier ("untrusted" | "standard" | "trusted").
            ``untrusted`` advertises a conservative, read-only-leaning toolset
            to the model so dangerous tools are never offered on third-party /
            stranger / generic-webhook routes (Issue #2298). ``None`` /
            ``standard`` / ``trusted`` apply no tier deny-list.
        allow_tools: If set, only these tool names are exposed on this route.
        deny_tools: Tool names removed before the run on this route.
        profile: Optional isolated tenant-profile name (Issue #3189). Names a
            per-route isolation scope the wrapper enters for the turn (e.g. its
            own memory namespace / secret scope / home), so one gateway can
            safely multiplex tenants. ``None`` means the route is unscoped; the
            wrapper must fail closed (never fall back to another tenant's
            profile) rather than silently share memory/secrets.
    """

    agent: str
    chat_type: Optional[str] = None
    peer: Optional[str] = None
    role: Optional[str] = None
    channel_id: Optional[str] = None
    account: Optional[str] = None
    priority: int = 0
    trust: Optional[str] = None
    allow_tools: Optional[List[str]] = None
    deny_tools: Optional[List[str]] = None
    profile: Optional[str] = None
    # New optional conditions are appended here (never inserted mid-list) so
    # existing positional constructors — RouteBinding("a", "dm", ..., priority)
    # — keep their meaning and stay backward-compatible (Issue #4839 review).
    thread_id: Optional[str] = None
    guild_id: Optional[str] = None

    # Specificity weights — exact thread beats peer beats role/channel beats
    # guild/account beats chat-type. Higher means more specific, so a single
    # thread rule wins over a whole-guild rule (Issue #4839).
    _SPECIFICITY = {
        "thread_id": 32,
        "peer": 16,
        "role": 8,
        "channel_id": 8,
        "guild_id": 4,
        "account": 4,
        "chat_type": 2,
    }

    def __post_init__(self) -> None:
        """Normalise ``trust``/``profile`` so config typos cannot fail open.

        Whitespace/case variants of a known tier (e.g. ``" Untrusted "``) are
        canonicalised. Any *unknown* non-empty value is treated as the most
        restrictive tier (``untrusted``) rather than as "no policy", so a
        misconfigured route can never accidentally expose the full toolset.
        A blank ``profile`` is coerced to ``None`` (unscoped) for the same
        fail-closed reason.
        """
        # Blank/whitespace-only profile means "unscoped" (None), never an
        # empty-named scope, so a wrapper checking ``if profile is not None``
        # fails closed rather than entering an anonymous namespace.
        if self.profile is not None and not str(self.profile).strip():
            self.profile = None

        if self.trust is None:
            return
        normalized = str(self.trust).strip().lower()
        if not normalized:
            self.trust = None
        elif normalized in TRUST_TIERS:
            self.trust = normalized
        else:
            self.trust = "untrusted"

    @property
    def specificity(self) -> int:
        """Sum of weights for the conditions this binding constrains on."""
        score = 0
        for field_name, weight in self._SPECIFICITY.items():
            if getattr(self, field_name) is not None:
                score += weight
        return score

    def matches(self, facts: "RouteFacts") -> bool:
        """Return True if every constrained condition equals the facts."""
        if self.peer is not None and str(self.peer) != str(facts.peer):
            return False
        if self.channel_id is not None:
            # Parent-chain match (Issue #4839): a channel_id condition matches
            # the channel itself OR a thread/forum-post whose parent is that
            # channel, so channel-level routes cover the threads beneath them
            # without enumerating each thread.
            expected_channel = str(self.channel_id)
            candidates = {str(facts.channel_id)}
            if facts.parent_channel_id is not None:
                candidates.add(str(facts.parent_channel_id))
            if expected_channel not in candidates:
                return False
        if self.thread_id is not None and str(self.thread_id) != str(facts.thread_id):
            return False
        if self.guild_id is not None and str(self.guild_id) != str(facts.guild_id):
            return False
        if self.account is not None and str(self.account) != str(facts.account):
            return False
        if self.chat_type is not None and self.chat_type != facts.chat_type:
            return False
        if self.role is not None:
            expected_role = str(self.role)
            if expected_role not in [str(role) for role in (facts.roles or [])]:
                return False
        return True

    def tool_policy(self) -> Optional["ToolPolicy"]:
        """Build the :class:`ToolPolicy` this binding declares, if any.

        Returns ``None`` when the binding does not constrain the toolset, so
        callers can cheaply skip the apply/restore dance for trusted routes.
        The ``untrusted`` trust tier seeds a conservative substring deny-list;
        explicit ``allow_tools`` / ``deny_tools`` layer on top of it.
        """
        deny_substrings: List[str] = []
        if self.trust == "untrusted":
            deny_substrings = list(UNTRUSTED_DENY_SUBSTRINGS)

        allow = set(self.allow_tools) if self.allow_tools else None
        deny = set(self.deny_tools) if self.deny_tools else set()

        if allow is None and not deny and not deny_substrings:
            return None
        return ToolPolicy(
            allow_tools=allow,
            deny_tools=deny,
            deny_substrings=deny_substrings,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouteBinding":
        """Create a binding from a YAML/dict mapping.

        Accepts ``agent`` (required). Unknown keys are ignored so the shape
        can evolve without breaking older configs.
        """
        return cls(
            agent=data.get("agent", "default"),
            chat_type=data.get("chat_type"),
            peer=_as_opt_str(data.get("peer")),
            role=data.get("role"),
            channel_id=_as_opt_str(data.get("channel_id")),
            account=_as_opt_str(data.get("account")),
            thread_id=_as_opt_str(data.get("thread_id")),
            guild_id=_as_opt_str(data.get("guild_id")),
            priority=int(data.get("priority", 0) or 0),
            trust=_as_opt_str(data.get("trust")),
            allow_tools=_as_opt_str_list(data.get("allow_tools")),
            deny_tools=_as_opt_str_list(data.get("deny_tools")),
            profile=_as_opt_str(data.get("profile")),
        )


@dataclass
class RouteFacts:
    """Inbound facts extracted from a message, used to resolve a binding.

    Attributes:
        chat_type: Normalised chat type ("dm" | "group" | "channel" | "default").
        peer: Sender/user id.
        roles: Roles/guild-role memberships of the sender.
        channel_id: The chat/channel id the message arrived in.
        account: The receiving bot account (multi-account channels).
        thread_id: The thread / forum-post id the message arrived in, when the
            platform threads conversations (Issue #4839).
        guild_id: The server / workspace id the message belongs to (Discord
            guild, Slack workspace), used for whole-server routing (Issue #4839).
        parent_channel_id: The parent channel of a thread/forum-post, so a
            channel-level binding can cover the threads beneath it via
            parent-chain matching (Issue #4839).
    """

    chat_type: str = "default"
    peer: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    channel_id: Optional[str] = None
    account: Optional[str] = None
    thread_id: Optional[str] = None
    guild_id: Optional[str] = None
    parent_channel_id: Optional[str] = None


@dataclass
class RouteMatch:
    """Result of resolving a route.

    Attributes:
        agent: The resolved agent id.
        binding: The binding that matched, or ``None`` when the fallback was used.
        reason: Short human-readable explanation for logging/debugging.
        profile: The isolated tenant-profile named by the matched binding, or
            ``None`` when the route is unscoped / the fallback was used (Issue
            #3189). Surfaced here so the wrapper can enter the profile's memory
            namespace / secret scope for the turn without re-resolving, and so
            an unmatched route fails closed (never inherits another tenant's
            profile).
    """

    agent: str
    binding: Optional[RouteBinding] = None
    reason: str = ""
    profile: Optional[str] = None


def _as_opt_str(value: Any) -> Optional[str]:
    """Coerce a value to a string, preserving ``None``."""
    if value is None:
        return None
    return str(value)


def _as_opt_str_list(value: Any) -> Optional[List[str]]:
    """Coerce a YAML scalar or sequence into ``Optional[List[str]]``.

    Accepts a single string (wrapped into a one-element list) or any iterable
    of values; returns ``None`` for ``None``/empty so an absent key stays
    unconstrained.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return [value] if value else None
    try:
        items = [str(v) for v in value]
    except TypeError:
        return [str(value)]
    return items or None


def resolve_route(
    bindings: List[RouteBinding],
    facts: RouteFacts,
    default_agent: str = "default",
) -> RouteMatch:
    """Resolve the handling agent from priority-ordered bindings.

    Bindings are evaluated most-specific-first: the matching binding with the
    highest ``priority`` wins; ties are broken by specificity (exact thread →
    peer → role/channel → guild/account → chat-type), then by declaration
    order.

    Args:
        bindings: Candidate route bindings (any order).
        facts: Inbound facts extracted from the message.
        default_agent: Agent id to fall back to when nothing matches.

    Returns:
        A :class:`RouteMatch` with the selected agent and matched binding.
    """
    best: Optional[RouteBinding] = None
    best_key: tuple = ()
    for idx, binding in enumerate(bindings):
        if not binding.matches(facts):
            continue
        # Higher priority wins, then higher specificity, then earlier order.
        key = (binding.priority, binding.specificity, -idx)
        if best is None or key > best_key:
            best = binding
            best_key = key

    if best is not None:
        return RouteMatch(
            agent=best.agent,
            binding=best,
            reason=(
                f"matched binding (priority={best.priority}, "
                f"specificity={best.specificity})"
            ),
            profile=best.profile,
        )

    return RouteMatch(
        agent=default_agent,
        binding=None,
        reason="no binding matched; using default",
    )


# ---------------------------------------------------------------------------
# Auth Mode protocols and helpers (bind-aware authentication posture)
# ---------------------------------------------------------------------------

AuthMode = Literal["local", "token", "password", "trusted-proxy"]
"""Authentication mode for gateway/UI components.

- "local": Permissive mode for loopback interfaces (127.0.0.1, localhost, ::1)
- "token": Token-based authentication required (default for external interfaces)  
- "password": Username/password authentication
- "trusted-proxy": Authentication handled by upstream proxy
"""


def is_loopback(host: str) -> bool:
    """Check if a host is a loopback interface.
    
    Args:
        host: Host/IP address to check
        
    Returns:
        True if the host is a loopback address
        
    Examples:
        >>> is_loopback("127.0.0.1")
        True
        >>> is_loopback("localhost") 
        True
        >>> is_loopback("::1")
        True
        >>> is_loopback("0.0.0.0")
        False
        >>> is_loopback("192.168.1.1")
        False
    """
    import ipaddress
    
    # Handle localhost specially
    if host in ("localhost", "0:0:0:0:0:0:0:1"):
        return True
    
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback
    except ValueError:
        # Not a valid IP address (e.g., domain name)
        return False


def resolve_auth_mode(bind_host: str, configured: Optional[AuthMode] = None) -> AuthMode:
    """Resolve authentication mode based on bind host and explicit configuration.
    
    Args:
        bind_host: Host/IP that the service is bound to
        configured: Explicitly configured auth mode (takes precedence)
        
    Returns:
        The resolved authentication mode
        
    Examples:
        >>> resolve_auth_mode("127.0.0.1")
        'local'
        >>> resolve_auth_mode("0.0.0.0")  
        'token'
        >>> resolve_auth_mode("127.0.0.1", "token")
        'token'
    """
    if configured is not None:
        return configured
    
    return "local" if is_loopback(bind_host) else "token"


# ---------------------------------------------------------------------------
# Weak / placeholder secret guard (Issue #3259)
# ---------------------------------------------------------------------------

KNOWN_WEAK_SECRETS: frozenset = frozenset({
    "change-me", "changeme", "change-me-now", "changemenow",
    "your-token-here", "your_token_here", "your-secret-here",
    "secret", "password", "passwd", "test", "token", "admin",
    "default", "example", "placeholder", "none", "null", "todo",
    # Copy-paste footgun: the literal fix-hint command pasted verbatim.
    "$(openssl rand -hex 16)", "$(openssl rand -hex 32)",
})
"""Well-known placeholder/weak shared secrets that must never protect a gateway.

A gateway bound to an external interface and "protected" by one of these
publicly-known values is effectively unauthenticated. See Issue #3259.
"""


class WeakGatewaySecretError(Exception):
    """Raised when a gateway secret matches a known-weak/placeholder value."""

    def __init__(self, field: str = "gateway.auth_token"):
        self.field = field
        super().__init__(
            f"Refusing to start: {field} is a known-weak/placeholder value.\n"
            f"A publicly-known secret provides no real authentication.\n"
            f"Fix:  praisonai onboard         (30 seconds, 3 prompts)\n"
            f"Or:   export GATEWAY_AUTH_TOKEN=\"$(openssl rand -hex 16)\"  "
            f"(run in a shell so the command is expanded, not pasted literally)"
        )


def is_weak_secret(value: Optional[str]) -> bool:
    """Return True if ``value`` is empty or a known-weak/placeholder secret.

    Comparison is whitespace-stripped and case-insensitive.

    Examples:
        >>> is_weak_secret("change-me")
        True
        >>> is_weak_secret("$(openssl rand -hex 16)")
        True
        >>> is_weak_secret("strong-non-placeholder-token")
        False
    """
    if not value:
        return True
    return str(value).strip().lower() in KNOWN_WEAK_SECRETS


def assert_gateway_secret_strong(value: Optional[str], *, field: str = "gateway.auth_token") -> None:
    """Fail closed if ``value`` is a known-weak/placeholder gateway secret.

    Args:
        value: The resolved secret to validate.
        field: Name of the credential (used in the error message).

    Raises:
        WeakGatewaySecretError: If ``value`` matches a known-weak value.
    """
    if is_weak_secret(value):
        raise WeakGatewaySecretError(field=field)


# ---------------------------------------------------------------------------
# Per-platform identity canonicalization (Issue #3886)
#
# The gateway keys a user's session/memory/pairing/allowlist on the raw
# platform address it receives on the wire. On some platforms one human is
# addressed by *two interchangeable forms* — most notably WhatsApp, which now
# surfaces both a privacy LID (``<lid>@lid``) and a phone JID
# (``<phone>@s.whatsapp.net``) for the same person. Propagating the raw address
# straight through splits one user into two principals: divergent session /
# memory, a broken DM allowlist match, and spurious re-pairing.
#
# This is the dependency-free *contract* for reconciling alternate address
# forms to one stable canonical id, consulted as the first step of identity
# resolution. The concrete, platform-specific implementation (which needs the
# bridge's own LID<->phone mapping — platform I/O) lives in the adapter, not in
# core; core owns only the protocol so any adapter with multiple address forms
# can plug in uniformly.
# ---------------------------------------------------------------------------

@runtime_checkable
class IdentityCanonicalizerProtocol(Protocol):
    """Reconcile a raw platform address to one stable canonical id.

    Consulted as the *first* step of identity resolution (before the session /
    memory / pairing / allowlist keys are derived) so that alternate address
    forms of the same person — e.g. WhatsApp's ``<lid>@lid`` vs
    ``<phone>@s.whatsapp.net`` — resolve to a single principal.

    Implementations MUST be deterministic and safe: return ``raw_user_id``
    unchanged whenever no reconciliation is known, so an adapter that cannot
    map a given address never corrupts identity (fail-open to today's
    behaviour). With no canonicalizer registered, resolution is unchanged.
    """

    def canonicalize(self, platform: str, raw_user_id: str) -> str:
        """Return the stable canonical id for a raw platform address.

        Args:
            platform: The platform name (e.g. ``"whatsapp"``).
            raw_user_id: The raw address as delivered on the wire.

        Returns:
            The reconciled canonical id, or ``raw_user_id`` unchanged when no
            reconciliation is known.
        """
        ...


# ---------------------------------------------------------------------------
# Auth, Pairing, and Session Binding Protocols (Issue #1588 Gap 3)
# ---------------------------------------------------------------------------

@runtime_checkable
class AuthProtocol(Protocol):
    """Protocol for authentication implementations.
    
    Enables structural typing for different authentication strategies
    (token-based, local loopback, trusted proxy, etc.).
    """
    
    def check(self, request: Any) -> Dict[str, Any]:
        """Check authentication for a request.
        
        Args:
            request: The request object to authenticate
            
        Returns:
            Authentication decision with metadata:
            - success: bool - whether authentication succeeded
            - user_id: Optional[str] - authenticated user ID
            - role: Optional[str] - user role/permissions
            - metadata: Dict[str, Any] - additional auth context
        """
        ...


@runtime_checkable  
class PairingProtocol(Protocol):
    """Protocol for channel pairing implementations.
    
    Manages the authorization of external channels (Telegram, Slack, UI)
    to communicate with the gateway through signed codes.
    """
    
    def generate_code(
        self, 
        channel_type: str = "unknown", 
        channel_id: Optional[str] = None
    ) -> str:
        """Generate a new pairing code for a channel.
        
        Args:
            channel_type: Type of channel (e.g., "telegram", "slack", "ui")
            channel_id: Optional channel identifier
            
        Returns:
            The generated pairing code
        """
        ...
    
    def approve(
        self, 
        channel_type: str,
        code: str,
        user_id: str = "",
        user_name: str = ""
    ) -> bool:
        """Approve a pairing code, authorizing the channel.
        
        Args:
            channel_type: Type of channel
            code: The pairing code to approve
            user_id: User identifier (optional, defaults to empty string)
            user_name: Human-readable username (optional, defaults to empty string)
            
        Returns:
            True if approval successful, False if code invalid/expired
        """
        ...
    
    def is_paired(self, channel_id: str, channel_type: str) -> bool:
        """Check if a channel is authorized.
        
        Args:
            channel_id: Channel identifier
            channel_type: Type of channel
            
        Returns:
            True if channel is paired/authorized
        """
        ...
    
    def list_paired(self) -> List["PairedChannel"]:
        """List all authorized channels.
        
        Returns:
            List of paired channel information
        """
        ...
    
    def revoke(self, channel_id: str, channel_type: str) -> bool:
        """Revoke authorization for a channel.
        
        Args:
            channel_id: Channel identifier
            channel_type: Type of channel
            
        Returns:
            True if revocation successful, False if not found
        """
        ...
    
    def list_pending(self, channel_type: Optional[str] = None) -> List[Dict[str, any]]:
        """List pending pairing requests.
        
        Args:
            channel_type: Optional filter by channel type
            
        Returns:
            List of pending requests with channel, code, user info, and age
        """
        ...


@runtime_checkable
class SessionBindingProtocol(Protocol):
    """Protocol for session binding implementations.
    
    Manages the association between sessions and authenticated principals
    (users, agents, etc.) for state tracking and authorization.
    """
    
    def bind(self, session_id: str, principal: Dict[str, Any]) -> None:
        """Bind a session to an authenticated principal.
        
        Args:
            session_id: Unique session identifier
            principal: Principal information (user_id, roles, metadata, etc.)
        """
        ...
    
    def lookup(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Look up the principal bound to a session.
        
        Args:
            session_id: Session identifier to look up
            
        Returns:
            Principal information if found, None otherwise
        """
        ...


# Home Channel and Delivery Routing Protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class HomeChannelRegistryProtocol(Protocol):
    """Protocol for managing default delivery targets per platform.
    
    Home channels provide a per-platform default delivery target that can be
    set once from inside a chat and persisted, so scheduled jobs can deliver
    results without requiring explicit channel IDs.
    """
    
    def set_home(
        self, 
        platform: str, 
        chat_id: str, 
        thread_id: Optional[str] = None
    ) -> None:
        """Set the home channel for a platform.
        
        Args:
            platform: Platform name (e.g., "telegram", "slack", "discord")
            chat_id: Platform-specific chat/channel ID
            thread_id: Optional thread ID for threaded platforms
        """
        ...
    
    def get_home(self, platform: str) -> Optional[tuple[str, Optional[str]]]:
        """Get the home channel for a platform.
        
        Args:
            platform: Platform name to look up
            
        Returns:
            Tuple of (chat_id, thread_id) if set, None otherwise
        """
        ...
    
    def platforms_with_home(self) -> List[str]:
        """List all platforms that have a home channel configured.
        
        Returns:
            List of platform names with home channels
        """
        ...


@dataclass(frozen=True)
class DeliveryValidation:
    """Result of a creation-time delivery-target pre-flight (Issue #3800).

    A scheduled job or agent-initiated proactive message carries a
    ``DeliveryTarget`` whose reachability is otherwise only discovered when the
    job *fires* — potentially hours later, where an unroutable target is
    silently dropped or dead-target self-healed. This closed shape lets a
    resolver answer "will this route?" the moment the send is created, so the
    creator gets an immediate, actionable error instead of a late invisible
    drop.

    Attributes:
        ok: Whether the target resolves to a reachable channel/route.
        reason: On failure, a human-readable explanation of why it is
            unroutable (empty when ``ok``).
        hint: On failure, an actionable next step (e.g. the configured
            channels, or a command to list them); empty when ``ok``.
        preview: A dry-run preview of the destination (e.g.
            ``"telegram:@alice (session main)"``) suitable for surfacing to the
            creator before commit.
    """

    ok: bool
    reason: str = ""
    hint: str = ""
    preview: str = ""


class ScheduleTargetError(ValueError):
    """Raised when a scheduled/agent-initiated send has an unroutable target.

    Carries the structured :class:`DeliveryValidation` reason/hint so the
    scheduler/CLI can fail fast at *creation* time with an actionable message
    (``channel 'telegramm' is not configured. Configured: telegram, slack.``)
    rather than accepting a target that is only discovered dead at fire time.
    """

    def __init__(self, reason: str, hint: str = ""):
        self.reason = reason
        self.hint = hint
        message = f"{reason} {hint}".strip() if hint else reason
        super().__init__(message)


@runtime_checkable
class DeliveryResolverProtocol(Protocol):
    """Protocol for resolving delivery routing tokens.
    
    Resolves tokens like "origin", "telegram", "all" to concrete delivery
    targets at fire time, enabling ergonomic routing without hard-coded IDs.
    """
    
    def resolve(
        self, 
        token: str, 
        *, 
        origin: Optional["DeliveryTarget"] = None
    ) -> List["DeliveryTarget"]:
        """Resolve a routing token to concrete delivery targets.
        
        Token formats:
        - "origin": Reply to the chat where the job was created (requires origin)
        - "<platform>": That platform's home channel
        - "<platform>:<chat_id>[:<thread_id>]": Explicit target
        - "all": Fan-out to every connected platform with a home channel
        
        Args:
            token: Routing token to resolve
            origin: Original delivery target (for "origin" token)
            
        Returns:
            List of concrete delivery targets
        """
        ...


@runtime_checkable
class DeliveryPreflightProtocol(Protocol):
    """Optional creation-time pre-flight extension for delivery resolvers.

    Kept separate from :class:`DeliveryResolverProtocol` so the base contract
    stays ``resolve()``-only: an existing resolver that implements just
    ``resolve`` still satisfies ``DeliveryResolverProtocol`` under
    ``isinstance``/``runtime_checkable``. A resolver that can additionally
    pre-flight or preview a target against its live registry advertises that by
    also satisfying this protocol; callers duck-type on it and fall back to a
    structural, registry-free check (:meth:`DeliveryTarget.preview`) otherwise.
    """

    def validate_target(
        self, target: "DeliveryTarget"
    ) -> "DeliveryValidation":
        """Pre-flight ``target`` against the live channel/route registry.

        Called at *creation* time (when a scheduled/agent-initiated send is
        registered) so an unroutable target is rejected or warned on with an
        actionable message, instead of being silently dropped when the job
        fires.

        Returns:
            A :class:`DeliveryValidation` (``ok`` / ``reason`` / ``hint`` /
            ``preview``).
        """
        ...

    def preview_target(
        self, target: "DeliveryTarget"
    ) -> str:
        """Return a dry-run preview of where ``target`` will deliver.

        A short, display-only string (e.g. ``"telegram:@alice (session
        main)"``) so the creator sees the destination before commit.
        """
        ...


# ---------------------------------------------------------------------------
# Agent-facing outbound messaging (Issue #2183)
# ---------------------------------------------------------------------------

@dataclass
class DeliveryResult:
    """Outcome of an agent-initiated proactive send.

    Attributes:
        ok: Whether the send was accepted for delivery.
        target: The resolved target the message was routed to.
        summary: Human-readable summary suitable for returning to the model.
        detail: Optional extra information (error text, message id, etc.).
    """

    ok: bool
    target: str = ""
    summary: str = ""
    detail: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "ok": self.ok,
            "target": self.target,
            "summary": self.summary,
            "detail": self.detail,
        }


@dataclass
class TargetInfo:
    """A reachable delivery target the agent can address.

    Attributes:
        target: The token to pass to ``send`` (e.g. "origin", "slack:#ops").
        platform: Platform name (e.g. "telegram", "slack").
        kind: Target kind ("origin", "home", or "alias").
        label: Friendly label for display to the model/user.
    """

    target: str
    platform: str = ""
    kind: str = "alias"
    label: str = ""

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "target": self.target,
            "platform": self.platform,
            "kind": self.kind,
            "label": self.label,
        }


ReactionStatus = Literal["ok", "unsupported", "failed", "no_route"]
"""Closed set of outcomes for a :meth:`OutboundMessengerProtocol.react` call.

* ``ok`` — the reaction was added/removed.
* ``unsupported`` — the channel has no ``reactions`` capability.
* ``failed`` — the transport rejected the reaction (e.g. no such message).
* ``no_route`` — the target could not be resolved to a reachable channel.
"""


@dataclass
class ReactionResult:
    """Outcome of an agent-initiated message reaction (Issue #3917).

    Every call resolves to exactly one :data:`ReactionStatus`, so the agent
    always gets a typed answer rather than a hard error — in particular a
    channel that cannot react returns ``unsupported`` rather than raising.

    Attributes:
        status: The outcome (``ok`` / ``unsupported`` / ``failed`` /
            ``no_route``).
        target: The resolved target the reaction was routed to.
        detail: Optional model-readable explanation.
    """

    status: ReactionStatus
    target: str = ""
    detail: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary for the tool return value."""
        data: Dict[str, Any] = {"status": self.status}
        if self.target:
            data["target"] = self.target
        if self.detail:
            data["detail"] = self.detail
        return data


ThreadStatus = Literal["ok", "unsupported", "failed", "no_route"]
"""Closed set of outcomes for a :meth:`OutboundMessengerProtocol.create_thread`.

* ``ok`` — a new thread/topic was opened; ``thread_id`` carries its id.
* ``unsupported`` — the channel has no ``supports_threads`` capability.
* ``failed`` — the transport rejected the attempt (e.g. topics mode off, or
  the bot lacks permission to manage threads).
* ``no_route`` — the target could not be resolved to a reachable channel.
"""


@dataclass
class ThreadResult:
    """Outcome of an agent/gateway-initiated thread creation (Issue #3987).

    Every call resolves to exactly one :data:`ThreadStatus`, so the caller
    always gets a typed answer rather than a hard error — in particular a
    channel that cannot thread returns ``unsupported`` rather than raising, and
    the caller falls back to the parent channel. This mirrors the
    :class:`ReactionResult` contract.

    Attributes:
        status: The outcome (``ok`` / ``unsupported`` / ``failed`` /
            ``no_route``).
        target: The resolved parent target the thread was opened under.
        thread_id: The new thread/topic id, populated only when
            ``status == "ok"``. Callers compose ``"<target>:<thread_id>"`` to
            route subsequent sends into it.
        detail: Optional model-readable explanation.
    """

    status: ThreadStatus
    target: str = ""
    thread_id: str = ""
    detail: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Whether a thread was opened (``status == "ok"``)."""
        return self.status == "ok"

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary for the tool return value."""
        data: Dict[str, Any] = {"status": self.status}
        if self.target:
            data["target"] = self.target
        if self.thread_id:
            data["thread_id"] = self.thread_id
        if self.detail:
            data["detail"] = self.detail
        return data


@runtime_checkable
class OutboundMessengerProtocol(Protocol):
    """Protocol for agent-facing proactive message delivery.

    A concrete implementation is provided by the running gateway/bot (in the
    praisonai wrapper) and registered into the per-turn context so the
    built-in ``send_message`` tool can resolve it. It bridges to the existing
    delivery stack (DeliveryRouter, HomeChannelRegistry, outbox, mirroring).

    Example usage (implementation in praisonai_bot.gateway)::

        messenger = BotOutboundMessenger(bot, resolver, router)
        token = register_outbound_messenger(messenger)
        try:
            ...  # agent runs; send_message tool resolves the messenger
        finally:
            clear_outbound_messenger(token)
    """

    async def send(
        self,
        target: str,
        text: str,
        *,
        media: Optional[List[str]] = None,
    ) -> "DeliveryResult":
        """Deliver a message to a symbolic target.

        Args:
            target: Symbolic target token ("origin", "<platform>",
                "<platform>:<chat_id>[:<thread_id>]", or a friendly alias).
            text: The message text to send.
            media: Optional list of local file paths to attach.

        Returns:
            A :class:`DeliveryResult` describing the outcome.
        """
        ...

    def list_targets(self) -> List["TargetInfo"]:
        """List the targets currently reachable from this runtime."""
        ...

    async def react(
        self,
        target: str,
        emoji: str,
        *,
        message_id: str = "",
        remove: bool = False,
    ) -> "ReactionResult":
        """Add (or remove) a reaction on a message (Issue #3917).

        A lightweight acknowledgement path for busy group channels: rather than
        posting a whole reply, an agent can react with a single emoji. Gated on
        the channel's ``PlatformCapabilities.reactions`` — a channel that cannot
        react returns a typed ``unsupported`` outcome instead of raising, so the
        model never has to guess.

        Args:
            target: Symbolic target token ("origin", "<platform>",
                "<platform>:<chat_id>[:<thread_id>]", or a friendly alias).
            emoji: The reaction emoji to add/remove.
            message_id: The message to react to. When empty and ``target`` is
                ``"origin"``, the message currently being handled is used.
            remove: When True, remove the reaction instead of adding it.

        Returns:
            A :class:`ReactionResult` describing the outcome.
        """
        ...

    async def create_thread(
        self,
        target: str,
        name: str,
    ) -> "ThreadResult":
        """Open a new thread/topic under ``target`` (Issue #3987).

        For multi-agent handoffs, subtasks, and parallel workflow branches, this
        lets the gateway scope a subtask into its own platform-native thread
        (Telegram forum topic, Discord thread, Slack thread anchor) instead of
        flooding the shared channel inline. Gated on the channel's
        ``PlatformCapabilities.supports_threads`` — a channel that cannot thread
        returns a typed ``unsupported`` outcome instead of raising, so the
        caller falls back to the parent channel::

            res = await messenger.create_thread("slack:C123", name="research")
            target = f"slack:C123:{res.thread_id}" if res.ok else "slack:C123"
            await messenger.send(target, subtask_output)

        Args:
            target: Symbolic target token ("origin", "<platform>", or
                "<platform>:<chat_id>", or a friendly alias).
            name: Human-friendly thread/topic title.

        Returns:
            A :class:`ThreadResult` carrying the new thread id on success, or a
            typed ``unsupported`` / ``failed`` / ``no_route`` outcome. Never
            raises.
        """
        ...


# ---------------------------------------------------------------------------
# Agent-callable cross-conversation request/reply (Issue #3689)
#
# ``send_message`` is fire-and-deliver: it returns a delivery receipt, not the
# target's answer. This adds the missing *ask another conversation and await
# the reply* capability — an agent can route a question to a symbolic target
# and get the next correlated inbound reply back into its own turn, bounded by
# a timeout. It reuses ``send_message``'s target resolution and the outbound
# send-policy guard; the only new surface is a one-shot reply correlation.
#
# Core owns only the *shape*: the typed outcome (:class:`ConversationReply`),
# the protocol seam (:class:`ConversationRequestProtocol`), the context-var
# registration slot (in ``session.context``), and the built-in
# ``ask_conversation`` tool. The correlation-aware reply source is bound by the
# running gateway/bot exactly as ``register_outbound_messenger`` binds the
# outbound side — no heavy import lives in core. Every path ends in a recorded
# outcome (reply | timeout | undelivered | no_route) — never a silent hang.
# ---------------------------------------------------------------------------

ConversationReplyStatus = Literal["reply", "timeout", "undelivered", "no_route"]
"""Closed set of outcomes for an :func:`ask_conversation` request.

* ``reply`` — the target replied within the timeout; ``text`` carries it.
* ``timeout`` — the prompt was delivered but no reply arrived in time.
* ``undelivered`` — the prompt could not be delivered to the target.
* ``no_route`` — the target could not be resolved to a reachable channel.
"""


@dataclass
class ConversationReply:
    """Outcome of an agent-initiated cross-conversation request (Issue #3689).

    Every request resolves to exactly one of the :data:`ConversationReplyStatus`
    outcomes, so the agent always gets a typed answer back into its turn rather
    than a silent hang.

    Attributes:
        status: The outcome (``reply`` / ``timeout`` / ``undelivered`` /
            ``no_route``).
        target: The resolved target the prompt was routed to.
        text: The reply text, populated only when ``status == "reply"``.
        detail: Optional extra information (error text, message id, etc.).
    """

    status: ConversationReplyStatus
    target: str = ""
    text: str = ""
    detail: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary for the tool return value."""
        data: Dict[str, Any] = {"status": self.status}
        if self.target:
            data["from"] = self.target
        if self.status == "reply":
            data["text"] = self.text
        if self.detail:
            data["detail"] = self.detail
        return data


@runtime_checkable
class ConversationRequestProtocol(Protocol):
    """Protocol for agent-facing cross-conversation request/reply.

    A concrete implementation is provided by the running gateway/bot (in the
    praisonai wrapper) and registered into the per-turn context so the built-in
    ``ask_conversation`` tool can resolve it. It sends the prompt via the same
    delivery stack ``send_message`` uses, then correlates the *next inbound
    reply* from that target (via the existing ``correlation_id``) with a bounded
    timeout, returning a typed :class:`ConversationReply`.

    Example usage (implementation in praisonai_bot.gateway)::

        requester = BotConversationRequester(router, origin=origin)
        token = register_conversation_requester(requester)
        try:
            ...  # agent runs; ask_conversation tool resolves the requester
        finally:
            clear_conversation_requester(token)
    """

    async def ask(
        self,
        target: str,
        text: str,
        *,
        timeout_s: float = 120.0,
    ) -> "ConversationReply":
        """Send ``text`` to ``target`` and await the next correlated reply.

        Args:
            target: Symbolic target token ("origin", "<platform>",
                "<platform>:<chat_id>[:<thread_id>]", or a friendly alias).
            text: The prompt to send.
            timeout_s: Maximum seconds to wait for a reply before returning a
                ``timeout`` outcome.

        Returns:
            A :class:`ConversationReply` describing the outcome.
        """
        ...


# ---------------------------------------------------------------------------
# Agent-callable live status/health (Issue #3688)
#
# The gateway already computes rich live state (per-turn run status, active
# sessions, delivery/DLQ backlog, degraded owners) but only humans/CLI/HTTP can
# read it. This read-only protocol lets the running gateway bind a live source
# into the per-turn context so the built-in ``gateway_status`` tool can report
# it — mirroring how ``OutboundMessengerProtocol`` backs ``send_message``. Core
# ships only the protocol + snapshot shape; the concrete binding (reading
# ``health()`` / ``metrics_snapshot()`` / the session registry) lives in the
# praisonai-bot wrapper. It is strictly read-only, redaction-aware and
# visibility-scoped (no secrets, no cross-tenant leakage).
# ---------------------------------------------------------------------------

@dataclass
class GatewayStatus:
    """Read-only snapshot of the gateway's live self-state (Issue #3688).

    A neutral, serializable shape the agent can reason about and report. All
    fields default to empty so a partial/minimal binding is valid and the tool
    never dead-ends. The concrete binding populates only the visibility-scoped
    facts it can safely expose.

    Attributes:
        run: Current turn/run status (e.g. "idle", "busy", "queued").
        queued: Number of turns queued behind the current one.
        active_sessions: Count of active sessions (visibility-scoped).
        sessions_by_channel: Active-session counts keyed by channel/platform.
        delivery: Delivery-health facts (e.g. outbox_depth, dlq, dead_targets).
        degraded: Degraded owners as ``{"owner": ..., "reason": ...}`` entries
            (channels/capabilities/routes flagged configured-unavailable).
        detail: Optional free-form extra context for the model.
    """

    run: str = "idle"
    queued: int = 0
    active_sessions: int = 0
    sessions_by_channel: Dict[str, int] = field(default_factory=dict)
    delivery: Dict[str, Any] = field(default_factory=dict)
    degraded: List[Dict[str, Any]] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "run": self.run,
            "queued": self.queued,
            "active_sessions": self.active_sessions,
            "sessions_by_channel": dict(self.sessions_by_channel),
            "delivery": dict(self.delivery),
            "degraded": list(self.degraded),
            "detail": self.detail,
        }


@runtime_checkable
class GatewayStatusProtocol(Protocol):
    """Protocol for agent-facing, read-only live status/health reporting.

    A concrete implementation is provided by the running gateway/bot (in the
    praisonai wrapper) and registered into the per-turn context so the built-in
    ``gateway_status`` tool can resolve it. It reads the same live objects the
    HTTP endpoints already serve (``health()`` / ``metrics_snapshot()`` / the
    session registry) and returns a redaction-aware, visibility-scoped
    :class:`GatewayStatus`.

    Example usage (implementation in praisonai_bot.gateway)::

        status = BotGatewayStatus(gateway)
        token = register_gateway_status(status)
        try:
            ...  # agent runs; gateway_status tool resolves the source
        finally:
            clear_gateway_status(token)
    """

    def snapshot(self) -> "GatewayStatus":
        """Return a read-only snapshot of the gateway's live self-state."""
        ...


# ---------------------------------------------------------------------------
# Outbound send-policy guard (Issue #2226)
#
# ``send_message`` lets the model choose where to deliver. Because the target
# is model-controlled, poisoned inbound content (prompt injection) can steer an
# agent into delivering to a channel the operator never intended. The router
# only fails on *unresolvable* targets — a reachability check, not an
# authorisation one. This policy seam sits in core, *before* dispatch, so every
# messenger implementation is constrained, not just one adapter. Absent a
# policy, today's behaviour is preserved (allow-all).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SendDecision:
    """Closed decision shape for an outbound send-policy evaluation.

    Attributes:
        allow: Whether the send to the requested target is permitted.
        reason: Optional model-readable explanation (used in the
            :class:`DeliveryResult` detail when denied).
    """

    allow: bool
    reason: str = ""


@runtime_checkable
class SendPolicyProtocol(Protocol):
    """Protocol for authorising agent-initiated proactive sends.

    Implementations decide whether an agent may deliver to a model-chosen
    ``target``. The hook is evaluated inside the ``send_message`` path before
    the messenger dispatches, so a denied send returns a clean, model-readable
    :class:`DeliveryResult` (``ok=False``) rather than delivering.

    A concrete, config-driven implementation (:class:`SendPolicy`) is provided
    for the common allow/deny case; richer back-ends may live in plugins.
    """

    def evaluate(
        self,
        target: str,
        *,
        agent_id: str = "",
        session_id: str = "",
        origin: Optional[str] = None,
    ) -> SendDecision:
        """Return a :class:`SendDecision` for the requested ``target``."""
        ...


class SendPolicy:
    """A lightweight allow/deny send-policy with an optional default-deny posture.

    This is the config-driven default referenced by ``send_policy`` blocks in
    ``gateway.yaml`` and the ``Bot(..., send_policy=...)`` Python surface. It is
    intentionally minimal (no heavy dependencies) and lives in core so the
    built-in ``send_message`` path is always interceptable.

    Matching is exact against the symbolic target token (e.g. ``"origin"``,
    ``"slack:#ops"``, or a friendly alias). With ``default="deny"`` only listed
    targets are permitted; with ``default="allow"`` all targets are permitted
    except those in ``deny``.

    Example::

        # default-deny: only the conversation origin and an ops alias allowed
        SendPolicy(default="deny", allow=["origin", "ops-alerts"])
        # default-allow: everything permitted except an exec channel
        SendPolicy(default="allow", deny=["slack:#exec"])
    """

    def __init__(
        self,
        default: str = "allow",
        allow: Optional[List[str]] = None,
        deny: Optional[List[str]] = None,
    ):
        default = (default or "allow").lower()
        if default not in ("allow", "deny"):
            raise ValueError(
                f"send_policy default must be 'allow' or 'deny', got {default!r}"
            )
        self.default = default
        self.allow = list(allow or [])
        self.deny = list(deny or [])

    def evaluate(
        self,
        target: str,
        *,
        agent_id: str = "",
        session_id: str = "",
        origin: Optional[str] = None,
    ) -> SendDecision:
        if target in self.deny:
            return SendDecision(
                allow=False,
                reason=f"target '{target}' is denied by send_policy",
            )
        if self.default == "deny":
            if target in self.allow:
                return SendDecision(allow=True)
            return SendDecision(
                allow=False,
                reason=f"target '{target}' is not permitted by send_policy",
            )
        return SendDecision(allow=True)


# ---------------------------------------------------------------------------
# Gateway idle-dormancy / scale-to-zero (Issue #2332)
# ---------------------------------------------------------------------------


@dataclass
class IdleDecision:
    """Result of an idle/quiesce evaluation.

    Attributes:
        idle: Whether the gateway is currently quiescent.
        reason: Optional human-readable explanation (logged on quiesce).
    """

    idle: bool
    reason: str = ""


@runtime_checkable
class GatewayIdlePolicyProtocol(Protocol):
    """Protocol for gateway-process idle/scale-to-zero decisions.

    Pure, import-free decision contract consumed by the wrapper's
    ``BotOS`` run-loop. The wrapper supplies live facts (running turns,
    last inbound timestamp, background-work flag) and the policy decides
    whether the whole gateway may safely stand down. Concrete drivers
    (suspend the compute host, stand transports down, register a wake
    URL) live in the wrapper; this contract keeps the *decision* testable
    in isolation without a live gateway.

    A config-driven default (:class:`ScaleToZeroPolicy`) is provided for
    the common "idle for N minutes with nothing in flight" case.
    """

    def should_arm(
        self,
        *,
        transports_quiescable: bool,
        wake_registered: bool,
    ) -> bool:
        """Return whether dormancy may be armed at all.

        Implementations gate on whether transports can be cleanly stood
        down and a wake path exists, so a gateway never quiesces into a
        state it cannot resume from.
        """
        ...

    def is_idle(
        self,
        *,
        running_turns: int,
        last_inbound_ts: float,
        has_background_work: bool,
        now: float,
    ) -> IdleDecision:
        """Return an :class:`IdleDecision` for the supplied facts."""
        ...


class ScaleToZeroPolicy:
    """Config-driven idle policy for safe scale-to-zero.

    The default referenced by ``scale_to_zero:`` blocks in ``gateway.yaml``
    and the ``BotOS(..., idle_policy=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in
    core and is provable in isolation; the wrapper owns the side effects
    (suspend host, stand transports down, wake endpoint).

    The gateway is considered idle only when *all* guards pass:

    * no in-flight agent turn (``running_turns == 0``),
    * no live background work (scheduled jobs, delegated subagents,
      durable outbox drains — ``has_background_work`` is ``False``),
    * no inbound message for at least ``idle_timeout_minutes``.

    Example::

        ScaleToZeroPolicy(idle_timeout_minutes=5,
                          wake_url="https://my-bot.fly.dev/_wake")
    """

    def __init__(
        self,
        idle_timeout_minutes: float = 5.0,
        wake_url: Optional[str] = None,
        enabled: bool = True,
    ):
        if idle_timeout_minutes <= 0:
            raise ValueError(
                f"idle_timeout_minutes must be > 0, got {idle_timeout_minutes!r}"
            )
        self.idle_timeout_minutes = float(idle_timeout_minutes)
        self.wake_url = wake_url
        self.enabled = bool(enabled)

    @property
    def idle_timeout_seconds(self) -> float:
        return self.idle_timeout_minutes * 60.0

    def should_arm(
        self,
        *,
        transports_quiescable: bool,
        wake_registered: bool,
    ) -> bool:
        if not self.enabled:
            return False
        # Never arm into a state we cannot resume from.
        return bool(transports_quiescable and wake_registered)

    def is_idle(
        self,
        *,
        running_turns: int,
        last_inbound_ts: float,
        has_background_work: bool,
        now: float,
    ) -> IdleDecision:
        if not self.enabled:
            return IdleDecision(idle=False, reason="scale_to_zero disabled")
        if running_turns > 0:
            return IdleDecision(
                idle=False,
                reason=f"{running_turns} agent turn(s) in flight",
            )
        if has_background_work:
            return IdleDecision(
                idle=False,
                reason="background work in progress",
            )
        elapsed = now - last_inbound_ts
        if elapsed < self.idle_timeout_seconds:
            remaining = self.idle_timeout_seconds - elapsed
            return IdleDecision(
                idle=False,
                reason=f"last inbound {elapsed:.0f}s ago; {remaining:.0f}s to idle",
            )
        return IdleDecision(
            idle=True,
            reason=f"idle for {elapsed:.0f}s with nothing in flight",
        )


# Backward-compatible alias. The canonical name follows the repo's
# ``*Protocol`` suffix convention (e.g. ``SendPolicyProtocol``); the old
# name is retained so existing imports keep working.
GatewayIdlePolicy = GatewayIdlePolicyProtocol


# ---------------------------------------------------------------------------
# Gateway freeze-thaw (involuntary host-suspend gap) recovery (Issue #4767)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThawDecision:
    """Result of a freeze-thaw (host-suspend gap) evaluation.

    Attributes:
        suspended: Whether an involuntary host-suspend gap was detected
            since the previous observation.
        gap_seconds: Estimated duration the host was frozen (0.0 when not
            suspended).
        restart_transports: Whether the wrapper should re-probe / restart
            outbound channel sockets (idle-gated) because they may be
            silently half-dead after the freeze.
        reconcile_schedule: Whether the wrapper should reconcile the
            scheduler (coalesce missed cron fires) against the gap instead
            of letting wall-clock catch-up storm on resume.
    """

    suspended: bool
    gap_seconds: float = 0.0
    restart_transports: bool = False
    reconcile_schedule: bool = False


@runtime_checkable
class ThawPolicyProtocol(Protocol):
    """Protocol for freeze-thaw (involuntary host-suspend) detection.

    Pure, import-free decision contract consumed by the wrapper's
    ``BotOS`` run-loop. The wrapper ticks the policy with a matched pair
    of ``time.monotonic()`` and ``time.time()`` readings; the policy
    compares the elapsed monotonic delta against the elapsed wall-clock
    delta and returns a :class:`ThawDecision`. On Linux ``CLOCK_MONOTONIC``
    does not advance while the host is suspended, so a wall-clock delta
    that runs far ahead of the monotonic delta is a positive signature of
    a freeze the process could not otherwise observe. Concrete recovery
    (restart channel sockets when idle, refresh presence, reconcile the
    scheduler) lives in the wrapper; this contract keeps the *detection*
    testable in isolation.
    """

    def observe(self, *, monotonic_now: float, wall_now: float) -> ThawDecision:
        """Return a :class:`ThawDecision` for the supplied clock readings."""
        ...


class WallClockGapThawPolicy:
    """Config-driven default freeze-thaw detector.

    The default referenced by ``gateway.thaw:`` blocks in ``gateway.yaml``
    and the ``BotOS(..., thaw_policy=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in
    core and is provable in isolation; the wrapper owns the side effects
    (restart channel sockets, refresh presence, reconcile the scheduler).

    A suspend gap is detected when, between two consecutive
    :meth:`observe` calls, the wall-clock delta ran ahead of the monotonic
    delta by more than ``gap_threshold_s`` *and* the monotonic clock itself
    stayed near-frozen (advanced by no more than one tick plus a small
    tolerance). Both conditions are the true signature of a frozen host:
    wall-clock jumps forward while ``CLOCK_MONOTONIC`` stalls. The reported
    ``gap_seconds`` is the wall-vs-monotonic divergence — the time the host
    was actually frozen.

    Requiring the monotonic delta to stay near-frozen distinguishes a real
    host suspend from a forward *wall-clock correction* (NTP step / manual
    clock set) that occurs while the process is running normally: in the
    correction case monotonic keeps advancing on schedule, so no recovery
    is requested and healthy transports/schedule are left untouched.

    The first observation only seeds the baseline and never reports a gap,
    so the default preserves current behaviour when no freeze occurs.

    Example::

        WallClockGapThawPolicy(tick_interval_s=15.0, gap_threshold_s=60.0)
    """

    def __init__(
        self,
        tick_interval_s: float = 15.0,
        gap_threshold_s: float = 60.0,
        enabled: bool = True,
    ):
        if tick_interval_s <= 0:
            raise ValueError(
                f"tick_interval_s must be > 0, got {tick_interval_s!r}"
            )
        if gap_threshold_s <= 0:
            raise ValueError(
                f"gap_threshold_s must be > 0, got {gap_threshold_s!r}"
            )
        self.tick_interval_s = float(tick_interval_s)
        self.gap_threshold_s = float(gap_threshold_s)
        self.enabled = bool(enabled)
        self._last_monotonic: Optional[float] = None
        self._last_wall: Optional[float] = None

    def observe(self, *, monotonic_now: float, wall_now: float) -> ThawDecision:
        if not self.enabled:
            return ThawDecision(suspended=False)

        prev_monotonic = self._last_monotonic
        prev_wall = self._last_wall
        self._last_monotonic = monotonic_now
        self._last_wall = wall_now

        # First tick only seeds the baseline; nothing to compare against.
        if prev_monotonic is None or prev_wall is None:
            return ThawDecision(suspended=False)

        monotonic_delta = monotonic_now - prev_monotonic
        wall_delta = wall_now - prev_wall
        # Divergence: how far wall-clock ran ahead of the process's own
        # elapsed (monotonic) time — i.e. the frozen window.
        divergence = wall_delta - monotonic_delta

        # A real host suspend freezes CLOCK_MONOTONIC: it stalls, so across
        # the gap it advances by less than one scheduled tick. A forward
        # wall-clock *correction* (NTP step / manual set) instead leaves
        # monotonic advancing in step with the loop — a full tick or more —
        # proving the process kept running. Requiring monotonic to have
        # stalled below one tick rejects that false positive so healthy
        # transports and the scheduler are left untouched.
        monotonic_frozen = monotonic_delta < self.tick_interval_s
        gap_detected = (
            divergence > self.gap_threshold_s
            and monotonic_frozen
        )
        if not gap_detected:
            return ThawDecision(suspended=False)

        return ThawDecision(
            suspended=True,
            gap_seconds=divergence,
            restart_transports=True,
            reconcile_schedule=True,
        )


# ---------------------------------------------------------------------------
# Gateway graceful-drain on shutdown (Issue #2375)
# ---------------------------------------------------------------------------


@dataclass
class DrainDecision:
    """Result of a drain-wait evaluation.

    Attributes:
        keep_draining: Whether to keep waiting for in-flight turns.
        reason: Optional human-readable explanation (logged at drain end).
    """

    keep_draining: bool
    reason: str = ""


@runtime_checkable
class GatewayDrainPolicyProtocol(Protocol):
    """Protocol for graceful-drain decisions on gateway shutdown.

    Pure, import-free decision contract consumed by the wrapper's
    ``BotOS`` shutdown path. On ``SIGTERM``/``SIGINT`` (rolling deploy,
    auto-update, host restart) the wrapper stops accepting new inbound
    and then repeatedly asks this policy whether to keep waiting for
    in-flight agent turns to finish, up to a bounded deadline. The
    wrapper supplies live facts (running turns, seconds elapsed); the
    policy decides whether the drain should continue. Concrete teardown
    (cancel tasks, stop transports, flush outbox) lives in the wrapper;
    this contract keeps the *wait condition* testable in isolation.

    A config-driven default (:class:`DrainTimeoutPolicy`) is provided for
    the common "wait for in-flight turns up to N seconds" case.
    """

    def should_keep_draining(
        self,
        *,
        running_turns: int,
        seconds_elapsed: float,
    ) -> DrainDecision:
        """Return a :class:`DrainDecision` for the supplied facts."""
        ...


class DrainTimeoutPolicy:
    """Config-driven graceful-drain policy for safe shutdown.

    The default referenced by ``drain_timeout`` in ``gateway.yaml`` and
    the ``BotOS(..., drain_timeout=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in
    core and is provable in isolation; the wrapper owns the side effects
    (quiesce ingress, wait, flush outbox, then tear down).

    Drain continues while *both* guards hold:

    * at least one agent turn is still in flight (``running_turns > 0``),
    * the elapsed wait is still within ``drain_timeout_seconds``.

    A ``drain_timeout_seconds`` of ``0`` disables draining entirely
    (today's behaviour: in-flight turns are cancelled immediately).

    Example::

        DrainTimeoutPolicy(drain_timeout_seconds=30)
    """

    def __init__(self, drain_timeout_seconds: float = 30.0):
        import math

        try:
            seconds = float(drain_timeout_seconds)
        except (TypeError, ValueError):
            raise ValueError(
                f"drain_timeout_seconds must be a number, got {drain_timeout_seconds!r}"
            )
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError(
                f"drain_timeout_seconds must be a finite value >= 0, "
                f"got {drain_timeout_seconds!r}"
            )
        self.drain_timeout_seconds = seconds

    def should_keep_draining(
        self,
        *,
        running_turns: int,
        seconds_elapsed: float,
    ) -> DrainDecision:
        if self.drain_timeout_seconds <= 0:
            return DrainDecision(keep_draining=False, reason="drain disabled")
        if running_turns <= 0:
            return DrainDecision(
                keep_draining=False,
                reason="no agent turns in flight",
            )
        if seconds_elapsed >= self.drain_timeout_seconds:
            return DrainDecision(
                keep_draining=False,
                reason=(
                    f"drain timeout: {running_turns} turn(s) still in flight "
                    f"after {seconds_elapsed:.0f}s"
                ),
            )
        return DrainDecision(
            keep_draining=True,
            reason=f"{running_turns} turn(s) in flight; draining",
        )


# ---------------------------------------------------------------------------
# Gateway inbound admission control (Issue #2454)
#
# The gateway protects the *outbound* path (slow-consumer eviction, bounded
# send queues, send-rate limiting) and serialises runs *per user*, but it has
# no gateway-wide ceiling on concurrent inbound agent runs. A burst of inbound
# traffic from many distinct users therefore translates directly into a burst
# of concurrent provider calls, with no admission gate in front of it.
#
# This is the pure, import-free decision contract for an admission gate. The
# wrapper's run-dispatch path (``BotSessionManager.chat``) supplies live facts
# (in-flight and queued counts) and the policy returns an ``AdmissionDecision``:
# admit now, queue (wait for capacity), or reject (busy ack). A config-driven
# default (:class:`ConcurrencyLimitPolicy`) is provided for the common bounded
# concurrency + bounded queue case; the wrapper owns the semaphore/queue
# mechanism (it needs the running event loop), this owns the *decision*.
# ---------------------------------------------------------------------------


class AdmissionDecision(str, Enum):
    """Outcome of an inbound admission evaluation.

    * ``ADMIT`` — capacity is available; run immediately.
    * ``QUEUE`` — at the concurrency ceiling but the wait queue has room;
      block until a slot frees up.
    * ``REJECT`` — over capacity and the queue is full; shed the run with a
      busy acknowledgement (a ``503``-style signal to the user).
    """

    ADMIT = "admit"
    QUEUE = "queue"
    REJECT = "reject"


@runtime_checkable
class GatewayConcurrencyPolicyProtocol(Protocol):
    """Protocol for gateway-wide inbound admission decisions.

    Pure, import-free decision contract consumed by the wrapper's run-dispatch
    path. The wrapper supplies the live aggregate counts (turns currently
    in flight and turns currently waiting) and the policy decides whether the
    next inbound turn may run now, must wait, or should be shed. Concrete
    enforcement (an ``asyncio.Semaphore`` ceiling plus a bounded
    ``asyncio.Queue`` with per-session fairness) lives in the wrapper, since it
    needs the running event loop and live session manager; this contract keeps
    the *decision* testable in isolation.

    A config-driven default (:class:`ConcurrencyLimitPolicy`) is provided for
    the common "N concurrent runs, bounded wait queue, declared overflow"
    case.
    """

    max_concurrent_runs: int
    queue_depth: int

    def decide(
        self,
        *,
        in_flight: int,
        queued: int,
        session_id: str = "",
    ) -> AdmissionDecision:
        """Return an :class:`AdmissionDecision` for the supplied facts."""
        ...


class ConcurrencyLimitPolicy:
    """Config-driven inbound admission policy for a bounded gateway.

    The default referenced by ``gateway.max_concurrent_runs`` /
    ``gateway.queue_depth`` / ``gateway.overflow_policy`` in ``gateway.yaml``
    and the ``BotOS(..., max_concurrent_runs=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in core and
    is provable in isolation; the wrapper owns the side effects (acquire a
    semaphore slot, enqueue/dequeue, return a busy ack).

    The decision is:

    * ``ADMIT`` while ``in_flight < max_concurrent_runs``.
    * At the ceiling, ``QUEUE`` while ``queued < queue_depth`` and the
      ``overflow_policy`` permits waiting.
    * Otherwise the ``overflow_policy`` decides the shed behaviour:
        - ``"reject"`` → :attr:`AdmissionDecision.REJECT` (busy ack).
        - ``"queue"`` → :attr:`AdmissionDecision.QUEUE` (block beyond the
          declared depth — for callers that prefer unbounded waiting to
          shedding; the wrapper still bounds the actual queue object).
        - ``"shed_oldest"`` → :attr:`AdmissionDecision.QUEUE`; the wrapper
          drops the oldest waiter to make room rather than rejecting the new
          arrival.

    A ``max_concurrent_runs`` of ``0`` disables admission control entirely
    (today's behaviour: every inbound turn is admitted immediately).

    Example::

        ConcurrencyLimitPolicy(max_concurrent_runs=32, queue_depth=128,
                               overflow_policy="reject")
    """

    _OVERFLOW = ("reject", "queue", "shed_oldest")

    def __init__(
        self,
        max_concurrent_runs: int = 0,
        queue_depth: int = 0,
        overflow_policy: str = "reject",
    ):
        try:
            ceiling = int(max_concurrent_runs)
        except (TypeError, ValueError):
            raise ValueError(
                f"max_concurrent_runs must be an integer, "
                f"got {max_concurrent_runs!r}"
            )
        if ceiling < 0:
            raise ValueError(
                f"max_concurrent_runs must be >= 0, got {max_concurrent_runs!r}"
            )
        try:
            depth = int(queue_depth)
        except (TypeError, ValueError):
            raise ValueError(
                f"queue_depth must be an integer, got {queue_depth!r}"
            )
        if depth < 0:
            raise ValueError(f"queue_depth must be >= 0, got {queue_depth!r}")
        overflow = (overflow_policy or "reject").strip().lower()
        if overflow not in self._OVERFLOW:
            raise ValueError(
                f"overflow_policy must be one of {self._OVERFLOW}, "
                f"got {overflow_policy!r}"
            )
        self.max_concurrent_runs = ceiling
        self.queue_depth = depth
        self.overflow_policy = overflow

    @property
    def enabled(self) -> bool:
        """Whether admission control is active (a positive ceiling is set)."""
        return self.max_concurrent_runs > 0

    def decide(
        self,
        *,
        in_flight: int,
        queued: int,
        session_id: str = "",
    ) -> AdmissionDecision:
        # Disabled: preserve legacy always-admit behaviour.
        if self.max_concurrent_runs <= 0:
            return AdmissionDecision.ADMIT
        if in_flight < self.max_concurrent_runs:
            return AdmissionDecision.ADMIT
        # At the ceiling: consult the bounded wait queue.
        if queued < self.queue_depth:
            return AdmissionDecision.QUEUE
        # Queue is full: declared overflow behaviour.
        if self.overflow_policy == "queue":
            # Caller opted into waiting beyond the declared depth.
            return AdmissionDecision.QUEUE
        if self.overflow_policy == "shed_oldest":
            # Make room by dropping the oldest waiter (wrapper enforces).
            return AdmissionDecision.QUEUE
        return AdmissionDecision.REJECT


# Backward-compatible alias following the repo's ``*Protocol`` convention.
GatewayConcurrencyPolicy = GatewayConcurrencyPolicyProtocol


# ---------------------------------------------------------------------------
# Gateway resource-pressure admission (Issue #3445)
#
# Admission today is concurrency/CPU-scaled and blind to memory; on a small
# always-on host a burst of concurrent turns drives RSS up until the OOM
# killer fires — the failure a $5 box hits first. This adds a pure, import-
# free decision that maps a resource *sample* (current RSS) onto the existing
# :class:`AdmissionDecision` so the gate can queue under soft pressure and
# shed under hard pressure *before* the process is killed. It reuses the
# admission seam (no new subsystem) and sits beside the concurrency / rate-
# limit / scale-to-zero policy family. The live sampler (reading
# ``resource.getrusage`` / optional ``psutil``) and the wiring into the gate
# live in the wrapper; this contract keeps the decision testable in isolation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceSample:
    """A point-in-time snapshot of the gateway process's resource usage.

    Attributes:
        rss_mb: Resident set size in mebibytes, or ``None`` when the platform
            cannot report it (the policy then admits and self-disables so the
            monitor never crashes the gateway it protects).
    """

    rss_mb: Optional[float] = None


@runtime_checkable
class ResourcePressurePolicyProtocol(Protocol):
    """Protocol for memory/resource-aware admission decisions.

    Pure, import-free decision contract consumed by the wrapper's admission
    gate. The wrapper samples its own resource usage on a lightweight cadence
    and hands the policy a :class:`ResourceSample`; the policy returns an
    :class:`AdmissionDecision` — ``ADMIT`` below the soft threshold, ``QUEUE``
    to apply backpressure above it, and ``REJECT`` above the hard threshold so
    the process sheds load before the OOM killer fires. Sampling and
    enforcement (the ``asyncio.Semaphore`` ceiling and bounded wait queue)
    live in the wrapper; this keeps the *decision* provable in isolation,
    symmetric with :class:`GatewayConcurrencyPolicyProtocol`.

    A config-driven default (:class:`MemoryPressurePolicy`) is provided for
    the common "soft/hard RSS threshold" case.
    """

    def evaluate(self, sample: ResourceSample) -> AdmissionDecision:
        """Return an :class:`AdmissionDecision` for the supplied sample."""
        ...


class MemoryPressurePolicy:
    """Config-driven RSS-threshold resource-pressure policy.

    The default wired by the ``max_rss_mb`` gateway config key
    (``BotOS(max_rss_mb=...)`` / ``gateway.yaml``) and the
    ``AdmissionGate(resource_policy=...)`` Python surface. It is intentionally
    minimal and dependency-free so the decision lives in core and is provable
    in isolation; the wrapper owns the live sampler and the side effects
    (queue / shed / busy ack).

    The decision, given a sample's ``rss_mb``:

    * ``ADMIT`` while ``rss_mb < soft_rss_mb`` (or the platform can't report
      memory, so ``rss_mb is None`` — never block on a missing signal).
    * ``QUEUE`` (apply backpressure) while ``soft_rss_mb <= rss_mb <
      hard_rss_mb``.
    * ``REJECT`` (shed with a busy ack) while ``rss_mb >= hard_rss_mb``.

    A ``hard_rss_mb`` of ``0`` disables pressure-based shedding entirely
    (every sample admits) — the legacy default when no threshold is set.

    Example::

        MemoryPressurePolicy(soft_rss_mb=400, hard_rss_mb=550)
    """

    def __init__(
        self,
        soft_rss_mb: float = 0.0,
        hard_rss_mb: float = 0.0,
    ):
        try:
            soft = float(soft_rss_mb or 0.0)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"soft_rss_mb must be a number, got {soft_rss_mb!r}"
            ) from err
        try:
            hard = float(hard_rss_mb or 0.0)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"hard_rss_mb must be a number, got {hard_rss_mb!r}"
            ) from err
        if soft < 0:
            raise ValueError(f"soft_rss_mb must be >= 0, got {soft_rss_mb!r}")
        if hard < 0:
            raise ValueError(f"hard_rss_mb must be >= 0, got {hard_rss_mb!r}")
        # A soft threshold above the hard one would queue turns that should be
        # shed; fail fast rather than silently invert the pressure ladder.
        if soft and hard and soft > hard:
            raise ValueError(
                f"soft_rss_mb ({soft_rss_mb!r}) must be <= "
                f"hard_rss_mb ({hard_rss_mb!r})"
            )
        self.soft_rss_mb = soft
        self.hard_rss_mb = hard

    @property
    def enabled(self) -> bool:
        """Whether pressure-based admission is active (a threshold is set)."""
        return self.soft_rss_mb > 0 or self.hard_rss_mb > 0

    def evaluate(self, sample: ResourceSample) -> AdmissionDecision:
        # Disabled, or the platform can't report memory: never block on a
        # missing/absent signal — admit and let concurrency limits apply.
        if not self.enabled:
            return AdmissionDecision.ADMIT
        rss = getattr(sample, "rss_mb", None)
        if rss is None:
            return AdmissionDecision.ADMIT
        if self.hard_rss_mb and rss >= self.hard_rss_mb:
            return AdmissionDecision.REJECT
        if self.soft_rss_mb and rss >= self.soft_rss_mb:
            return AdmissionDecision.QUEUE
        return AdmissionDecision.ADMIT


# ---------------------------------------------------------------------------
# Gateway memory-pressure cache eviction (Issue #3804)
#
# ``MemoryPressurePolicy`` above sheds *new* inbound turns under RSS pressure,
# but it never reclaims the memory already held by *idle* warm per-session
# agent caches. On a memory-limited host (a "$5 VPS", a Fly machine, a k8s pod
# with a cgroup limit) a busy gateway accumulates dozens of warm caches and,
# absent eviction, keeps climbing until the kernel OOM-kills the whole process
# — dropping *every* live session at once. This adds a pure, import-free
# planner that, given a memory *budget* and the LRU order of warm sessions,
# names the coldest rebuildable caches to soft-evict *before* the OOM killer
# fires. Each victim is transparently rebuilt from the persisted session store
# on its next turn, so eviction is cheap and lossless — as long as we never
# evict a session with an unflushed transcript or an in-flight turn.
#
# The *decision* lives here (provable in isolation, no event loop, no heavy
# imports), mirroring :class:`MemoryPressurePolicy`; the *mechanism* — the warm
# registry, the LRU order and the flushed/in-flight signals, plus reading the
# cgroup limit and anon RSS — lives in the running gateway (the wrapper).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WarmSession:
    """A warm per-session agent cache eligible for memory-pressure eviction.

    A pure, import-free fact carried from the running gateway to
    :func:`plan_pressure_evictions`. Attributes:

    * ``session_id``: the cache key to soft-evict.
    * ``last_activity``: monotonic/epoch seconds of the session's last turn;
      the planner evicts the coldest (smallest ``last_activity``) first.
    * ``in_flight``: ``True`` while a turn is executing — never evicted (would
      abort live work).
    * ``flushed``: ``True`` when the transcript is durably persisted — only a
      flushed cache is rebuildable, so an unflushed one is never evicted
      (would lose data).
    """

    session_id: str
    last_activity: float = 0.0
    in_flight: bool = False
    flushed: bool = True


@runtime_checkable
class MemoryPressureProtocol(Protocol):
    """Protocol for reading the memory budget and pressure of a gateway host.

    Pure contract the gateway implements over its own process: report the
    container's memory limit (from the cgroup v1/v2 memory limit) and the
    current anonymous (non-reclaimable) RSS, so the eviction budget tracks the
    *real* container ceiling rather than a hard-coded number. Both return
    ``None``/``0`` gracefully when the platform can't report them, so the
    planner degrades to a no-op instead of crashing the gateway it protects.
    """

    def cgroup_limit_mb(self) -> Optional[float]:
        """Return the container memory limit in MiB, or ``None`` if unknown."""
        ...

    def anon_rss_mb(self) -> float:
        """Return current anonymous (non-reclaimable) RSS in MiB."""
        ...


def plan_pressure_evictions(
    budget_mb: Optional[float],
    rss_mb: float,
    warm_sessions: Sequence[WarmSession],
    *,
    headroom_ratio: float = 0.9,
) -> List[str]:
    """Return the ``session_id``s to soft-evict, coldest (LRU) first.

    A pure planner: it takes the container memory *budget* (typically the
    cgroup limit), the current anonymous ``rss_mb`` and the warm-cache
    registry, and names the coldest rebuildable caches to shed until RSS is
    back within ``headroom_ratio`` of the budget. It never touches the event
    loop or the caches themselves — the gateway enacts the returned plan.

    Guards (a victim is *skipped*, never evicted, when):

    * ``in_flight`` is ``True`` — an executing turn must not be aborted, or
    * ``flushed`` is ``False`` — an unflushed transcript is not yet rebuildable
      from the store, so evicting it would lose data.

    Returns an empty list when RSS is within budget, the budget is unknown
    (``None``/``<= 0``), or nothing evictable remains — so a host that can't
    report a cgroup limit simply never soft-evicts (legacy behaviour).
    """
    if budget_mb is None:
        return []
    try:
        budget = float(budget_mb)
        rss = float(rss_mb)
    except (TypeError, ValueError):
        return []
    # Reject non-finite measurements (NaN/inf): a NaN budget or rss would slip
    # past the ``rss <= target`` check (every comparison with NaN is False) and
    # spuriously evict *every* warm cache — the opposite of protecting them.
    if not math.isfinite(budget) or not math.isfinite(rss) or budget <= 0:
        return []
    try:
        ratio = float(headroom_ratio)
    except (TypeError, ValueError):
        ratio = 0.9
    if not (math.isfinite(ratio) and 0.0 < ratio <= 1.0):
        ratio = 0.9
    target = budget * ratio
    if rss <= target:
        return []

    # Name the coldest evictable caches, LRU-first. We deliberately do not
    # track per-cache bytes (guessing sizes would be scope creep) so we cannot
    # remeasure RSS mid-plan; instead the planner returns every evictable cache
    # coldest-first and the gateway evicts down that ordered list, re-sampling
    # its own RSS as it goes and stopping as soon as it is back within target.
    # Over-shedding is thus avoided by the enactor and under-shedding is caught
    # on the next pass — keeping this decision pure and byte-agnostic.
    evictable = [
        s for s in warm_sessions
        if not s.in_flight and s.flushed
    ]
    if not evictable:
        return []
    evictable.sort(key=lambda s: (s.last_activity, s.session_id))
    return [s.session_id for s in evictable]


# ---------------------------------------------------------------------------
# Gateway rate-limit admission (Issue #2532)
#
# Rate limiting completes the gateway's policy-protocol family (send, idle,
# drain, concurrency). Like its siblings it is a pure, import-free decision
# over typed facts — an identity, a scope (endpoint class / channel / tenant)
# and a timestamp — returning a closed :class:`RateLimitDecision`. Core ships
# a config-driven sliding-window default (:class:`SlidingWindowRateLimitPolicy`)
# that reproduces today's built-in behaviour; the wrapper limiters adopt the
# protocol and developers can inject their own (per-tenant, distributed,
# cost-based) without importing wrapper internals. Core maps a ``limited``
# decision onto ``ConnectErrorCode.RATE_LIMITED`` +
# ``HelloError.retry_after_seconds``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a rate-limit evaluation.

    Attributes:
        allowed: Whether the request may proceed.
        retry_after_seconds: Backoff hint populated when ``allowed`` is
            ``False`` (seconds until the caller may retry); ``None`` when
            allowed.
    """

    allowed: bool
    retry_after_seconds: Optional[float] = None


@runtime_checkable
class RateLimitPolicyProtocol(Protocol):
    """Protocol for gateway rate-limit / throttle admission decisions.

    Pure, import-free decision contract consumed by the wrapper's admission
    paths. The wrapper supplies typed facts (the caller ``identity``, the
    ``scope`` — an endpoint class, channel, or tenant token — and the current
    ``now`` timestamp) and the policy decides whether the request is allowed
    or ``limited`` with a ``retry_after_seconds`` hint. Concrete state and
    enforcement (sliding windows, token buckets, a Redis-backed per-tenant
    quota) live in the implementation; this contract keeps the *decision*
    injectable and testable in isolation, symmetric with
    :class:`SendPolicyProtocol` / :class:`GatewayConcurrencyPolicyProtocol`.

    A config-driven default (:class:`SlidingWindowRateLimitPolicy`) is
    provided for the common "N requests per window per identity" case; core
    maps a ``limited`` decision onto ``ConnectErrorCode.RATE_LIMITED`` and
    ``HelloError.retry_after_seconds``.
    """

    def check(
        self,
        *,
        identity: str,
        scope: str,
        now: float,
    ) -> RateLimitDecision:
        """Return a :class:`RateLimitDecision` for the supplied facts."""
        ...


class SlidingWindowRateLimitPolicy:
    """Config-driven sliding-window rate-limit policy.

    The default referenced by ``gateway.rate_limit`` blocks in
    ``gateway.yaml`` and the ``WebSocketGateway(..., rate_limit_policy=...)``
    Python surface. It is intentionally minimal and dependency-free so the
    decision lives in core and is provable in isolation; heavy wrapper
    limiters (``gateway/rate_limiter.py`` sliding window,
    ``bots/_rate_limit.py`` token bucket) may adopt this protocol while
    keeping their own state and side effects.

    The decision, keyed by ``(scope, identity)``:

    * ``allowed`` while fewer than ``max_requests`` have been seen in the
      current ``window_seconds`` window.
    * Once the window count exceeds ``max_requests``, the key enters a
      ``lockout_seconds`` cooldown and every :meth:`check` returns
      ``allowed=False`` with a ``retry_after_seconds`` hint until it elapses.

    A ``max_requests`` of ``0`` disables limiting entirely (every request is
    allowed) — the legacy default when no rate limit is configured.

    This class is not internally synchronised; the wrapper owns any locking
    it needs for concurrent hot paths (the built-in limiters already do).

    State ownership: per-``(scope, identity)`` window/lockout entries are
    reclaimed lazily — a key's entry is dropped or overwritten the next time
    that key is checked. It keeps one entry per *active* key and is intended
    for a bounded identity space (endpoint classes, authenticated tenants). A
    wrapper exposing it to an unbounded/untrusted identity space (e.g. raw
    per-IP keys) owns periodic reclamation, exactly as it owns locking.

    Example::

        SlidingWindowRateLimitPolicy(max_requests=5, window_seconds=60,
                                     lockout_seconds=300)
    """

    def __init__(
        self,
        max_requests: int = 0,
        window_seconds: float = 60.0,
        lockout_seconds: float = 0.0,
    ):
        try:
            ceiling = int(max_requests)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"max_requests must be an integer, got {max_requests!r}"
            ) from err
        if ceiling < 0:
            raise ValueError(f"max_requests must be >= 0, got {max_requests!r}")
        try:
            window = float(window_seconds)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"window_seconds must be a number, got {window_seconds!r}"
            ) from err
        if window <= 0:
            raise ValueError(
                f"window_seconds must be > 0, got {window_seconds!r}"
            )
        try:
            lockout = float(lockout_seconds)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"lockout_seconds must be a number, got {lockout_seconds!r}"
            ) from err
        if lockout < 0:
            raise ValueError(
                f"lockout_seconds must be >= 0, got {lockout_seconds!r}"
            )
        self.max_requests = ceiling
        self.window_seconds = window
        self.lockout_seconds = lockout
        # (scope, identity) -> (window_start, count)
        self._windows: Dict[Tuple[str, str], Tuple[float, int]] = {}
        # (scope, identity) -> lockout_expires_at
        self._lockouts: Dict[Tuple[str, str], float] = {}

    @property
    def enabled(self) -> bool:
        """Whether limiting is active (a positive ceiling is set)."""
        return self.max_requests > 0

    def check(
        self,
        *,
        identity: str,
        scope: str,
        now: float,
    ) -> RateLimitDecision:
        # Disabled: preserve legacy always-allow behaviour.
        if self.max_requests <= 0:
            return RateLimitDecision(allowed=True)

        key = (scope, identity)

        # Active lockout?
        lockout_until = self._lockouts.get(key)
        if lockout_until is not None:
            if now < lockout_until:
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=max(0.0, lockout_until - now),
                )
            # Expired lockout: clear and start fresh.
            del self._lockouts[key]

        window = self._windows.get(key)
        if window is None or (now - window[0]) >= self.window_seconds:
            # New or expired window.
            self._windows[key] = (now, 1)
            return RateLimitDecision(allowed=True)

        window_start, count = window
        count += 1
        if count > self.max_requests:
            # Over the ceiling within the window.
            if self.lockout_seconds > 0:
                # Cooldown: drop the window and lock the key out until it
                # elapses.
                del self._windows[key]
                retry = self.lockout_seconds
                self._lockouts[key] = now + self.lockout_seconds
            else:
                # No cooldown: keep the window so the key stays denied until
                # it naturally expires, matching the retry hint. Deleting it
                # here would let the next check start a fresh window and be
                # allowed immediately, bypassing the ceiling.
                self._windows[key] = (window_start, count)
                retry = max(0.0, self.window_seconds - (now - window_start))
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry,
            )

        self._windows[key] = (window_start, count)
        return RateLimitDecision(allowed=True)


# Backward-compatible alias following the repo's ``*Protocol`` convention.
RateLimitPolicy = RateLimitPolicyProtocol


# ---------------------------------------------------------------------------
# Durable-queue dead-letter decision (Issue #3519)
#
# The gateway's durable inbound journal and outbound queue must decide when a
# repeatedly-failing entry is a genuine *poison message* (dead-letter it) vs a
# victim of a *transient channel outage* (keep retrying). Deciding on the
# attempt counter alone dead-letters deliverable traffic during a routine
# few-minute API incident, because the exponential backoff burns the default
# five attempts in well under a minute — a silent-loss failure the durable
# queue exists to prevent.
#
# The fix is a pure, import-free *decision* contract, symmetric with the other
# gateway policy protocols above (``SendPolicyProtocol``,
# ``RateLimitPolicyProtocol``): a recoverable/transient failure is only
# dead-lettered once it is BOTH attempt-exhausted AND genuinely old, while a
# permanently-classified error (credentials revoked, permanent target) still
# short-circuits immediately. The durable-queue runtime in ``praisonai-bot``
# consumes it where it currently tests ``attempts >= max_attempts``.
# ---------------------------------------------------------------------------


# Error classes that are already *known-permanent* and should dead-letter
# immediately regardless of age — no amount of retrying recovers a revoked
# credential or a permanently-invalid target.
PERMANENT_ERROR_CLASSES: Tuple[str, ...] = ("credential", "permanent_target")


@dataclass(frozen=True)
class DeadLetterDecision:
    """Result of a dead-letter evaluation.

    Attributes:
        dead_letter: Whether the entry should be routed to the dead-letter
            queue / marked ``permanent_failure`` now. When ``False`` the
            caller reschedules the entry under its normal capped backoff.
        reason: Short machine-readable explanation (``"permanent_error"``,
            ``"attempts_and_age"``, ``"retry"``) for logging/metrics.
    """

    dead_letter: bool
    reason: str = ""


@runtime_checkable
class DeadLetterPolicyProtocol(Protocol):
    """Protocol for the durable-queue dead-letter decision.

    Pure, import-free decision contract consumed by the outbound queue's
    ``drain`` and the inbound journal's redelivery/replay paths. The runtime
    supplies typed facts about a repeatedly-failing entry (its ``attempts``,
    the ``first_seen_epoch`` it was first received, the current ``now_epoch``,
    and a coarse ``error_class``) and the policy returns a
    :class:`DeadLetterDecision`. Concrete queue state and side effects (SQLite
    rows, DLQ enqueue) stay in the implementation; this keeps the *policy*
    injectable and testable in isolation, symmetric with
    :class:`SendPolicyProtocol` / :class:`RateLimitPolicyProtocol`.

    A config-driven default (:class:`AttemptAndAgeDeadLetterPolicy`) is
    provided for the common "poison vs transient" case.
    """

    def should_dead_letter(
        self,
        *,
        attempts: int,
        first_seen_epoch: float,
        now_epoch: float,
        error_class: str = "",
    ) -> DeadLetterDecision:
        """Return a :class:`DeadLetterDecision` for the supplied facts."""
        ...


class AttemptAndAgeDeadLetterPolicy:
    """Default dead-letter policy: require BOTH attempt-exhaustion AND age.

    Distinguishes a *poison message* (fails repeatedly over a long time) from
    a *transient outage* (fails a few times quickly, then recovers). A
    recoverable/transient failure is dead-lettered only once it satisfies
    **both**:

    1. ``attempts >= max_attempts``, and
    2. ``age >= min_age_seconds`` (wall-clock age since first receipt).

    Until an entry is genuinely old it keeps retrying under capped backoff
    rather than being discarded, so a brief channel incident results in
    delayed-but-delivered messages rather than a DLQ full of manual-replay
    work. A truly poisoned entry still dead-letters — it keeps failing past
    both thresholds.

    An error whose ``error_class`` is known-permanent (see
    :data:`PERMANENT_ERROR_CLASSES` — a revoked credential or a permanently
    invalid target) short-circuits to dead-letter immediately regardless of
    age, since retrying can never recover it.

    ``min_age_seconds=0`` restores the legacy attempt-count-only behaviour,
    keeping the knob fully backward-compatible for callers that opt in.

    Example::

        AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=6*3600)
    """

    #: Default minimum age (6 hours) before a transient failure may dead-letter.
    DEFAULT_MIN_AGE_SECONDS: int = 6 * 3600

    def __init__(
        self,
        max_attempts: int = 5,
        min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS,
    ) -> None:
        try:
            attempts_ceiling = int(max_attempts)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"max_attempts must be an integer, got {max_attempts!r}"
            ) from err
        if attempts_ceiling < 1:
            raise ValueError(
                f"max_attempts must be >= 1, got {max_attempts!r}"
            )
        try:
            min_age = float(min_age_seconds)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"min_age_seconds must be a number, got {min_age_seconds!r}"
            ) from err
        if min_age < 0:
            raise ValueError(
                f"min_age_seconds must be >= 0, got {min_age_seconds!r}"
            )
        self.max_attempts = attempts_ceiling
        self.min_age_seconds = min_age

    def should_dead_letter(
        self,
        *,
        attempts: int,
        first_seen_epoch: float,
        now_epoch: float,
        error_class: str = "",
    ) -> DeadLetterDecision:
        # Known-permanent conditions can never be recovered by retrying.
        if error_class in PERMANENT_ERROR_CLASSES:
            return DeadLetterDecision(dead_letter=True, reason="permanent_error")

        exhausted = attempts >= self.max_attempts
        # Guard against a missing/zero first-seen stamp: treat it as "just now"
        # so a malformed row is never prematurely dead-lettered on age.
        age = now_epoch - first_seen_epoch if first_seen_epoch else 0.0
        old_enough = age >= self.min_age_seconds

        if exhausted and old_enough:
            return DeadLetterDecision(dead_letter=True, reason="attempts_and_age")
        return DeadLetterDecision(dead_letter=False, reason="retry")


# ---------------------------------------------------------------------------
# Port-less, restart-safe external drain trigger (Issue #2390)
#
# Hosted/containerised deployments (Docker, Fly, Kubernetes) need to ask a
# *running* gateway to drain — finish active turns, stop accepting new ones,
# then exit — without exposing an inbound control port (a port is attack
# surface the gateway deliberately avoids). The mechanism is a presence-based
# marker file (e.g. ``~/.praisonai/gateway/.drain_request.json``) that a
# background watcher in the wrapper reads. The marker is stamped with an
# *instantiation epoch* (kernel boot id + PID-1 start time); a marker left
# over from a prior instantiation on a durable volume is treated as stale and
# ignored, so a rebooted instance never wedges in "draining" forever.
#
# The epoch/staleness check is a pure, testable predicate and belongs in core
# beside ``ScaleToZeroPolicy``/``DrainTimeoutPolicy``; the watcher wiring and
# the ``praisonai gateway drain`` CLI live in the wrapper.
# ---------------------------------------------------------------------------


def current_epoch() -> str:
    """Return a stable identifier for the current OS *instantiation*.

    The epoch combines the most durable, restart-distinguishing signals
    available so a drain marker can be tied to the instantiation that wrote
    it. It is derived from (best-effort, in order of preference):

    * the kernel boot id (Linux ``/proc/sys/kernel/random/boot_id``), which
      changes on every reboot, and
    * the start time of PID 1 (the init process), which also changes on every
      boot / container (re)start.

    On platforms where neither is available the function degrades gracefully
    to an empty string; callers that cannot determine an epoch should treat
    *every* marker as foreign (fail-safe: ignore stale-looking requests) by
    pairing this with :class:`DrainMarkerPolicy`, which ignores markers whose
    epoch does not match the current one.

    Returns:
        A non-secret, opaque epoch token (``"<boot_id>:<pid1_start>"``) when
        *both* signals are available, or an empty string otherwise. Requiring
        both keeps the contract fail-closed: a partial epoch (e.g. ``boot_id``
        alone, which is unchanged across same-host container restarts) could
        let a durable stale marker match a fresh instance, so it is never
        emitted.
    """
    boot_id = ""
    try:
        with open("/proc/sys/kernel/random/boot_id", "r") as fh:
            boot_id = fh.read().strip()
    except (OSError, ValueError):
        boot_id = ""

    pid1_start = ""
    try:
        # field 22 of /proc/1/stat is the process start time in clock ticks
        # since boot. Names can contain spaces/parens, so split on the final
        # ')' to reach the stable numeric tail.
        with open("/proc/1/stat", "r") as fh:
            raw = fh.read()
        tail = raw.rsplit(")", 1)[-1].split()
        # tail[0] is 'state'; field 22 overall == index 19 of the tail.
        if len(tail) > 19:
            pid1_start = tail[19]
    except (OSError, ValueError, IndexError):
        pid1_start = ""

    if boot_id and pid1_start:
        return f"{boot_id}:{pid1_start}"
    # Fail closed: a partial epoch cannot reliably distinguish a restart, so an
    # empty epoch is returned and DrainMarkerPolicy treats every marker as
    # foreign (ignored) unless ``require_epoch=False`` is set explicitly.
    return ""


class DrainMarkerPolicy:
    """Pure predicate deciding whether an external drain marker is actionable.

    A drain marker is a small JSON object written by an operator / deploy step
    (via ``praisonai gateway drain``) into a well-known path. A background
    watcher in the wrapper reads it and asks this policy whether the running
    gateway should react. The decision is intentionally side-effect free so it
    is provable in isolation without a live gateway or filesystem.

    A marker is honoured only when it requests a drain *for the current
    instantiation*:

    * a missing marker (``None``) is never a drain request;
    * a marker carrying no ``epoch`` is treated as foreign and ignored, so a
      hand-rolled or legacy file cannot wedge a process;
    * a marker whose ``epoch`` differs from ``current_epoch`` is stale — it
      survived a reboot/restart on a durable volume — and is ignored;
    * a current-epoch marker is honoured (subject to an optional
      already-handled de-duplication via ``last_handled_epoch``).

    Example::

        policy = DrainMarkerPolicy()
        if policy.drain_requested(read_marker(), current_epoch(), monotonic()):
            await gateway.stop(drain_timeout=cfg.gateway.drain_timeout)
    """

    def __init__(self, *, require_epoch: bool = True):
        self.require_epoch = bool(require_epoch)

    def drain_requested(
        self,
        marker: Optional[Dict[str, Any]],
        current_epoch: str,
        now: float,
        *,
        last_handled_epoch: Optional[str] = None,
    ) -> bool:
        """Return whether ``marker`` is a live drain request for this instance.

        Args:
            marker: Parsed marker contents, or ``None`` when no marker file is
                present.
            current_epoch: The current instantiation epoch (see
                :func:`current_epoch`).
            now: A monotonic timestamp (unused by the default policy; accepted
                so subclasses can implement TTL/debounce without changing the
                call site).
            last_handled_epoch: If supplied and equal to the marker's epoch,
                the request is treated as already handled and ignored, so a
                watcher polling repeatedly only fires once per instantiation.

        Returns:
            ``True`` only for a non-stale, current-epoch drain request that has
            not already been handled.
        """
        if not isinstance(marker, dict):
            return False

        marker_epoch = marker.get("epoch")
        if not isinstance(marker_epoch, str) or not marker_epoch:
            # No epoch stamp: cannot prove it belongs to this instantiation.
            # Fail safe by ignoring it unless epochs are explicitly optional.
            if self.require_epoch:
                return False
        elif marker_epoch != current_epoch:
            # A marker from a prior instantiation (e.g. survived a reboot on a
            # durable volume). Ignore it so a fresh instance never wedges.
            return False
        elif last_handled_epoch is not None and marker_epoch == last_handled_epoch:
            # Already acted on this instantiation's request.
            return False

        action = marker.get("action", "drain")
        if not isinstance(action, str):
            # A non-string action is a malformed marker; fail closed.
            return False
        if action.strip().lower() not in ("", "drain"):
            return False
        return True


# ---------------------------------------------------------------------------
# Crash / shutdown forensics (Issue #2436)
#
# A 24/7 gateway restarted by a supervisor (systemd/s6/Kubernetes) leaves no
# evidence of *why* it died when the death was not its own decision — OOM kill,
# supervisor ``SIGKILL``/``SIGTERM``, or a parent dying. The wrapper installs
# forensic signal handlers that capture a fast, non-blocking snapshot and spawn
# a detached diagnostic that survives a ``SIGKILL`` on the process group.
#
# The decision/formatting pieces that need no OS I/O live here as pure helpers
# beside ``ScaleToZeroPolicy``/``DrainTimeoutPolicy``/``DrainMarkerPolicy``; the
# heavy /proc reads, ``os.getrusage``/``os.getloadavg`` calls, and detached
# subprocess spawn live in the praisonai wrapper behind the protocol below.
# ---------------------------------------------------------------------------


@runtime_checkable
class ShutdownForensicsProtocol(Protocol):
    """Protocol for capturing forensics when a gateway dies unexpectedly.

    Pure contract consumed by the wrapper's signal handlers. ``snapshot``
    must be fast (<10ms), never raise, and never block the asyncio teardown;
    ``spawn_diagnostic`` is fire-and-forget and must run the diagnostic in a
    *detached* session so a ``SIGKILL`` on the process group does not also kill
    the diagnostic. Concrete OS I/O (``/proc`` reads, ``os.getrusage``,
    ``os.getloadavg``, subprocess spawn) lives in the wrapper implementation.
    """

    def snapshot(self, signal_name: Optional[str] = None) -> Dict[str, Any]:
        """Return a small, JSON-serialisable forensic context.

        Must never raise; on any internal failure it returns a best-effort
        (possibly partial) dict so the caller can still log *something*.
        """
        ...

    def spawn_diagnostic(self, ctx: Dict[str, Any], log_dir: Optional[str]) -> None:
        """Fire-and-forget a detached diagnostic into ``log_dir``.

        Must never raise and must not block the caller; the diagnostic runs in
        a detached session so it survives a ``SIGKILL`` on the process group.
        """
        ...


def format_forensics_for_log(ctx: Optional[Dict[str, Any]]) -> str:
    """Render a forensic snapshot dict as a single, stable log line.

    Pure and side-effect free so it is provable in isolation and safe to call
    from a signal handler. Unknown/missing fields are simply omitted; the
    output is a compact ``key=value`` sequence prefixed with a stable marker so
    operators (and log scrapers) can grep ``gateway-forensics`` reliably.

    Args:
        ctx: The dict returned by :meth:`ShutdownForensicsProtocol.snapshot`,
            or ``None``.

    Returns:
        A single-line, human-readable summary. Never raises.
    """
    if not isinstance(ctx, dict):
        return "gateway-forensics: <unavailable>"

    # Ordered so the most operationally useful facts come first.
    keys = (
        "signal",
        "pid",
        "ppid",
        "supervised",
        "loadavg_1m",
        "traced",
        "maxrss_kb",
    )
    parts: List[str] = []
    for key in keys:
        if key not in ctx:
            continue
        value = ctx[key]
        if value is None:
            continue
        if isinstance(value, bool):
            rendered = "yes" if value else "no"
        elif isinstance(value, float):
            rendered = f"{value:.2f}"
        else:
            rendered = str(value).replace("\n", " ").strip()
        if rendered == "":
            continue
        parts.append(f"{key}={rendered}")

    if not parts:
        return "gateway-forensics: <empty>"
    return "gateway-forensics: " + " ".join(parts)


def is_supervised(ppid: Optional[int], invocation_id: Optional[str]) -> bool:
    """Return whether the process appears to run under a service manager.

    Pure predicate. A process is considered supervised when either:

    * its parent is PID 1 (``ppid == 1`` — reparented to init / the container
      entrypoint), or
    * the systemd ``INVOCATION_ID`` environment variable is present (the unit
      was started by systemd).

    Args:
        ppid: The parent PID, or ``None`` when unavailable.
        invocation_id: The value of ``$INVOCATION_ID``, or ``None``/empty.

    Returns:
        ``True`` when either supervision signal is present.
    """
    if ppid == 1:
        return True
    return bool(invocation_id)


def drain_timeout_has_headroom(
    stop_timeout_s: Optional[float],
    drain_timeout_s: Optional[float],
    headroom_s: float = 30.0,
) -> bool:
    """Return whether the supervisor stop-timeout leaves room to drain.

    Pure predicate used by a startup sanity check. A supervisor whose
    stop-timeout is shorter than ``drain_timeout + headroom`` will ``SIGKILL``
    the gateway mid-drain, leaving no explanation. This returns ``False`` only
    when we can *prove* the headroom is insufficient; when either value is
    unknown (``None``) or non-positive it returns ``True`` (fail-open: do not
    emit a spurious warning when we cannot tell).

    Args:
        stop_timeout_s: The supervisor's configured stop-timeout in seconds, or
            ``None`` when it could not be determined.
        drain_timeout_s: The gateway's configured drain timeout in seconds, or
            ``None``/0 when draining is disabled.
        headroom_s: Slack to reserve beyond the drain window for teardown.

    Returns:
        ``True`` when there is adequate headroom (or it cannot be determined),
        ``False`` only when the stop-timeout is provably too short.
    """
    try:
        drain = float(drain_timeout_s) if drain_timeout_s is not None else 0.0
        head = float(headroom_s)
    except (TypeError, ValueError):
        return True
    if drain <= 0:
        # Draining disabled: nothing to be killed mid-drain.
        return True
    if stop_timeout_s is None:
        # Unknown supervisor timeout: cannot prove a problem.
        return True
    try:
        stop = float(stop_timeout_s)
    except (TypeError, ValueError):
        return True
    if stop <= 0:
        return True
    return stop >= drain + head


# ---------------------------------------------------------------------------
# Code-skew guard for hot operations (Issue #2460)
# ---------------------------------------------------------------------------


def detect_code_skew(
    boot_fp: Optional[str], disk_fp: Optional[str]
) -> Optional[Tuple[str, str]]:
    """Return shortened ``(boot, disk)`` fingerprints if the code changed.

    This is the pure, side-effect-free heart of the code-skew guard. It does
    not read the filesystem or git; callers pass the fingerprint captured at
    boot and a freshly-read on-disk fingerprint (see
    :func:`read_code_fingerprint`).

    The check is intentionally fail-open: if either fingerprint is unknown
    (``None`` / empty) it returns ``None`` so the caller proceeds normally and
    never blocks an operation just because the revision could not be read.

    Args:
        boot_fp: Fingerprint captured when the gateway started.
        disk_fp: Fingerprint of the code currently on disk.

    Returns:
        ``(boot_short, disk_short)`` when the running code differs from disk,
        otherwise ``None``. Git SHAs are shortened to 7 characters (including a
        leading SHA in a combined ``"<sha>+mtime:..."`` fingerprint); other
        fingerprints are returned unchanged.
    """
    if not boot_fp or not disk_fp:
        return None
    if boot_fp == disk_fp:
        return None

    def _is_sha(token: str) -> bool:
        return len(token) == 40 and all(c in "0123456789abcdef" for c in token.lower())

    def _short(fp: str) -> str:
        # Shorten bare git SHAs (40 hex chars) to the conventional 7, including
        # a leading SHA in a combined "<sha>+mtime:<ns>" fingerprint; leave
        # other fingerprint shapes (e.g. "mtime:...") untouched.
        if _is_sha(fp):
            return fp[:7]
        head, sep, tail = fp.partition("+")
        if sep and _is_sha(head):
            return f"{head[:7]}{sep}{tail}"
        return fp

    return (_short(boot_fp), _short(disk_fp))


# ---------------------------------------------------------------------------
# Restart-intent exit-code protocol (Issue #2437)
# ---------------------------------------------------------------------------
#
# When the gateway/bot process exits, its exit code is the only signal a
# process supervisor (systemd ``Restart=on-failure``, an s6 finish script,
# a Kubernetes restart policy) receives about whether coming back is worth
# it. A generic ``1`` makes a transient blip and a fatal misconfiguration
# look identical, so a misconfigured gateway crash-loops forever instead of
# stopping and surfacing the problem.
#
# These constants follow the ``sysexits.h`` convention so they compose with
# existing supervisor tooling without bespoke wrappers:
#
#   * ``EX_TEMPFAIL`` (75) — transient/restartable: ask the supervisor to
#     restart (network blip, upstream 503, intentional drain-then-restart).
#   * ``EX_CONFIG`` (78) — fatal config error: do NOT restart, fix the
#     config (duplicate token, no platforms, malformed ``gateway.yaml``,
#     invalid credentials at startup).
#
# The constants and the pure ``classify_exit_reason`` classifier live in
# core so the wrapper CLI, the runtime entry point, and any future runtime
# share one source of truth. The wrapper owns the actual ``sys.exit``.

GATEWAY_OK_EXIT_CODE = 0
"""Clean shutdown / success (EX_OK)."""

GATEWAY_RESTART_EXIT_CODE = 75
"""Transient/restartable failure — ask the supervisor to restart (EX_TEMPFAIL)."""

GATEWAY_FATAL_CONFIG_EXIT_CODE = 78
"""Fatal config error — supervisor should stop restarting; fix config (EX_CONFIG)."""


class FatalConfigError(Exception):
    """Raised on an unrecoverable gateway/bot configuration error.

    Signals that restarting the process is pointless until an operator
    fixes the configuration — e.g. two bots sharing one token, no
    messaging platform configured, a malformed ``gateway.yaml``, or an
    invalid credential detected at startup. The wrapper entry point maps
    this to :data:`GATEWAY_FATAL_CONFIG_EXIT_CODE` (78) so the supervisor
    halts the crash-loop and the failure is terminal and visible.
    """


def classify_exit_reason(exc: "BaseException | None") -> int:
    """Map an exit cause to a supervisor-friendly exit code (pure).

    The single source of truth shared by the wrapper CLI and runtime
    entry point. Side-effect free so it is provable in isolation.

    Args:
        exc: The exception that terminated the process, or ``None`` for a
            clean shutdown.

    Returns:
        * :data:`GATEWAY_OK_EXIT_CODE` (0) when ``exc`` is ``None`` or a
          ``KeyboardInterrupt``/``SystemExit(0)`` (clean stop).
        * :data:`GATEWAY_FATAL_CONFIG_EXIT_CODE` (78) for
          :class:`FatalConfigError` (do not restart — fix config).
        * :data:`GATEWAY_RESTART_EXIT_CODE` (75) for any other exception
          (transient — ask supervisor to restart).
    """
    if exc is None:
        return GATEWAY_OK_EXIT_CODE
    if isinstance(exc, KeyboardInterrupt):
        return GATEWAY_OK_EXIT_CODE
    if isinstance(exc, SystemExit):
        code = exc.code
        if code is None or code == 0:
            return GATEWAY_OK_EXIT_CODE
        return code if isinstance(code, int) else GATEWAY_RESTART_EXIT_CODE
    if isinstance(exc, FatalConfigError):
        return GATEWAY_FATAL_CONFIG_EXIT_CODE
    return GATEWAY_RESTART_EXIT_CODE


class RestartLoopGuard:
    """Pure rolling-window predicate that trips on a rapid restart loop.

    A companion to :func:`classify_exit_reason` for the crash-loop breaker
    referenced in Issue #3021. Where ``classify_exit_reason`` maps a *single*
    exit to a supervisor exit code, this tracks the *rate* of restart-worthy
    boots so a process that keeps crashing-on-resume can stop auto-resuming the
    offending work rather than wedging in a tight restart loop.

    It is intentionally side-effect free (records timestamps only, no I/O, no
    heavy deps) so both gateway runtimes (``BotOS`` and ``WebSocketGateway``)
    can reuse the same *decision* and prove it in isolation. The caller feeds a
    monotonic timestamp each time a restart-interrupted boot is observed and
    asks whether the breaker has tripped.

    A trip means: at least ``max_restarts`` restarts occurred within the last
    ``window_seconds``. When tripped, the caller should stop auto-resuming the
    offending session (while still serving real inbound) instead of restarting
    it again immediately.

    Example::

        guard = RestartLoopGuard(max_restarts=3, window_seconds=60)
        if guard.record(now=time.monotonic()):
            # too many restarts too fast — stop auto-resuming this session
            ...
    """

    def __init__(self, max_restarts: int = 3, window_seconds: float = 60.0):
        if max_restarts < 1:
            raise ValueError(f"max_restarts must be >= 1, got {max_restarts!r}")
        if window_seconds <= 0:
            raise ValueError(
                f"window_seconds must be > 0, got {window_seconds!r}"
            )
        self.max_restarts = int(max_restarts)
        self.window_seconds = float(window_seconds)
        self._events: "List[float]" = []

    def record(self, now: float) -> bool:
        """Record a restart at ``now`` and return whether the breaker tripped.

        Args:
            now: A monotonic timestamp for this restart event.

        Returns:
            ``True`` when at least ``max_restarts`` restarts have occurred
            within the trailing ``window_seconds`` (breaker tripped);
            ``False`` otherwise.
        """
        cutoff = now - self.window_seconds
        # Drop events that have aged out of the trailing window.
        self._events = [t for t in self._events if t >= cutoff]
        self._events.append(now)
        return len(self._events) >= self.max_restarts

    def tripped(self, now: float) -> bool:
        """Return whether the breaker is currently tripped without recording.

        Prunes aged-out events first so a burst that has since gone quiet is
        no longer considered a live loop.
        """
        cutoff = now - self.window_seconds
        self._events = [t for t in self._events if t >= cutoff]
        return len(self._events) >= self.max_restarts

    def reset(self) -> None:
        """Clear the recorded restart history (e.g. after a clean run)."""
        self._events = []


# ---------------------------------------------------------------------------
# Process-lifecycle record + unclean/OOM classification (Issue #4603)
#
# ``RestartLoopGuard`` above tracks the *rate* of restart-worthy boots in
# memory, and ``classify_exit_reason`` maps a caught exception to an exit code.
# Neither survives a ``SIGKILL``/OOM-kill — no in-process hook runs for those —
# so a hosted gateway cannot tell on its next boot that its previous process
# died uncleanly. These three pure primitives close that gap: a small durable
# lifecycle *record* the runtime restamps on boot/shutdown, a pure predicate
# that classifies "was the last exit clean?", and a restart-loop guard whose
# events load from / flush to an injected durable store so the breaker survives
# the very death it guards. All I/O — the ``/proc``/cgroup sampling and the
# durable sentinel — lives in the ``praisonai-bot`` runtime; core stays
# protocol + pure default policy, symmetric with the block above.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleRecord:
    """Durable, boot-scoped snapshot of the gateway process's lifecycle.

    Written by the runtime at boot (``phase="running"``) and on a graceful stop
    (``phase="exited"``), with a memory sample folded in by the heartbeat. On
    the *next* boot the runtime reads the prior record and runs
    :func:`classify_unclean_exit`: a record still marked ``running`` means the
    previous process never reached its graceful-stop path — an unclean exit,
    and (given a high last memory sample) a suspected OOM-kill.

    Pure and JSON-round-trippable so both the durable store and the health
    surface share one shape; the wrapper owns persistence.

    Attributes:
        phase: ``"running"`` | ``"draining"`` | ``"exited"`` — the last phase
            the process recorded for itself.
        exit_kind: ``"clean"`` | ``"unclean"`` | ``"unknown"`` — set by
            :func:`classify_unclean_exit` on the *next* boot (never
            ``"unknown"``-treated-as-healthy downstream).
        suspected_oom: ``True`` when an unclean exit coincided with a high last
            memory sample (memory pressure at death).
        last_mem_fraction: Last sampled memory-budget fraction in ``[0, 1]``, or
            ``None`` when the platform could not report it.
        restart_events: Persisted monotonic-independent wall-clock timestamps of
            restart-worthy boots, for :class:`PersistentRestartLoopGuard`.
    """

    phase: Literal["running", "draining", "exited"] = "running"
    exit_kind: Literal["clean", "unclean", "unknown"] = "unknown"
    suspected_oom: bool = False
    last_mem_fraction: Optional[float] = None
    restart_events: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict for the durable sentinel."""
        return {
            "phase": self.phase,
            "exit_kind": self.exit_kind,
            "suspected_oom": self.suspected_oom,
            "last_mem_fraction": self.last_mem_fraction,
            "restart_events": list(self.restart_events),
        }

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "LifecycleRecord":
        """Rebuild from a persisted dict, tolerating partial/legacy shapes."""
        if not isinstance(data, Mapping):
            return cls()

        phase = data.get("phase")
        if phase not in ("running", "draining", "exited"):
            phase = "running"
        exit_kind = data.get("exit_kind")
        if exit_kind not in ("clean", "unclean", "unknown"):
            exit_kind = "unknown"

        frac = data.get("last_mem_fraction")
        try:
            frac_val: Optional[float] = None if frac is None else float(frac)
        except (TypeError, ValueError):
            frac_val = None

        raw_events = data.get("restart_events") or []
        events: List[float] = []
        if isinstance(raw_events, (list, tuple)):
            for item in raw_events:
                try:
                    events.append(float(item))
                except (TypeError, ValueError):
                    continue

        return cls(
            phase=phase,  # type: ignore[arg-type]
            exit_kind=exit_kind,  # type: ignore[arg-type]
            suspected_oom=bool(data.get("suspected_oom", False)),
            last_mem_fraction=frac_val,
            restart_events=events,
        )


def classify_unclean_exit(
    prev: Optional[LifecycleRecord],
    *,
    oom_fraction: float = 0.9,
) -> LifecycleRecord:
    """Classify the previous boot's exit and return a fresh boot record (pure).

    Given the record persisted by the *previous* process, decide whether that
    process exited cleanly and stamp a new ``phase="running"`` record for *this*
    boot. Side-effect free so it is provable in isolation, mirroring
    :func:`classify_exit_reason`.

    Rules:

    * No prior record ⇒ first boot / fresh store: ``exit_kind="unknown"`` (the
      caller must never treat ``"unknown"`` as healthy, but there is nothing to
      resume).
    * Prior ``phase == "exited"`` ⇒ the previous process reached its graceful
      stop: ``exit_kind="clean"``.
    * Prior ``phase in ("running", "draining")`` ⇒ the previous process died
      before recording a clean exit (SIGKILL/OOM/segfault/orchestrator kill):
      ``exit_kind="unclean"``, and ``suspected_oom`` when its last memory sample
      was at/above ``oom_fraction`` of the budget.

    The returned record carries forward the prior ``restart_events`` so the
    persistent restart-loop guard sees the full cross-boot history.

    Args:
        prev: The previous process's persisted :class:`LifecycleRecord`, or
            ``None`` on a fresh store.
        oom_fraction: Memory-budget fraction at/above which an unclean exit is
            flagged as a suspected OOM-kill.

    Returns:
        A fresh ``phase="running"`` :class:`LifecycleRecord` for this boot.
    """
    carried = list(prev.restart_events) if prev is not None else []
    if prev is None:
        return LifecycleRecord(
            phase="running", exit_kind="unknown", restart_events=carried
        )
    if prev.phase == "exited":
        return LifecycleRecord(
            phase="running", exit_kind="clean", restart_events=carried
        )
    # Still "running"/"draining" in the prior record ⇒ never reached graceful stop.
    frac = prev.last_mem_fraction
    suspected_oom = frac is not None and frac >= oom_fraction
    return LifecycleRecord(
        phase="running",
        exit_kind="unclean",
        suspected_oom=suspected_oom,
        last_mem_fraction=frac,
        restart_events=carried,
    )


@runtime_checkable
class RestartStoreProtocol(Protocol):
    """Durable-store contract for cross-boot restart timestamps (Issue #4603).

    The pure decision (:class:`PersistentRestartLoopGuard`) lives in core; the
    wrapper injects a concrete store that reads/writes the timestamps to a small
    sentinel file. Both methods are best-effort: an implementation that cannot
    reach its backing store returns ``[]`` from :meth:`load_events` and silently
    drops :meth:`save_events`, so the breaker degrades to in-memory behaviour
    rather than crashing the gateway it protects.
    """

    def load_events(self) -> List[float]:
        """Return the persisted restart timestamps (``[]`` when unavailable)."""
        ...

    def save_events(self, events: List[float]) -> None:
        """Persist the restart timestamps (best-effort, never raises)."""
        ...


class PersistentRestartLoopGuard(RestartLoopGuard):
    """A :class:`RestartLoopGuard` whose events survive a process restart.

    The in-memory guard is reconstructed fresh on every boot, so a persisted
    turn that hard-crashes the *whole* process (OOM, segfault) can drive an
    infinite ``supervisor → boot → auto-resume → crash`` loop the breaker never
    sees. This subclass loads its event history from an injected
    :class:`RestartStoreProtocol` at construction and flushes back on every
    mutation, so the breaker observes the true cross-boot restart rate and can
    trip on a crash cycle *slower* than a single in-process window.

    The window defaults to one hour (vs. the in-process 60s) because a
    cross-boot crash loop is paced by process (re)start latency, not by an
    in-loop retry. Pure decision preserved: all persistence is delegated to the
    injected store, so the trip logic remains provable in isolation.

    Example::

        guard = PersistentRestartLoopGuard(store, max_restarts=3,
                                           window_seconds=3600)
        if guard.record(now=time.time()):
            # too many restart-interrupted boots — stop auto-resuming the turn
            ...
    """

    def __init__(
        self,
        store: RestartStoreProtocol,
        *,
        max_restarts: int = 3,
        window_seconds: float = 3600.0,
    ):
        super().__init__(max_restarts=max_restarts, window_seconds=window_seconds)
        self._store = store
        try:
            loaded = store.load_events()
        except Exception:
            loaded = []
        if loaded:
            self._events = [float(t) for t in loaded]

    def _flush(self) -> None:
        try:
            self._store.save_events(list(self._events))
        except Exception:
            pass

    def record(self, now: float) -> bool:
        """Record a restart at wall-clock ``now`` and flush to the store.

        Unlike the base class this expects a *wall-clock* timestamp
        (``time.time()``), because a monotonic clock resets across process
        boots and would make persisted events meaningless.
        """
        tripped = super().record(now)
        self._flush()
        return tripped

    def reset(self) -> None:
        """Clear the history in memory *and* in the durable store."""
        super().reset()
        self._flush()


def classify_resource_pressure(
    *,
    mem_fraction: Optional[float] = None,
    disk_free_mb: Optional[float] = None,
    mem_elevated: float = 0.75,
    mem_critical: float = 0.9,
    disk_min_free_mb: float = 512.0,
) -> Dict[str, str]:
    """Classify coarse memory + disk pressure for the health surface (pure).

    A tiny, redaction-safe classifier that folds the wrapper's ``/proc``/cgroup
    memory-budget fraction and free-disk sample into a closed ``ok`` /
    ``elevated`` / ``critical`` / ``unknown`` vocabulary. Lives in core so the
    SDK and the bot classify identically; the wrapper owns the sampling.

    ``unknown`` is returned when a signal is missing and — per the issue — must
    never be treated as healthy by callers (it is deliberately *not* ``ok``).

    Args:
        mem_fraction: Anonymous-RSS / memory-budget fraction in ``[0, ∞)``, or
            ``None`` when the platform has no cgroup limit to report against.
        disk_free_mb: Free disk headroom in MiB for the gateway's state dir, or
            ``None`` when it could not be sampled.
        mem_elevated: Fraction at/above which memory is ``"elevated"``.
        mem_critical: Fraction at/above which memory is ``"critical"``.
        disk_min_free_mb: Free-MiB floor below which disk is ``"critical"``;
            ``"elevated"`` below twice that.

    Returns:
        ``{"memory": <level>, "disk": <level>}`` with values drawn from the
        closed vocabulary above.
    """

    def _mem(frac: Optional[float]) -> str:
        if frac is None:
            return "unknown"
        try:
            f = float(frac)
        except (TypeError, ValueError):
            return "unknown"
        if f >= mem_critical:
            return "critical"
        if f >= mem_elevated:
            return "elevated"
        return "ok"

    def _disk(free_mb: Optional[float]) -> str:
        if free_mb is None:
            return "unknown"
        try:
            mb = float(free_mb)
        except (TypeError, ValueError):
            return "unknown"
        if mb < disk_min_free_mb:
            return "critical"
        if mb < disk_min_free_mb * 2:
            return "elevated"
        return "ok"

    return {"memory": _mem(mem_fraction), "disk": _disk(disk_free_mb)}


class FleetSupervisionPolicy:
    """Pure fleet-level crash-loop breaker for channel supervision (Issue #3840).

    Per-channel restart budgets (``ChannelHealthMonitor`` /
    ``ChannelRestartHistory`` in ``praisonai-bot``) throttle one misbehaving
    channel, but they are blind to a *systemic* fault — a bad shared provider,
    a network partition, an org-wide expired token — that makes *every* channel
    restart at once. Each channel then independently stays "under budget" while
    the fleet as a whole thrashes: a reconnect storm that floods logs, burns
    CPU, and risks an upstream rate-limit ban with no single operator-visible
    signal.

    This is the aggregate breaker that sits *on top of* the per-channel budgets.
    Like :class:`RestartLoopGuard` it is intentionally side-effect free (records
    timestamps only, no I/O, no heavy deps) so the *decision* lives in core and
    is provable in isolation; the wrapper owns the side effects (halting
    restarts, recording one ``gateway`` degraded-owner entry).

    The breaker trips when *either* aggregate signal crosses its threshold
    within the trailing window:

    * the fleet restart rate reaches ``fleet_restarts_per_hour`` restarts across
      all channels, or
    * the fraction of channels in a failing/parked state reaches
      ``failing_channel_fraction``.

    Once tripped it stays tripped for ``breaker_cooldown_s`` so the caller
    applies backpressure (stops auto-restarting, backs off) instead of feeding
    the storm; after the cooldown it re-arms automatically.

    Example::

        policy = FleetSupervisionPolicy(fleet_restarts_per_hour=40)
        if policy.note_restart(now=time.monotonic()):
            # fleet breaker tripped — stop auto-restarting, surface degraded
            ...
    """

    def __init__(
        self,
        fleet_restarts_per_hour: int = 40,
        failing_channel_fraction: float = 0.5,
        breaker_cooldown_s: float = 120.0,
    ):
        if fleet_restarts_per_hour < 1:
            raise ValueError(
                f"fleet_restarts_per_hour must be >= 1, got {fleet_restarts_per_hour!r}"
            )
        if not 0.0 < failing_channel_fraction <= 1.0:
            raise ValueError(
                "failing_channel_fraction must be in (0.0, 1.0], got "
                f"{failing_channel_fraction!r}"
            )
        if breaker_cooldown_s < 0:
            raise ValueError(
                f"breaker_cooldown_s must be >= 0, got {breaker_cooldown_s!r}"
            )
        self.fleet_restarts_per_hour = int(fleet_restarts_per_hour)
        self.failing_channel_fraction = float(failing_channel_fraction)
        self.breaker_cooldown_s = float(breaker_cooldown_s)
        self._window_seconds = 3600.0  # restart-rate window is per-hour
        self._events: "List[float]" = []
        self._tripped_until: Optional[float] = None

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        self._events = [t for t in self._events if t >= cutoff]

    def note_restart(self, now: float) -> bool:
        """Record a fleet restart at ``now`` and return whether the breaker is tripped.

        Args:
            now: A monotonic timestamp for this restart event.

        Returns:
            ``True`` when the aggregate restart rate has reached
            ``fleet_restarts_per_hour`` within the trailing hour (or the breaker
            is still within its cooldown); ``False`` otherwise.
        """
        # While actively cooling down, do NOT record new events: the caller has
        # already HELD the restart, so counting held (non-)restarts would keep
        # renewing the window and leave the breaker stuck until the full hour
        # expires. Just report that we are still tripped.
        if self.tripped(now):
            return True
        self._prune(now)
        self._events.append(now)
        if len(self._events) >= self.fleet_restarts_per_hour:
            self._tripped_until = now + self.breaker_cooldown_s
            return True
        return False

    def note_fleet_state(
        self, failing_channels: int, total_channels: int, now: float
    ) -> bool:
        """Trip the breaker when too large a fraction of the fleet is failing.

        A systemic fault often shows up as many channels simultaneously in a
        failing/parked state rather than as a raw restart rate. When at least
        ``failing_channel_fraction`` of the fleet is failing, trip and start the
        cooldown.

        Args:
            failing_channels: Number of channels currently failing/parked.
            total_channels: Total number of supervised channels.
            now: A monotonic timestamp for this evaluation.

        Returns:
            ``True`` when the breaker is tripped (now or still cooling down).
        """
        if total_channels > 0:
            fraction = failing_channels / total_channels
            if fraction >= self.failing_channel_fraction:
                self._tripped_until = now + self.breaker_cooldown_s
                return True
        return self.tripped(now)

    def tripped(self, now: float) -> bool:
        """Return whether the breaker is currently tripped without recording.

        When the cooldown has elapsed the breaker re-arms cleanly: the accrued
        event window is cleared so the accumulated pre-trip restarts cannot
        immediately re-trip on the very next ``note_restart``.
        """
        if self._tripped_until is not None:
            if now < self._tripped_until:
                return True
            self._tripped_until = None
            self._events = []
        return False

    def reset(self) -> None:
        """Clear recorded restart history and any active trip (clean recovery)."""
        self._events = []
        self._tripped_until = None


# ---------------------------------------------------------------------------
# Protocol Version Negotiation (Issue #2130)
# ---------------------------------------------------------------------------

# Protocol version constants
PROTOCOL_VERSION = 1
MIN_PROTOCOL_VERSION = 1
MAX_PROTOCOL_VERSION = 1


class ProtocolHello(TypedDict, total=False):
    """Protocol version negotiation handshake request.
    
    Sent by client during join to negotiate protocol version.
    """
    min_version: int  # Minimum protocol version client supports
    max_version: int  # Maximum protocol version client supports
    features: List[str]  # Optional feature flags


class ProtocolHelloOk(TypedDict):
    """Protocol version negotiation response.
    
    Server's response to protocol negotiation.
    """
    protocol_version: int  # Negotiated protocol version
    server_min_version: int  # Server's minimum supported version
    server_max_version: int  # Server's maximum supported version
    features: List[str]  # Enabled feature flags


class GapInfo(TypedDict):
    """Information about a gap in the event sequence."""
    expected_seq: int  # Expected sequence number
    received_seq: int  # Received sequence number  
    missed_count: int  # Number of events missed


class ResumeSnapshot(TypedDict, total=False):
    """Complete snapshot for session resumption.
    
    Provides all necessary state for one-round-trip reconnection.
    """
    cursor: int  # Resume cursor position
    sequence: int  # Current sequence number for gap detection
    events: List[Dict[str, Any]]  # Replayed events since cursor
    presence: List[Dict[str, Any]]  # Current presence information
    health: Dict[str, Any]  # Gateway health status
    session_state: Dict[str, Any]  # Session-specific state


# ──────────────────────────────────────────────────────────────────────
# Relay transport (Issue #2485)
#
# A protocol-first seam so a thin *connector* process can own the platform
# socket (Telegram/Discord/WhatsApp/...) and relay normalised inbound events
# to a gateway over an authenticated transport, while accepting outbound
# sends/interrupts back down. This decouples the *platform connection* from
# the gateway process, enabling:
#   * headless / NAT-friendly hosting (gateway needs no public inbound port),
#   * one gateway fronting many remotely-hosted connectors,
#   * lossless scale-to-zero (the connector stays connected and buffers while
#     the gateway is dormant, draining the backlog on wake).
#
# These are *protocols only* — no transport (WebSocket/gRPC/message bus) and
# no platform SDK is imported here. Concrete implementations live in the
# praisonai wrapper.
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityDescriptor:
    """A capability profile a relay connector attests at handshake time.

    Where :class:`~praisonaiagents.bots.presentation.PlatformCapabilities`
    declares capabilities *statically* in core, this descriptor is negotiated
    by a remote connector at connect time so the streaming/delivery layer can
    adapt to the actual platform the connector is fronting.

    Attributes:
        max_message_length: Maximum outbound message length the platform
            accepts before the connector must split/truncate.
        length_unit: How ``max_message_length`` is measured — ``"chars"``
            (Unicode code points) or ``"utf16"`` (UTF-16 code units, as some
            platforms count).
        supports_edit: Whether the platform supports editing a sent message
            (enables draft-streaming via in-place edits).
        supports_draft_streaming: Whether the connector can stream partial
            drafts (incremental updates) for a single turn.
        markdown_dialect: Markdown flavour the platform renders
            (e.g. ``"none"``, ``"markdown"``, ``"markdownv2"``, ``"html"``).
    """

    max_message_length: int
    length_unit: str = "chars"  # "chars" | "utf16"
    supports_edit: bool = False
    supports_draft_streaming: bool = False
    markdown_dialect: str = "none"

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary (for the handshake wire)."""
        return {
            "max_message_length": self.max_message_length,
            "length_unit": self.length_unit,
            "supports_edit": self.supports_edit,
            "supports_draft_streaming": self.supports_draft_streaming,
            "markdown_dialect": self.markdown_dialect,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityDescriptor":
        """Reconstruct a descriptor from its serialized form."""
        return cls(
            max_message_length=int(data["max_message_length"]),
            length_unit=str(data.get("length_unit", "chars")),
            supports_edit=bool(data.get("supports_edit", False)),
            supports_draft_streaming=bool(
                data.get("supports_draft_streaming", False)
            ),
            markdown_dialect=str(data.get("markdown_dialect", "none")),
        )


@runtime_checkable
class RelayTransport(Protocol):
    """Protocol for an out-of-process platform-connector relay.

    A concrete implementation (e.g. a ``WebSocketRelayTransport`` in the
    praisonai wrapper) lets a connector that holds the platform socket
    forward normalised inbound :class:`GatewayMessage` events to the gateway
    and accept outbound sends/interrupts back down. The gateway treats the
    relay like any other adapter (same inbound routing, admission control,
    delivery) but the connection lives elsewhere.

    Lifecycle::

        caps = await transport.connect()            # handshake → capabilities
        transport.set_inbound_handler(on_message)   # wire inbound events in
        ...                                          # events relayed in/out
        await transport.go_dormant()                 # pause, keep connection
        await transport.disconnect()                 # tear down
    """

    async def connect(self) -> "CapabilityDescriptor":
        """Establish the relay and complete the handshake.

        Returns the :class:`CapabilityDescriptor` attested by the connector
        for the platform it is fronting.
        """
        ...

    def set_inbound_handler(
        self, handler: Callable[["GatewayMessage"], Awaitable[None]]
    ) -> None:
        """Register the coroutine invoked for each relayed inbound message."""
        ...

    async def send_outbound(
        self, target: "TargetInfo", message: "GatewayMessage"
    ) -> "DeliveryResult":
        """Relay an outbound message to ``target`` via the connector."""
        ...

    async def go_dormant(self) -> None:
        """Pause inbound dispatch without dropping the connection.

        The connector keeps the platform socket open and buffers inbound
        events while the gateway is dormant (scale-to-zero), so they can be
        drained losslessly on wake.
        """
        ...

    async def disconnect(self) -> None:
        """Tear down the relay connection."""
        ...


# ---------------------------------------------------------------------------
# Gateway pipeline span-tracing seam (Issue #2716)
#
# Running a bot fleet on the gateway means debugging latency/failures across an
# async pipeline: inbound -> admission/queue -> agent turn -> each tool/LLM
# call -> outbox -> delivery. Today an operator can correlate *logs* by a
# single correlation id and read *counters* from ``/metrics``, but cannot see a
# per-turn span breakdown or error spans in a distributed tracer
# (Jaeger/Tempo/Datadog/Honeycomb).
#
# This is the missing *stage seam*: a dependency-free hook the wrapper gateway
# can fire around each pipeline stage. Core holds only the protocol and a
# zero-cost no-op default (``NullGatewayTraceHook``) so there is no OTel import
# and no hot-path overhead when tracing is disabled. A ``praisonai-plugins``
# OTel exporter implements the protocol and opens/closes real spans over OTLP,
# reusing the existing correlation id as a span attribute — keeping the heavy
# ``opentelemetry-sdk`` dependency out of core and the wrapper.
#
# The seam is intentionally a synchronous context-manager factory so it wraps
# both sync and async stages uniformly (``with self._trace.stage(...):``) and
# is trivially provable in isolation.
# ---------------------------------------------------------------------------

# Canonical gateway pipeline stage names, so a tracer plugin and the wrapper
# agree on span names without a hard import between them.
GATEWAY_TRACE_STAGES = (
    "inbound",
    "admit",
    "agent.run",
    "llm.call",
    "tool.call",
    "outbox.enqueue",
    "delivery",
)


@runtime_checkable
class GatewayTraceHook(Protocol):
    """Structural contract for tracing a gateway pipeline stage as a span.

    A hook is fired around each stage of the inbound -> agent -> tool ->
    delivery pipeline. Implementations return a context manager whose scope is
    the span: entering starts it, exiting ends it, and an exception propagating
    out marks the span as failed. The default core implementation
    (:class:`NullGatewayTraceHook`) is a no-op so tracing is zero-cost when no
    exporter is attached.

    The contract is deliberately dependency-free: no OpenTelemetry import lives
    in core. A ``praisonai-plugins`` exporter implements ``stage`` with
    ``tracer.start_as_current_span(...)`` and carries the correlation id as a
    span attribute. Example::

        with self._trace.stage(
            "agent.run",
            correlation_id=current_correlation_id(),
            session=sid,
        ):
            reply = await agent.astart(text)

    W3C trace-context propagation is layered on top of the same seam without
    forcing OpenTelemetry into core. ``stage`` accepts an optional
    ``parent_carrier`` (a header mapping such as an inbound request's
    ``{"traceparent": ..., "tracestate": ...}``) so an exporter can *continue*
    an upstream caller's trace instead of starting a detached one; and the two
    companion methods let egress call sites propagate the active span context:

        # ingress: continue the caller's trace when a traceparent arrives
        with self._trace.stage("agent.run", parent_carrier=inbound.headers):
            ...

        # egress: write the active traceparent onto an outbound request.
        # Seed with provider headers first, then inject last so the active
        # trace context always wins over any stale traceparent/tracestate.
        headers = dict(provider_headers)
        self._trace.inject_context(headers)  # no-op unless an exporter is set

    Both companion methods are no-ops in :class:`NullGatewayTraceHook`, so the
    default path stays zero-cost and OpenTelemetry-free.
    """

    def stage(
        self,
        name: str,
        *,
        correlation_id: "Optional[str]" = None,
        parent_carrier: "Optional[Mapping[str, str]]" = None,
        **attrs: Any,
    ) -> "AbstractContextManager[Any]":
        """Open a tracing scope for pipeline stage ``name``.

        Args:
            name: The stage name (see :data:`GATEWAY_TRACE_STAGES`), used as the
                span name.
            correlation_id: The inbound turn's correlation id, attached as a
                span attribute so spans and logs share a key.
            parent_carrier: Optional inbound header mapping carrying W3C
                trace-context (``traceparent``/``tracestate``). When present and
                an exporter is attached, the stage is entered *under* the
                extracted parent context so the span nests within the caller's
                distributed trace instead of starting a new root.
            **attrs: Extra span attributes (e.g. ``session``, ``model``,
                ``tool``, ``channel``).

        Returns:
            A context manager delimiting the span's lifetime.
        """
        ...

    def inject_context(self, carrier: "MutableMapping[str, str]") -> None:
        """Write the active span context into ``carrier`` as W3C headers.

        Called at an egress boundary (LLM / MCP / HTTP-tool request) so the
        downstream service's spans nest under the current agent turn. A no-op
        when no exporter is attached, leaving ``carrier`` untouched.
        """
        ...

    def extract_carrier(
        self, carrier: "Mapping[str, str]"
    ) -> "Optional[Mapping[str, str]]":
        """Return a propagation carrier extracted from inbound ``carrier``.

        Reads W3C trace-context (``traceparent``/``tracestate``) from an
        inbound header mapping and returns a normalized carrier suitable to pass
        as ``stage(..., parent_carrier=...)``, or ``None`` when no usable
        context is present. A no-op returning ``None`` when no exporter is
        attached.
        """
        ...


class NullGatewayTraceHook:
    """Zero-cost no-op :class:`GatewayTraceHook` used when tracing is disabled.

    Every stage call returns a lightweight, argument-ignoring null context
    manager (one small allocation per call), so firing the seam adds negligible
    overhead on the hot path. This is the default a gateway uses until an
    exporter plugin (e.g. the OTel/OTLP plugin in ``praisonai-plugins``) is
    supplied.
    """

    @staticmethod
    @contextmanager
    def _null_scope() -> "Iterator[None]":
        yield None

    def stage(
        self,
        name: str,
        *,
        correlation_id: "Optional[str]" = None,
        parent_carrier: "Optional[Mapping[str, str]]" = None,
        **attrs: Any,
    ) -> "AbstractContextManager[Any]":
        """Return a no-op context manager, ignoring all arguments."""
        return self._null_scope()

    def inject_context(self, carrier: "MutableMapping[str, str]") -> None:
        """No-op: leave ``carrier`` untouched when tracing is disabled."""
        return None

    def extract_carrier(
        self, carrier: "Mapping[str, str]"
    ) -> "Optional[Mapping[str, str]]":
        """No-op: no parent context to continue when tracing is disabled."""
        return None


# Shared singleton: the default no-op hook is stateless, so one instance is
# reused everywhere a gateway needs a zero-cost default.
NULL_GATEWAY_TRACE_HOOK = NullGatewayTraceHook()


def resolve_trace_hook(
    hook: "Optional[GatewayTraceHook]",
) -> "GatewayTraceHook":
    """Return ``hook`` when a tracer is supplied, else the no-op default.

    A tiny helper so a gateway can accept an optional ``tracer=`` argument and
    always hold a callable hook without branching on ``None`` at every stage.

    Args:
        hook: A user/plugin-supplied trace hook, or ``None``.

    Returns:
        ``hook`` if not ``None``, otherwise the shared
        :data:`NULL_GATEWAY_TRACE_HOOK`.
    """
    return hook if hook is not None else NULL_GATEWAY_TRACE_HOOK


# ---------------------------------------------------------------------------
# Gateway self-lifecycle command guardrail (Issue #2753)
#
# A running gateway is a long-lived process that hosts an agent which can act on
# the same host — it can call a shell tool or author a scheduled job. Nothing
# inspects the *content* of an agent-issued command to stop it from targeting
# the gateway's own lifecycle: ``praisonai gateway stop``, ``pkill -f
# 'praisonai gateway'``, or ``systemctl --user stop`` the gateway unit would
# take the process itself down (self-DoS), and under an external supervisor can
# become a respawn flap. Approval gating does not help — it decides *whether*
# an agent may run a tool, not *whether a specific command is self-destructive*.
#
# This is the pure, import-free decision seam for a default-deny lifecycle
# guardrail, symmetric with the other gateway policy protocols above
# (``SendPolicy``, ``ScaleToZeroPolicy``, ``DrainMarkerPolicy``, …). The wrapper
# consults it *before* a shell/CLI tool executes and *before* a scheduled job
# is registered; a denied command returns a clean, model-readable reason rather
# than running. Matching is command-anchored (structural token inspection, not
# prose) so ordinary English mentioning "stop the gateway" is never tripped,
# and it scans the command string (and any resolved script text). It is
# on-by-default and opt-outable via ``enabled=False``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleCommandDecision:
    """Closed decision shape for a self-lifecycle command evaluation.

    Attributes:
        allow: Whether the command may run (``True``) or is refused
            (``False``) because it targets this gateway's own lifecycle.
        reason: Model-readable explanation, populated on denial so the caller
            can surface *why* the command was blocked.
        matched: The specific command fragment that triggered the deny (for
            logging / the blocked-attempt audit line); empty when allowed.
    """

    allow: bool
    reason: str = ""
    matched: str = ""


@runtime_checkable
class LifecycleCommandPolicyProtocol(Protocol):
    """Protocol for guarding an agent from stopping its own gateway.

    Pure, import-free decision contract consulted by the wrapper *before* a
    shell/CLI tool executes and *before* a scheduled job is registered. The
    wrapper supplies the resolved command string (and, when a script file is
    involved, its text); the policy returns a :class:`LifecycleCommandDecision`
    that either allows the command or refuses it because its effect is to
    stop / restart / reload / kill *this* gateway process. Concrete pattern
    sets are swappable (a plugin may supply a richer one); this contract keeps
    the *decision* testable in isolation, symmetric with
    :class:`SendPolicyProtocol` / :class:`GatewayConcurrencyPolicyProtocol`.

    A config-driven default (:class:`LifecycleCommandGuardPolicy`) is provided
    for the common ``praisonai gateway stop`` / ``pkill … gateway`` /
    ``systemctl stop <unit>`` case.
    """

    def evaluate(
        self,
        command: str,
        *,
        agent_id: str = "",
    ) -> LifecycleCommandDecision:
        """Return a :class:`LifecycleCommandDecision` for ``command``."""
        ...


class LifecycleCommandGuardPolicy:
    """Config-driven, command-anchored guard against gateway self-lifecycle hits.

    The default referenced by ``gateway.lifecycle_guard`` blocks in
    ``gateway.yaml`` and the ``BotOS(..., lifecycle_policy=...)`` Python
    surface. It is intentionally minimal and dependency-free so the decision
    lives in core and is provable in isolation; the wrapper owns the consult
    points (shell-tool executor, scheduler job registration) and the audit log.

    Matching is *structural*, not prose-based, to avoid false positives on
    ordinary English (e.g. "please stop the gateway from spamming"):

    * ``praisonai gateway stop|restart|reload`` — the CLI self-control verbs,
      matched only when ``praisonai`` and ``gateway`` appear as adjacent
      command tokens followed by a lifecycle verb.
    * ``pkill`` / ``kill`` / ``killall`` naming the gateway (a configured
      ``process_names`` token — ``praisonai`` by default — appearing as a whole
      component in the argument list or a ``-f`` pattern).
    * ``systemctl`` / ``launchctl`` / ``sc`` ``stop`` / ``restart`` / ``kill``
      on a unit whose name mentions the gateway (same whole-component match).

    Matching is *whole-component*, not bare substring: unrelated services whose
    name merely contains a token (``api-gateway``, ``kong-gateway``) are not
    tripped, while the real ``praisonai-gateway`` unit still matches.

    The scan is applied to every ``;``/``&&``/``||``/pipe-separated segment of
    the command *and* to any additional script text supplied, so a command that
    shells out to a wrapper script cannot smuggle the intent past the guard.

    ``default_allow`` is a fail posture: on any internal parsing error the guard
    keeps today's behaviour (allow) unless ``default_allow=False`` is set for a
    strict, fail-closed deployment. ``enabled=False`` disables the guard
    entirely (an operator who legitimately wants an agent to manage the
    process).

    Example::

        LifecycleCommandGuardPolicy()                    # on by default
        LifecycleCommandGuardPolicy(enabled=False)       # opt out
        LifecycleCommandGuardPolicy(process_names=["praisonai", "mybot"])
    """

    _CLI_VERBS = frozenset({"stop", "restart", "reload", "kill", "down"})
    _SERVICE_MGRS = frozenset({"systemctl", "launchctl", "service", "sc"})
    _SERVICE_VERBS = frozenset(
        {"stop", "restart", "reload", "kill", "disable", "down"}
    )
    _KILL_CMDS = frozenset({"pkill", "kill", "killall"})
    _SEGMENT_SPLIT = ("&&", "||", "|", ";", "\n")

    def __init__(
        self,
        enabled: bool = True,
        process_names: Optional[List[str]] = None,
        default_allow: bool = True,
    ):
        self.enabled = bool(enabled)
        # Default to the project's own, *specific* identity token. Bare
        # ``"gateway"`` is deliberately NOT a default deny token — it is too
        # generic and would false-positive on unrelated services whose name
        # contains it (``api-gateway``, ``kong-gateway``). The CLI-form rule
        # (``praisonai gateway stop``) still catches the self-control verbs via
        # the adjacent ``gateway`` sub-command, which needs no per-name entry.
        names = process_names if process_names else ["praisonai"]
        # Lower-cased, de-duplicated identity tokens that name *this* gateway.
        self.process_names = [str(n).strip().lower() for n in names if str(n).strip()]
        self.default_allow = bool(default_allow)

    def _mentions_self(self, text: str) -> bool:
        """Whether ``text`` names this gateway process/unit.

        Uses *whole-component* matching, not bare substring containment, so an
        unrelated service whose name merely *contains* a configured token is
        not tripped. The text is split into identifier components on whitespace
        and the ``- _ . / : @``, ``'`` / ``"`` characters that delimit service
        units, paths and quoted ``-f`` patterns; a configured name matches only
        when it equals one of those components. Thus the default
        ``process_names=["praisonai"]`` matches ``praisonai-gateway`` (real
        unit) and ``pkill -f praisonai`` but NOT ``api-gateway`` /
        ``kong-gateway`` / ``my-praisonaibot``.
        """
        import re

        components = {c for c in re.split(r"[\s\-_./:@'\"]+", text) if c}
        return any(name in components for name in self.process_names)

    @staticmethod
    def _tokenize(segment: str) -> List[str]:
        """Best-effort shell tokenization; falls back to whitespace split."""
        import shlex

        try:
            return shlex.split(segment)
        except ValueError:
            return segment.split()

    def _segment_targets_self(self, segment: str) -> str:
        """Return the offending fragment if ``segment`` hits our lifecycle.

        Returns an empty string when the segment is benign.
        """
        lowered = segment.lower()
        tokens = [t.lower() for t in self._tokenize(segment)]
        if not tokens:
            return ""
        # Drop common leading privilege/env prefixes so the real command verb
        # (e.g. ``sudo praisonai gateway stop``) is inspected structurally.
        idx = 0
        while idx < len(tokens) and tokens[idx] in ("sudo", "env", "nohup", "exec"):
            idx += 1
        head = tokens[idx:]
        if not head:
            return ""

        cmd = head[0]
        # Normalise a path-qualified executable (``/usr/bin/pkill``) to its base.
        base = cmd.rsplit("/", 1)[-1]

        # 1) <cli> gateway <verb> — the CLI self-control form. Enforce the
        #    documented adjacency (``praisonai gateway stop``) rather than a
        #    loose "words appear somewhere" match, and honour ``process_names``
        #    so a renamed/forked CLI (``mybot gateway stop`` with
        #    ``process_names=["mybot"]``) is covered symmetrically with rules 2/3.
        cli_names = set(self.process_names) | {"praisonai"}
        for gi, token in enumerate(head):
            if token != "gateway":
                continue
            prev_is_cli = gi >= 1 and head[gi - 1] in cli_names
            next_is_verb = gi + 1 < len(head) and head[gi + 1] in self._CLI_VERBS
            if prev_is_cli and next_is_verb:
                return segment.strip()

        # 2) kill / pkill / killall naming the gateway
        if base in self._KILL_CMDS:
            args = head[1:]
            # -f/-fl pattern match, or an explicit process-name argument.
            if self._mentions_self(" ".join(args)):
                return segment.strip()

        # 3) service manager stop/restart on our unit
        if base in self._SERVICE_MGRS:
            args = head[1:]
            if any(v in self._SERVICE_VERBS for v in args) and self._mentions_self(
                lowered
            ):
                return segment.strip()

        return ""

    def evaluate(
        self,
        command: str,
        *,
        agent_id: str = "",
    ) -> LifecycleCommandDecision:
        """Return a :class:`LifecycleCommandDecision` for ``command``.

        Args:
            command: The resolved command / scheduled-job command string (may
                also carry appended script text — every segment is scanned).
            agent_id: Optional agent identity (accepted for parity with the
                other policy protocols; unused by the default guard).

        Returns:
            An *allow* decision when the command is benign, or a *deny*
            decision naming the offending fragment when it would stop / restart
            / kill this gateway.
        """
        if not self.enabled:
            return LifecycleCommandDecision(allow=True)
        if not isinstance(command, str) or not command.strip():
            return LifecycleCommandDecision(allow=True)

        try:
            segments: List[str] = [command]
            for sep in self._SEGMENT_SPLIT:
                expanded: List[str] = []
                for seg in segments:
                    expanded.extend(seg.split(sep))
                segments = expanded

            for seg in segments:
                offending = self._segment_targets_self(seg)
                if offending:
                    return LifecycleCommandDecision(
                        allow=False,
                        reason=(
                            "Refusing: command would stop/restart/kill this "
                            "gateway process (self-lifecycle guard)"
                        ),
                        matched=offending,
                    )
        except Exception:
            # Parsing must never crash the caller: honour the configured fail
            # posture (fail-open by default, fail-closed when default_allow is
            # False for a strict, hosted gateway).
            if not self.default_allow:
                return LifecycleCommandDecision(
                    allow=False,
                    reason=(
                        "Refusing: could not prove command is safe for this "
                        "gateway (self-lifecycle guard, fail-closed)"
                    ),
                    matched=command.strip(),
                )
            return LifecycleCommandDecision(allow=True)

        return LifecycleCommandDecision(allow=True)


# Backward-compatible alias following the repo's ``*Protocol`` convention.
LifecycleCommandPolicy = LifecycleCommandPolicyProtocol


# ---------------------------------------------------------------------------
# Application-level connection liveness (Issue #2798)
#
# The gateway advertises a ``heartbeat_ms`` policy and stamps every session's
# ``last_activity``, but nothing enforces it: there is no protocol-level
# ping/pong frame and no server-side sweep, so a *half-open* connection (peer
# vanished, no FIN/RST — routine behind NAT/proxies/load-balancers/mobile) can
# linger forever, keeping presence "online" and silently queuing/dropping
# messages routed to it.
#
# This closes the loop with one transport-agnostic contract: a ``PING``/``PONG``
# event pair (see :class:`EventType`) plus a pure, import-free
# :class:`LivenessPolicy` — symmetric with the other gateway policy protocols
# above (``SendPolicy``, ``DrainTimeoutPolicy``, ``ConcurrencyLimitPolicy``, …).
# The policy owns only the *decision* (``KEEP`` vs ``REAP``) over a stamped
# ``last_activity`` and a ``now`` timestamp; the wrapper server owns the
# heartbeat-emit + reaper task and the reference client owns the heartbeat-send
# + silence watchdog, each consuming this decision. A ``REAP`` maps onto
# :attr:`GatewayCloseCode.LIVENESS_TIMEOUT`.
# ---------------------------------------------------------------------------


class LivenessDecision(str, Enum):
    """Outcome of a connection-liveness evaluation.

    * ``KEEP`` — the connection has shown activity recently enough; leave it.
    * ``REAP`` — the connection missed too many heartbeats and is presumed
      dead/half-open; the server should close it with
      :attr:`GatewayCloseCode.LIVENESS_TIMEOUT` and release its
      session/presence/queue state.
    """

    KEEP = "keep"
    REAP = "reap"


@runtime_checkable
class LivenessPolicyProtocol(Protocol):
    """Protocol for application-level connection-liveness decisions.

    Pure, import-free decision contract consumed by the wrapper's gateway
    (heartbeat-emit + reaper task) and the reference client (heartbeat-send +
    silence watchdog). The caller supplies the connection's last-activity
    timestamp and the current time; the policy returns a
    :class:`LivenessDecision`. Concrete transport machinery (sending the
    ``PING`` frame, closing the socket, forcing a reconnect) lives in the
    implementations, since it needs the running event loop and live sockets;
    this contract keeps the *decision* testable in isolation, symmetric with
    :class:`GatewayDrainPolicyProtocol` / :class:`RateLimitPolicyProtocol`.

    A config-driven default (:class:`LivenessPolicy`) is provided for the
    common "heartbeat every ``interval_ms``, reap after N missed beats" case.
    """

    interval_ms: int
    missed_beats_before_reap: int

    def evaluate(self, last_activity: float, now: float) -> LivenessDecision:
        """Return a :class:`LivenessDecision` for the supplied timestamps."""
        ...


@dataclass(frozen=True)
class LivenessPolicy:
    """Config-driven, pure liveness policy for half-open connection reaping.

    The default referenced by ``gateway.liveness`` blocks in ``gateway.yaml``
    and the ``WebSocketGateway(..., liveness_policy=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in core and
    is provable in isolation; the wrapper owns the side effects (emit the
    ``PING`` heartbeat, close the socket, force the client reconnect).

    A connection is reaped once its ``last_activity`` is older than
    ``interval_ms × missed_beats_before_reap`` — i.e. it has silently missed
    that many heartbeat intervals. Any activity (an inbound frame, an inbound
    ``PONG``, or the peer's own ``PING``) refreshes ``last_activity`` and keeps
    the connection alive. The reference client typically force-reconnects after
    ``~2×`` the interval of silence, so it heals before the server reaps it.

    The window derivation is shared with the client watchdog via
    :meth:`reap_deadline` / :attr:`interval_seconds` so both sides agree on the
    same arithmetic from one advertised ``interval_ms``.

    ``interval_ms`` of ``0`` disables liveness reaping entirely (today's
    behaviour: ``last_activity`` is stamped but never acted upon), so the
    feature is fully backward-compatible and opt-in.

    Example::

        LivenessPolicy(interval_ms=30_000, missed_beats_before_reap=2)
    """

    interval_ms: int = 30_000
    missed_beats_before_reap: int = 2

    def __post_init__(self) -> None:
        if self.interval_ms < 0:
            raise ValueError(
                f"interval_ms must be >= 0 (use 0 to disable liveness reaping), "
                f"got {self.interval_ms!r}"
            )
        if self.missed_beats_before_reap < 1:
            raise ValueError(
                f"missed_beats_before_reap must be >= 1, "
                f"got {self.missed_beats_before_reap!r}"
            )

    @property
    def enabled(self) -> bool:
        """Whether liveness reaping is active (a positive interval is set)."""
        return self.interval_ms > 0

    @property
    def interval_seconds(self) -> float:
        """The heartbeat interval expressed in seconds."""
        return self.interval_ms / 1000.0

    def reap_deadline(self, last_activity: float) -> float:
        """Return the absolute time after which the connection is stale.

        A connection is reaped when the evaluation-time ``now`` is strictly
        above this deadline (``now > reap_deadline(last_activity)``). Exposed
        so the server reaper and the client watchdog derive the same window
        from one advertised interval.
        """
        return last_activity + self.interval_seconds * self.missed_beats_before_reap

    def evaluate(self, last_activity: float, now: float) -> LivenessDecision:
        """Return :attr:`LivenessDecision.REAP` iff the connection is stale.

        Args:
            last_activity: The connection's last-activity timestamp (same clock
                as ``now`` — the wrapper uses a monotonic clock).
            now: The current timestamp.

        Returns:
            :attr:`LivenessDecision.KEEP` while reaping is disabled or the
            connection is within its liveness window; otherwise
            :attr:`LivenessDecision.REAP`.
        """
        if not self.enabled:
            return LivenessDecision.KEEP
        if now > self.reap_deadline(last_activity):
            return LivenessDecision.REAP
        return LivenessDecision.KEEP


# ---------------------------------------------------------------------------
# Cluster-wide per-turn serialisation contract (Issue #3643)
# ---------------------------------------------------------------------------
#
# Turn serialisation — "only one turn runs against a given resolved session at
# a time" — is enforced in-process by an ``asyncio.Lock`` (``LockMap``). That
# guarantee evaporates the moment a gateway is scaled to ``replicas > 1`` (the
# sanctioned HA topology behind ``redis_pubsub.py`` + the Helm chart): two
# messages for one session land on two replicas and run concurrent turns with
# no serialisation between them, corrupting the shared transcript, tripping
# provider strict-alternation, duplicating replies and double-billing.
#
# This is the pure, dependency-free contract for a *distributed* turn lock,
# mirroring how every other gateway robustness knob (drain, admission,
# rate-limit, liveness, dead-letter) is a swappable pure protocol in core. The
# heavy Redis/network implementation is an optional-dep runtime concern that
# lives in the wrapper/bot package; core keeps only the protocol, the lease
# token, and a zero-cost in-process default so single-replica behaviour is
# unchanged and no new dependency is introduced.


@dataclass(frozen=True)
class TurnLeaseToken:
    """An opaque handle to a held turn lease (Issue #3643).

    Returned by :meth:`TurnLockProtocol.acquire` and passed back to
    :meth:`TurnLockProtocol.release`. The ``owner`` token identifies the
    replica/process that holds the lease so a distributed backend can make
    ``release`` **identity-checked and idempotent** — a replica can only
    release the lease it actually owns, and a stale/expired lease that has
    since been reclaimed by another owner is never clobbered.

    Attributes:
        key: The resolved session id the lease serialises on.
        owner: The holder's opaque owner token (e.g. a per-replica id).
        expires_at: Absolute wall-clock expiry (same clock the backend uses).
            A dead holder's lease is reclaimable once ``now`` passes this, so a
            crashed replica cannot wedge a healthy session forever.
    """

    key: str
    owner: str
    expires_at: float


@runtime_checkable
class TurnLockProtocol(Protocol):
    """Contract for serialising a session's turns — cluster-wide or in-process.

    The gateway holds this lock for the *whole* agent turn keyed on the
    resolved session id, so only one turn ever runs against one session's
    transcript at a time. With the default in-process backend
    (:class:`LocalTurnLock`) this reproduces today's ``asyncio.Lock`` behaviour
    exactly and adds no dependency. With a distributed backend (a
    ``RedisTurnLock`` in the wrapper/bot package, reusing the scheduler's proven
    ``owner``+TTL lease pattern) the same ``async with`` seam serialises turns
    across every replica.

    Contract:
        * :meth:`acquire` blocks until the lease for ``key`` is held, then
          returns a :class:`TurnLeaseToken`. ``ttl`` bounds how long the lease
          survives without renewal so a crashed holder self-heals.
        * :meth:`release` is identity-checked against the token's ``owner`` and
          idempotent: releasing an already-expired/reclaimed lease is a no-op,
          never an error and never another owner's lease.
        * :meth:`hold` is the ergonomic async context manager wrapping
          acquire/release, used at the ``async with self._turn_lock.hold(...)``
          call site.

    A backend outage must fail *open* (degrade to a loud warning rather than
    wedging a healthy session), mirroring the fail-safe defaults elsewhere.
    """

    async def acquire(self, key: str, *, owner: str, ttl: float) -> TurnLeaseToken:
        """Block until the lease for ``key`` is held; return its token."""
        ...

    async def release(self, token: TurnLeaseToken) -> None:
        """Release ``token``'s lease (identity-checked, idempotent)."""
        ...

    def hold(
        self, key: str, *, owner: str, ttl: float
    ) -> "AbstractAsyncContextManager[TurnLeaseToken]":
        """Return an async context manager holding the lease for the block."""
        ...


class LocalTurnLock:
    """Default in-process turn lock — today's ``asyncio.Lock`` behaviour.

    Zero-cost, dependency-free implementation of :class:`TurnLockProtocol` for
    single-replica / no-backend deployments. It serialises turns within one
    process (per event loop) exactly as the existing ``LockMap`` does, so
    upgrading is byte-for-byte backward compatible. It provides **no** cross-
    process guarantee — selecting a distributed backend (e.g. ``redis``) is what
    extends serialisation across replicas.

    The ``owner``/``ttl`` arguments are accepted for protocol symmetry but are
    inert here: an in-process ``asyncio.Lock`` is released deterministically
    when the holding task exits, so there is no crashed-holder lease to expire.
    """

    def __init__(self) -> None:
        self._locks: Dict[str, "asyncio.Lock"] = {}
        # Current lease holder per key, so release() is identity-checked: only
        # the exact token handed out by the latest acquire() may release, so a
        # stale token can never clobber a waiter that took the lock after it.
        self._holders: Dict[str, TurnLeaseToken] = {}

    def _lock_for(self, key: str) -> "asyncio.Lock":
        lock = self._locks.get(key)
        if lock is None:
            import asyncio

            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def acquire(self, key: str, *, owner: str, ttl: float) -> TurnLeaseToken:
        lock = self._lock_for(key)
        await lock.acquire()
        token = TurnLeaseToken(key=key, owner=owner, expires_at=0.0)
        self._holders[key] = token
        return token

    async def release(self, token: TurnLeaseToken) -> None:
        # Identity-checked & idempotent: a stale/duplicate token whose lease has
        # since been reclaimed by a waiter is a harmless no-op, never another
        # holder's lease. ``is`` (not ``==``) so equal-valued tokens from two
        # acquires are not conflated (``TurnLeaseToken`` is frozen/value-equal).
        if self._holders.get(token.key) is not token:
            return
        del self._holders[token.key]
        lock = self._locks.get(token.key)
        if lock is not None and lock.locked():
            lock.release()

    def hold(
        self, key: str, *, owner: str, ttl: float
    ) -> "AbstractAsyncContextManager[TurnLeaseToken]":
        return _TurnLeaseHold(self, key, owner=owner, ttl=ttl)


class _TurnLeaseHold:
    """Async context manager wrapping acquire/release for any turn lock.

    Reusable by any :class:`TurnLockProtocol` implementation so the concrete
    lock only needs ``acquire``/``release``; ``hold`` composes them safely
    (releasing on every exit path, including exceptions).
    """

    def __init__(
        self, lock: "TurnLockProtocol", key: str, *, owner: str, ttl: float
    ) -> None:
        self._lock = lock
        self._key = key
        self._owner = owner
        self._ttl = ttl
        self._token: Optional[TurnLeaseToken] = None

    async def __aenter__(self) -> TurnLeaseToken:
        self._token = await self._lock.acquire(
            self._key, owner=self._owner, ttl=self._ttl
        )
        return self._token

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            await self._lock.release(self._token)
            self._token = None


# ---------------------------------------------------------------------------
# Per-session turn-execution isolation (Issue #4011)
#
# Today every session's agent turn runs as an ``asyncio`` task on the single
# gateway event loop, in one process: a turn that wedges the loop (a tight CPU
# loop, a blocking C-extension call, GIL starvation), runs away, or crashes
# the interpreter degrades or kills *every* session at once, and the only
# remedy the runtime has is a whole-process ``os._exit(75)`` restart that
# drops every other user's in-flight turn.
#
# This is the pure, dependency-free contract for a swappable turn *executor*,
# mirroring how every other gateway robustness knob (drain, admission,
# rate-limit, liveness, dead-letter, turn-lock) is a swappable protocol in
# core. The executor decides *where* a session's turn runs; the default
# :class:`InProcessTurnExecutor` runs it on the current loop exactly as today
# (zero change for existing users, no dependency introduced). Heavy executors
# that place a turn on an isolated worker (subprocess / container / remote),
# each with optional per-worker resource limits, are optional-dep runtime
# concerns that live in the wrapper/bot package; core keeps only the protocol,
# the placement/fencing invariants, and the safe in-process default so a bad
# turn can be torn down on its own worker without an ``os._exit`` of the whole
# gateway.
# ---------------------------------------------------------------------------


class WorkerWedgedError(Exception):
    """Raised when a session's turn worker is wedged / unresponsive.

    Signals the gateway that the placement's worker can no longer make
    progress (a wedged loop, an unresponsive subprocess/container, a lost
    remote worker). The gateway responds by tearing down *only* that
    placement (:meth:`TurnExecutorProtocol.teardown`) and re-placing the
    session, rather than the process-wide ``os._exit`` that a single shared
    loop forces today. Distinct from ordinary turn errors, which surface as
    the turn's own exception and do not condemn the worker.
    """


@dataclass(frozen=True)
class TurnPlacement:
    """Which worker owns a session's turns, and at what epoch (Issue #4011).

    A lifecycle-owned handle returned by :meth:`TurnExecutorProtocol.place`
    and passed back to :meth:`~TurnExecutorProtocol.execute_turn` /
    :meth:`~TurnExecutorProtocol.teardown`. The gateway revalidates the
    placement (worker alive, matching ``epoch``) immediately before dispatch
    and again after any awaited admission/approval work; a stale placement
    (its worker was replaced, so ``epoch`` no longer matches) **fails closed**
    and the session is re-placed rather than executed on a dead worker.

    Attributes:
        session_id: The resolved session whose turns this placement serves.
        worker_id: Opaque id of the worker that owns the session's turns. For
            the in-process default this is a constant (one loop, one worker);
            for isolated executors it identifies the subprocess/container/
            remote worker.
        epoch: Monotonic generation bumped whenever the worker backing a
            session is replaced (e.g. after a wedge teardown). A turn carrying
            a stale epoch must not run — the fencing token that stops a
            reclaimed worker from executing against a session it no longer owns.
    """

    session_id: str
    worker_id: str
    epoch: int = 0


@runtime_checkable
class TurnExecutorProtocol(Protocol):
    """Contract for *where* a session's agent turn executes (Issue #4011).

    The gateway calls :meth:`place` to obtain a :class:`TurnPlacement` for a
    session, then :meth:`execute_turn` to run the turn on that placement, and
    :meth:`teardown` to reclaim a placement's worker. The default
    :class:`InProcessTurnExecutor` runs the turn on the current event loop,
    reproducing today's behaviour exactly; an isolated executor (subprocess /
    container / remote, in the wrapper) runs it on its own worker so a wedged,
    runaway, or crashed turn is contained to its session.

    Contract:
        * :meth:`place` returns the placement that owns ``session_id``'s
          turns. Implementations may cache a placement per session and bump
          its ``epoch`` when the backing worker is replaced.
        * :meth:`execute_turn` runs ``turn`` (an ``async`` no-arg callable the
          gateway already built for this turn) on ``placement`` and returns
          its result. The in-process default awaits ``turn`` directly on the
          current loop. An isolated executor does **not** ship this live
          callable (and its captured loop/agent state) across a process
          boundary — the worker owns the session (via :meth:`place`) and
          rebuilds/dispatches the turn from serialisable inputs on its own
          side; ``turn`` then acts as the gateway-side await point for that
          worker's result. ``cancel_token`` carries the per-turn interrupt so
          the existing cancellation seam is preserved. ``limits`` optionally
          bounds the worker's CPU/memory/wall time (honoured by isolated
          executors; ignored in-process). It raises :class:`WorkerWedgedError`
          if the placement's worker can no longer make progress.
        * :meth:`teardown` reclaims ``placement``'s worker (kills the
          subprocess/container/remote worker, or is a no-op in-process),
          scoped to the owning session only.

    A worker fault must fail *scoped*: tear down the offending placement and
    re-place its session, never the whole gateway — mirroring the fail-safe,
    blast-radius-contained defaults elsewhere.
    """

    async def place(self, session_id: str) -> TurnPlacement:
        """Return the placement that owns ``session_id``'s turns."""
        ...

    async def execute_turn(
        self,
        placement: TurnPlacement,
        turn: "Callable[[], Awaitable[Any]]",
        *,
        cancel_token: Any = None,
        limits: Any = None,
    ) -> Any:
        """Run ``turn`` on ``placement`` and return its result."""
        ...

    async def teardown(self, placement: TurnPlacement, *, reason: str) -> None:
        """Reclaim ``placement``'s worker (scoped to its session)."""
        ...


class InProcessTurnExecutor:
    """Default turn executor — today's on-loop behaviour, no isolation.

    Zero-cost, dependency-free implementation of
    :class:`TurnExecutorProtocol` for single-process deployments. It runs each
    turn directly on the current event loop exactly as the gateway does today,
    so selecting it (or leaving the executor unset) is byte-for-byte backward
    compatible and introduces no dependency. It provides **no** blast-radius
    isolation: a turn that wedges the loop still affects the process — choosing
    an isolated executor (subprocess / container / remote, in the wrapper) is
    what contains a bad turn to its own worker.

    All turns share one worker (the current process/loop), so every placement
    carries the same constant ``worker_id`` at ``epoch`` 0, and ``teardown``
    is inert — an in-process turn is cancelled through the existing
    ``cancel_token`` when the holding task exits, so there is no worker to
    reclaim. The ``limits`` argument is accepted for protocol symmetry but is
    inert here (no separate worker to bound).
    """

    _WORKER_ID = "inprocess"

    async def place(self, session_id: str) -> TurnPlacement:
        return TurnPlacement(
            session_id=session_id, worker_id=self._WORKER_ID, epoch=0
        )

    async def execute_turn(
        self,
        placement: TurnPlacement,
        turn: "Callable[[], Awaitable[Any]]",
        *,
        cancel_token: Any = None,
        limits: Any = None,
    ) -> Any:
        # Run the gateway's pre-built turn coroutine on this loop, unchanged.
        return await turn()

    async def teardown(self, placement: TurnPlacement, *, reason: str) -> None:
        # No isolated worker to reclaim; the shared loop keeps serving.
        return None


# ---------------------------------------------------------------------------
# Declarative method -> required-scope registry (Issue #3206)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GatewayMethodDescriptor:
    """Declarative authorisation descriptor for one gateway method.

    A descriptor states — once, next to the protocol it guards — *what scope a
    caller must hold* to invoke ``name``. The dispatcher resolves the required
    scope from the registry instead of scattering ``_require_scope`` /
    ``_client_has_scope`` calls per endpoint, so a newly added method is
    **closed until explicitly classified** rather than reachable by omission.

    Attributes:
        name: The method / route / message-type identifier (e.g.
            ``"agent.message"``, ``"channels.control"``).
        required_scope: The baseline scope required to invoke the method.
        owner: Who declared the method (``"core"``, a plugin name, ...). Purely
            informational; helps auditing a growing control surface.
        since: Optional version/date the method was classified.
        escalate_fields: Optional per-payload-field escalation. Maps a param
            field name to the stricter scope demanded when that field is
            present. Fields not listed here are treated as *unknown/structural*
            and escalate to :attr:`escalate_unknown_scope` (fail closed) when
            :attr:`strict_fields` is True.
        strict_fields: When True, any payload field not in ``escalate_fields``
            (and not in ``safe_fields``) escalates to
            :attr:`escalate_unknown_scope`. Defaults to False so today's
            behaviour (no field-level derivation) is preserved unless opted in.
        safe_fields: Field names that never escalate — read-only / benign
            params. Only consulted when ``strict_fields`` is True.
        escalate_unknown_scope: Scope demanded for unknown structural fields
            under ``strict_fields``. Defaults to ``ADMIN`` (fail closed).
    """

    name: str
    required_scope: OperatorScope = OperatorScope.ADMIN
    owner: str = "core"
    since: Optional[str] = None
    escalate_fields: Dict[str, OperatorScope] = field(default_factory=dict)
    strict_fields: bool = False
    safe_fields: Set[str] = field(default_factory=set)
    escalate_unknown_scope: OperatorScope = OperatorScope.ADMIN

    def __post_init__(self) -> None:
        """Defensively copy the mutable collections so the descriptor is a
        genuinely immutable authorisation record.

        ``@dataclass(frozen=True)`` blocks attribute *reassignment* but not
        in-place mutation of the referenced dict/set. Direct construction
        (e.g. a plugin building a descriptor without going through
        :func:`register_gateway_method`) could otherwise mutate
        ``escalate_fields`` / ``safe_fields`` after the fact and silently
        change the resolved scope. Freeze them at construction so the resolved
        scope can never drift after registration.
        """
        object.__setattr__(self, "escalate_fields", dict(self.escalate_fields))
        object.__setattr__(self, "safe_fields", frozenset(self.safe_fields))

    def resolve(self, params: Optional[Dict[str, Any]] = None) -> OperatorScope:
        """Resolve the effective required scope for a call with ``params``.

        Starts from :attr:`required_scope` and escalates (never de-escalates)
        based on the payload:

          * any field listed in :attr:`escalate_fields` raises the requirement
            to that field's scope;
          * under :attr:`strict_fields`, any field that is neither a
            ``safe_field`` nor an ``escalate_field`` is treated as unknown /
            structural and raises the requirement to
            :attr:`escalate_unknown_scope` (fail closed on unknown fields).
        """
        required = self.required_scope
        if params:
            for key in params:
                escalated = self.escalate_fields.get(key)
                if escalated is not None:
                    required = _max_scope(required, escalated)
                elif self.strict_fields and key not in self.safe_fields:
                    required = _max_scope(required, self.escalate_unknown_scope)
        return required


# Privilege lattice used to combine (never weaken) scopes.
#
# READ < WRITE are a strict linear chain. APPROVALS and PAIRING are *sibling*
# capabilities at the same tier: each is stricter than WRITE, but they are
# **incomparable** to each other (holding APPROVALS does not imply PAIRING or
# vice versa). ADMIN is the top of the lattice.
#
# ``_SCOPE_TIER`` gives the linear rank; APPROVALS and PAIRING share a tier only
# to express "both above WRITE, both below ADMIN". Combining two *distinct*
# scopes that sit at that same tier is unsound to collapse into one of them, so
# :func:`_max_scope` escalates such a pair to their common upper bound, ADMIN
# (fail closed) rather than silently picking whichever was passed first.
_SCOPE_TIER: Dict[OperatorScope, int] = {
    OperatorScope.READ: 0,
    OperatorScope.WRITE: 1,
    OperatorScope.APPROVALS: 2,
    OperatorScope.PAIRING: 2,
    OperatorScope.ADMIN: 3,
}

# Scopes at a shared tier that are siblings (incomparable), so combining two
# different ones must escalate rather than pick one.
_INCOMPARABLE_TIERS = frozenset({2})


def _max_scope(a: OperatorScope, b: OperatorScope) -> OperatorScope:
    """Return the stricter scope, escalating incomparable siblings to ADMIN.

    For the linear part of the lattice (READ < WRITE < ... < ADMIN) this
    returns the higher-ranked scope. When ``a`` and ``b`` are two *distinct*
    scopes sharing an incomparable tier (e.g. APPROVALS vs PAIRING), neither
    implies the other, so the combined requirement is escalated to their common
    upper bound (``ADMIN``) to stay fail-closed — a single-scope check can then
    never be satisfied by holding only one of the two required capabilities.
    """
    if a == b:
        return a
    tier_a = _SCOPE_TIER.get(a, _SCOPE_TIER[OperatorScope.ADMIN])
    tier_b = _SCOPE_TIER.get(b, _SCOPE_TIER[OperatorScope.ADMIN])
    if tier_a == tier_b and tier_a in _INCOMPARABLE_TIERS:
        return OperatorScope.ADMIN
    return b if tier_b > tier_a else a


# Module-level registry. Kept intentionally simple (a dict) so the contract is
# a pure, dependency-free lookup that clients and the wrapper can share.
GATEWAY_METHODS: Dict[str, GatewayMethodDescriptor] = {}


def register_gateway_method(
    name: str,
    *,
    scope: OperatorScope = OperatorScope.ADMIN,
    owner: str = "core",
    since: Optional[str] = None,
    escalate_fields: Optional[Dict[str, OperatorScope]] = None,
    strict_fields: bool = False,
    safe_fields: Optional[Set[str]] = None,
    escalate_unknown_scope: OperatorScope = OperatorScope.ADMIN,
    replace: bool = False,
) -> GatewayMethodDescriptor:
    """Register (once) the required scope for a gateway method.

    Core methods are registered at import time (see below); plugins that add
    new gateway surface should register their descriptors through this same
    function so they inherit default-deny semantics.

    Raises:
        ValueError: If ``name`` is already registered and ``replace`` is False.
    """
    if not replace and name in GATEWAY_METHODS:
        raise ValueError(
            f"gateway method {name!r} is already registered "
            f"(pass replace=True to override)"
        )
    desc = GatewayMethodDescriptor(
        name=name,
        required_scope=scope,
        owner=owner,
        since=since,
        escalate_fields=dict(escalate_fields or {}),
        strict_fields=strict_fields,
        safe_fields=set(safe_fields or ()),
        escalate_unknown_scope=escalate_unknown_scope,
    )
    GATEWAY_METHODS[name] = desc
    return desc


def resolve_required_scope(
    method: str, params: Optional[Dict[str, Any]] = None
) -> OperatorScope:
    """Resolve the scope required to invoke ``method`` with ``params``.

    Default-deny: an unclassified/unknown method requires ``ADMIN`` so new
    control surface is closed until explicitly classified — the omission fails
    **closed** rather than open.
    """
    desc = GATEWAY_METHODS.get(method)
    if desc is None:
        return OperatorScope.ADMIN
    return desc.resolve(params)


# Core method classification. Registered once at import so the dispatcher can
# consult the registry instead of scattered per-endpoint checks. Structural
# mutations (channel control) demand ADMIN; sending as the agent needs WRITE;
# status/read needs READ. Anything unregistered defaults to ADMIN (deny).
def _register_core_gateway_methods() -> None:
    core: Dict[str, OperatorScope] = {
        # Connection lifecycle. These run before a client can hold any scope, so
        # they must not require one -- classifying them ADMIN by omission is what
        # kept resolve_required_scope() from ever being wired into dispatch.
        "hello": OperatorScope.READ,
        "join": OperatorScope.READ,
        "leave": OperatorScope.READ,
        "agent.message": OperatorScope.WRITE,
        "message": OperatorScope.WRITE,
        # Aborting a turn mutates it, so it carries the same scope as sending one.
        "abort": OperatorScope.WRITE,
        "session.status": OperatorScope.READ,
        "session.transcript": OperatorScope.READ,
        "approvals.resolve": OperatorScope.APPROVALS,
        "pairing.approve": OperatorScope.PAIRING,
        "pairing.revoke": OperatorScope.PAIRING,
        "channels.control": OperatorScope.ADMIN,
        "channels.pause": OperatorScope.ADMIN,
        "channels.resume": OperatorScope.ADMIN,
        "channels.reconnect": OperatorScope.ADMIN,
    }
    for name, scope in core.items():
        register_gateway_method(name, scope=scope, owner="core", replace=True)


_register_core_gateway_methods()


# ---------------------------------------------------------------------------
# Global operator emergency-stop / pause brake (Issue #4220)
# ---------------------------------------------------------------------------
#
# A single, durable, fail-safe operator brake: "stop admitting NEW agent work
# everywhere, right now, but let in-flight runs finish — and resume later with
# no restart." Every new-work admission seam (WebSocket inbound, HTTP/MCP
# inbound, kanban dispatch cycle, scheduler due-loop) consults one shared
# contract instead of each lane deciding independently.
#
# Design mirrors the drain / idle / admission / liveness policy family already
# in this module: a pure ``Protocol`` in core plus a lightweight default and a
# durable fail-safe backend. When no brake is engaged, ``is_engaged()`` is
# ``False`` and behaviour is byte-for-byte today's — zero cost, no new
# dependency, fully backward-compatible.


@dataclass(frozen=True)
class EmergencyStopState:
    """Immutable snapshot of the operator brake, for status/audit surfaces.

    ``engaged`` is the only field the hot path needs; ``reason``/``actor``/
    ``at`` provide the optional audit trail surfaced in ``/health``/status.
    """

    engaged: bool
    reason: str = ""
    actor: str = ""
    at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engaged": self.engaged,
            "reason": self.reason,
            "actor": self.actor,
            "at": self.at,
        }


@runtime_checkable
class EmergencyStopProtocol(Protocol):
    """Pure contract for the global operator brake consulted at every seam.

    Fail-safe rule: if the engaged state cannot be read with confidence (a
    corrupt / unreadable durable sentinel), ``is_engaged()`` MUST return
    ``True`` — an ambiguous brake holds new work rather than letting it run
    freely. ``engage``/``disengage`` are idempotent.
    """

    def is_engaged(self) -> bool: ...

    def engage(self, *, reason: str = "", actor: str = "") -> None: ...

    def disengage(self) -> None: ...

    def state(self) -> EmergencyStopState: ...


class NullEmergencyStop:
    """Default no-op brake: never engaged, no persistence.

    Selected by ``backend: "off"`` (the default) so a gateway with no brake
    configured behaves exactly as before — ``is_engaged()`` is always
    ``False`` and ``engage``/``disengage`` are inert.
    """

    def is_engaged(self) -> bool:
        return False

    def engage(self, *, reason: str = "", actor: str = "") -> None:
        return None

    def disengage(self) -> None:
        return None

    def state(self) -> EmergencyStopState:
        return EmergencyStopState(engaged=False)


class FileEmergencyStop:
    """Durable, fail-safe file-sentinel operator brake.

    Engaging writes a small JSON sentinel at ``path``; disengaging removes it.
    The engaged state therefore survives a crash/restart (durable) and is
    shared by every lane that consults the same path.

    Fail-safe: any error reading the sentinel — a partially written file,
    corrupt JSON, a permission error — is treated as *engaged*. An ambiguous
    brake holds new work; it never silently falls open to "run freely". The
    common, unambiguous case (sentinel simply absent) reports not-engaged.

    Pure-stdlib (``os``/``json``): no new dependency, safe to live in core.
    """

    def __init__(self, path: str) -> None:
        if not path:
            raise ValueError("FileEmergencyStop requires a non-empty sentinel path")
        import os

        self._path = os.path.expanduser(str(path))

    def is_engaged(self) -> bool:
        import os

        if not os.path.exists(self._path):
            return False
        # Present but unreadable/corrupt => fail-safe engaged.
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                fh.read()
            return True
        except OSError:
            return True

    def engage(self, *, reason: str = "", actor: str = "") -> None:
        import json
        import os

        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "engaged": True,
            "reason": str(reason or ""),
            "actor": str(actor or ""),
            "at": time.time(),
        }
        # Atomic replace so a reader never observes a half-written sentinel
        # (which would fail-safe engaged anyway, but this keeps it clean).
        # ``mkstemp`` in the sentinel's own directory yields an unpredictable
        # name owned by us, so a local attacker cannot pre-create a symlink to
        # redirect the write. fsync + parent-dir fsync make an engaged brake
        # durable across an abrupt crash.
        import tempfile

        fd, tmp = tempfile.mkstemp(
            dir=directory or ".", prefix=".gateway.pause.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        if directory:
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass

    def disengage(self) -> None:
        import os

        try:
            os.remove(self._path)
        except FileNotFoundError:
            return None

    def state(self) -> EmergencyStopState:
        import json
        import os

        if not os.path.exists(self._path):
            return EmergencyStopState(engaged=False)
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("sentinel is not a JSON object")
            return EmergencyStopState(
                engaged=True,
                reason=str(data.get("reason", "")),
                actor=str(data.get("actor", "")),
                at=float(data.get("at", 0.0) or 0.0),
            )
        except (OSError, TypeError, ValueError):
            # Fail-safe: unreadable/corrupt sentinel counts as engaged. A valid
            # JSON object with a non-numeric ``at`` (e.g. a list) raises
            # TypeError from ``float()`` and must also fail-safe engaged.
            return EmergencyStopState(engaged=True, reason="unreadable-sentinel")
