"""Session-projection reducer for Gateway clients (Issue #5324).

A pure, dependency-free state machine that folds an initial snapshot plus a
stream of :class:`~praisonaiagents.gateway.protocols.GatewayEvent`\\ s into a
consistent, de-duplicated, memory-bounded view of a session. It turns *a
stream of frames* into *a correct, resumable view* so every gateway client
(the bundled Python client, the ``praisonai-ts`` mirror, the realtime
dashboard, third-party integrations) stops re-implementing the same fiddly
reconciliation logic:

- **Snapshot + fold**: apply a snapshot, then fold live events into ``entries``.
- **Identity de-duplication**: a final assistant message that arrives both as a
  streamed delta sequence *and* as a persisted transcript row renders once.
- **Optimistic reconciliation**: a locally-echoed outbound message is replaced
  (not duplicated) by its durable counterpart, keyed on ``request_id``.
- **Gap handling**: a sequence gap flips ``has_transport_gap``; after a resync
  the reducer converges rather than appending duplicates.
- **Bounded retention**: tracked runs are capped (LRU) so long-lived sessions
  stay memory-bounded; a run with an active (unfinished) stream is never
  evicted.

This module lives in **core** because it is a pure reducer built on types core
already owns (``GatewayEvent``/``GatewayMessage``/``EventType``); it must not be
trapped in the transport client so all clients can share it. It has **no**
third-party dependencies and does no I/O.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple, Union

from .protocols import EventType, GatewayEvent, GatewayMessage

__all__ = [
    "RunView",
    "SessionProjectionState",
    "SessionProjection",
]


def _event_type_value(event: GatewayEvent) -> str:
    """Return the wire string for an event type (enum or raw str)."""
    etype = event.type
    return etype.value if isinstance(etype, EventType) else str(etype)


def _run_id_of(event: GatewayEvent) -> Optional[str]:
    """Best-effort run/turn identifier for a streaming event."""
    data = event.data or {}
    for key in ("run_id", "turn_id", "message_id", "response_id"):
        value = data.get(key)
        if value:
            return str(value)
    return None


@dataclass(frozen=True)
class RunView:
    """Immutable view of a single agent run/turn within a session.

    Attributes:
        run_id: The run/turn identifier the streamed deltas belong to.
        text: The accumulated streamed text so far.
        done: Whether the stream has ended (``STREAM_END``) for this run.
        final_message_id: ``message_id`` of the persisted final row, once the
            durable transcript row for this run has been reconciled in.
    """

    run_id: str
    text: str = ""
    done: bool = False
    final_message_id: Optional[str] = None


@dataclass(frozen=True)
class SessionProjectionState:
    """Immutable, de-duplicated, bounded view of a session.

    Attributes:
        entries: Ordered transcript messages, de-duplicated by identity.
        runs: Per-run streaming views, keyed by ``run_id``.
        has_transport_gap: ``True`` when a sequence gap was observed and a
            resync has not yet reconciled the state.
    """

    entries: Tuple[GatewayMessage, ...] = ()
    runs: Dict[str, RunView] = field(default_factory=dict)
    has_transport_gap: bool = False


class SessionProjection:
    """Fold a snapshot + :class:`GatewayEvent`\\ s into a consistent view.

    The reducer is idempotent: applying the same persisted message twice (e.g.
    once from the live stream's ``STREAM_END`` and once as a durable transcript
    row on reconnect) yields a single entry. Feed it with
    :meth:`apply_snapshot` then :meth:`apply`; read :attr:`state` at any time.

    Args:
        max_tracked_runs: Cap on how many finished runs are tracked before the
            oldest are evicted (LRU). Runs with an active/unfinished stream are
            never evicted. Must be positive.
    """

    def __init__(self, *, max_tracked_runs: int = 200) -> None:
        if max_tracked_runs <= 0:
            raise ValueError("max_tracked_runs must be positive")
        self._max_tracked_runs = max_tracked_runs
        self._entries: List[GatewayMessage] = []
        # message_id -> index into self._entries, for identity de-dup.
        self._by_message_id: Dict[str, int] = {}
        # request_id -> index into self._entries, for optimistic reconciliation.
        self._by_request_id: Dict[str, int] = {}
        # run_id -> RunView, ordered for LRU eviction.
        self._runs: "OrderedDict[str, RunView]" = OrderedDict()
        self._expected_sequence: Optional[int] = None
        self._has_gap: bool = False

    # -- public API -------------------------------------------------------

    @property
    def state(self) -> SessionProjectionState:
        """Return the current immutable projection state."""
        return SessionProjectionState(
            entries=tuple(self._entries),
            runs=dict(self._runs),
            has_transport_gap=self._has_gap,
        )

    def apply_snapshot(
        self, snapshot: Union[Dict[str, Any], Any]
    ) -> SessionProjectionState:
        """Replace all tracked state from a full snapshot.

        A snapshot resets gap tracking and rebuilds the transcript from the
        persisted rows it carries, so a resync converges rather than appending
        duplicates. Accepts a mapping (``{"messages"/"entries": [...],
        "cursor"/"sequence": N}``) or any object exposing ``messages``/
        ``entries`` and an optional ``sequence``/``cursor`` attribute.
        """
        self._entries = []
        self._by_message_id = {}
        self._by_request_id = {}
        self._runs = OrderedDict()
        self._has_gap = False
        self._expected_sequence = None

        rows = _snapshot_rows(snapshot)
        for row in rows:
            message = _coerce_message(row)
            if message is not None:
                self._upsert_message(message)

        seq = _snapshot_sequence(snapshot)
        if seq is not None:
            self._expected_sequence = seq + 1
        return self.state

    def apply(self, event: GatewayEvent) -> SessionProjectionState:
        """Fold a single event into the state and return the new state.

        Idempotent for persisted messages (de-duped by ``message_id``) and for
        optimistic echoes (reconciled by ``request_id``). Streaming deltas are
        accumulated per run; ``STREAM_END`` closes the run. Sequence gaps set
        :attr:`SessionProjectionState.has_transport_gap`.
        """
        self._track_sequence(event)

        etype = _event_type_value(event)
        if etype in _STREAM_DELTA_TYPES:
            self._apply_delta(event)
        elif etype == EventType.STREAM_END.value:
            self._apply_stream_end(event)
        elif etype in _MESSAGE_TYPES:
            self._apply_message(event)
        # Other event types (health, presence, typing, ...) carry no transcript
        # state; they are intentionally ignored by the projection.
        return self.state

    # -- sequence / gap tracking -----------------------------------------

    def _track_sequence(self, event: GatewayEvent) -> None:
        seq = event.sequence
        if seq is None:
            return
        if self._expected_sequence is not None and seq > self._expected_sequence:
            # A hole in the monotonic sequence: mark the view as gapped until a
            # snapshot/resync reconciles it.
            self._has_gap = True
        # Advance the watermark to the highest sequence seen.
        if self._expected_sequence is None or seq >= self._expected_sequence:
            self._expected_sequence = seq + 1

    # -- message handling -------------------------------------------------

    def _apply_message(self, event: GatewayEvent) -> None:
        message = _coerce_message(event.data)
        if message is None:
            return
        request_id = _request_id_of(event, message)
        self._upsert_message(message, request_id=request_id)

    def _upsert_message(
        self, message: GatewayMessage, *, request_id: Optional[str] = None
    ) -> None:
        # Identity de-dup: same persisted row seen twice renders once.
        existing = self._by_message_id.get(message.message_id)
        if existing is not None:
            self._entries[existing] = message
            self._reindex(existing, message, request_id)
            return

        # Optimistic reconciliation: a durable row replaces its local echo.
        if request_id is not None:
            echoed = self._by_request_id.get(request_id)
            if echoed is not None:
                stale_id = self._entries[echoed].message_id
                self._entries[echoed] = message
                # Drop the echo's provisional message_id so a re-delivered echo
                # cannot later overwrite the durable row via identity lookup.
                if stale_id != message.message_id:
                    self._by_message_id.pop(stale_id, None)
                self._reindex(echoed, message, request_id)
                return

        self._entries.append(message)
        idx = len(self._entries) - 1
        self._by_message_id[message.message_id] = idx
        if request_id is not None:
            self._by_request_id[request_id] = idx

    def _reindex(
        self,
        idx: int,
        message: GatewayMessage,
        request_id: Optional[str],
    ) -> None:
        self._by_message_id[message.message_id] = idx
        if request_id is not None:
            self._by_request_id[request_id] = idx

    # -- streaming handling ----------------------------------------------

    def _apply_delta(self, event: GatewayEvent) -> None:
        run_id = _run_id_of(event)
        if run_id is None:
            return
        chunk = _delta_text_of(event)
        current = self._runs.get(run_id)
        if current is None:
            current = RunView(run_id=run_id, text=chunk)
        else:
            current = replace(current, text=current.text + chunk)
        self._runs[run_id] = current
        self._runs.move_to_end(run_id)
        self._evict_runs()

    def _apply_stream_end(self, event: GatewayEvent) -> None:
        run_id = _run_id_of(event)
        if run_id is None:
            return
        current = self._runs.get(run_id) or RunView(run_id=run_id)
        final_id = None
        data = event.data or {}
        final_id = data.get("message_id") or data.get("final_message_id")
        current = replace(
            current,
            done=True,
            final_message_id=str(final_id) if final_id else current.final_message_id,
        )
        self._runs[run_id] = current
        self._runs.move_to_end(run_id)
        self._evict_runs()

    def _evict_runs(self) -> None:
        if len(self._runs) <= self._max_tracked_runs:
            return
        # Evict oldest finished runs first; never evict an active stream.
        for run_id in list(self._runs.keys()):
            if len(self._runs) <= self._max_tracked_runs:
                break
            if self._runs[run_id].done:
                del self._runs[run_id]


# Streaming delta event types whose text is accumulated per run.
_STREAM_DELTA_TYPES = frozenset(
    {
        EventType.TOKEN_STREAM.value,
        "delta_text",
    }
)

# Event types carrying a persisted transcript message.
_MESSAGE_TYPES = frozenset(
    {
        EventType.MESSAGE.value,
        "message_persisted",
    }
)


def _delta_text_of(event: GatewayEvent) -> str:
    data = event.data or {}
    for key in ("delta", "text", "content", "token", "chunk"):
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""


def _request_id_of(
    event: GatewayEvent, message: GatewayMessage
) -> Optional[str]:
    data = event.data or {}
    rid = data.get("request_id") or message.metadata.get("request_id")
    return str(rid) if rid else None


def _coerce_message(row: Any) -> Optional[GatewayMessage]:
    if isinstance(row, GatewayMessage):
        return row
    if isinstance(row, dict):
        payload = row
        # A "message" event wraps the row under a "message" key in some frames.
        if "message" in row and isinstance(row["message"], (dict, GatewayMessage)):
            inner = row["message"]
            return inner if isinstance(inner, GatewayMessage) else _coerce_message(inner)
        if "content" not in payload and "message_id" not in payload:
            return None
        try:
            return GatewayMessage.from_dict(payload)
        except Exception:
            return None
    return None


def _snapshot_rows(snapshot: Any) -> List[Any]:
    if isinstance(snapshot, dict):
        for key in ("messages", "entries", "transcript"):
            rows = snapshot.get(key)
            if isinstance(rows, list):
                return rows
        return []
    for attr in ("messages", "entries", "transcript"):
        rows = getattr(snapshot, attr, None)
        if isinstance(rows, list):
            return rows
    return []


def _snapshot_sequence(snapshot: Any) -> Optional[int]:
    if isinstance(snapshot, dict):
        for key in ("sequence", "cursor", "seq"):
            value = snapshot.get(key)
            if isinstance(value, int):
                return value
        return None
    for attr in ("sequence", "cursor", "seq"):
        value = getattr(snapshot, attr, None)
        if isinstance(value, int):
            return value
    return None
