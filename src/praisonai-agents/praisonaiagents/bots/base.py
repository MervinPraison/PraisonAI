"""
BasePlatformAdapter — the inheritable base class for gateway channel adapters.

This module provides a single, dependency-free base class that new messaging
channels can subclass. It defines a **minimal abstract contract** (four
methods) and a wide set of **capability-driven default implementations** so
that a new channel inherits robust delivery, chunking, retry/backoff, typing
heartbeats and graceful edit/delete fallbacks for free.

Design goals:

- **Protocol-only / dependency-free:** lives in core (``praisonai-agents``) so
  third-party adapters can type against it without importing the wrapper. No
  heavy platform SDK is imported here; the default orchestration is pure logic
  that only calls the abstract ``send``/``edit`` primitives.
- **Capability-driven:** all default behaviour keys off
  :class:`PlatformCapabilities` read via ``getattr`` so the shared delivery
  path has zero per-platform branching and degrades gracefully when a feature
  is absent.

Adding a channel becomes: subclass, implement ~4 methods, declare
capabilities — and inherit robust delivery/chunking/typing/retry.

Example::

    from praisonaiagents.bots import BasePlatformAdapter, PlatformCapabilities

    class AcmeBot(BasePlatformAdapter):
        capabilities = PlatformCapabilities(
            supports_edit=True, supports_typing=True, max_message_length=4096,
        )

        async def connect(self, *, is_reconnect=False):
            ...
            return True

        async def disconnect(self):
            ...

        async def send(self, chat_id, content, *, reply_to=None, metadata=None):
            message_id = await acme_api.send(chat_id, content)
            return SendResult(ok=True, message_id=message_id, chat_id=chat_id)

        async def get_chat_info(self, chat_id):
            return {"id": chat_id}

    # chunking / retry / typing / edit fallbacks inherited, capability-gated
"""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from .protocols import PlatformCapabilities

__all__ = [
    "SendErrorKind",
    "SendResult",
    "classify_send_error",
    "BasePlatformAdapter",
]


class SendErrorKind(str, Enum):
    """Structured, machine-readable classification of *why* a send failed.

    Carried on :class:`SendResult` so the retry loop, delivery router,
    dead-target registry, DLQ and user-notice path can all reason about a
    failure uniformly instead of substring-matching an English error string.

    Members:
        RATE_LIMITED: Throttled by the platform (HTTP 429); retry after wait.
        TARGET_NOT_FOUND: Chat/channel no longer exists (HTTP 404/410); the
            whole target is permanently unreachable — do not retry, mark dead.
        FORBIDDEN: Bot was kicked/blocked or lacks rights (HTTP 403); the
            target is permanently unreachable — do not retry, mark dead.
        AUTH_FATAL: Bad/expired/revoked credential (HTTP 401); retrying the
            same token is pointless — surface as a degraded state.
        INVALID_REQUEST: Malformed payload the platform rejects (HTTP 400);
            retrying the identical request will fail again.
        TRANSIENT: Network blip / 5xx / timeout; safe to retry with backoff.
        UNKNOWN: Could not classify; treated as retryable to preserve the
            historical default (do not silently drop a send we can't classify).
    """

    RATE_LIMITED = "rate_limited"
    TARGET_NOT_FOUND = "target_not_found"
    FORBIDDEN = "forbidden"
    AUTH_FATAL = "auth_fatal"
    INVALID_REQUEST = "invalid_request"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


#: Kinds that must NOT be retried by the default delivery loop. Everything
#: else (rate-limited, transient, unknown) stays retryable so the historical
#: behaviour is preserved and only *provably permanent* failures short-circuit.
_NON_RETRYABLE_KINDS = frozenset(
    {
        SendErrorKind.TARGET_NOT_FOUND,
        SendErrorKind.FORBIDDEN,
        SendErrorKind.AUTH_FATAL,
        SendErrorKind.INVALID_REQUEST,
    }
)


def _retryable_for_kind(kind: Optional[SendErrorKind]) -> bool:
    """Derive whether a failure of ``kind`` should be retried.

    ``None`` (no classification) and the transient/rate-limited/unknown kinds
    are retryable; only the confirmed-permanent kinds are not.
    """
    if kind is None:
        return True
    return kind not in _NON_RETRYABLE_KINDS


def _error_status_code(exc: BaseException) -> Optional[int]:
    """Best-effort extract an HTTP/platform status code from ``exc``.

    Reads the common attributes platform SDKs expose (``status``,
    ``status_code``, ``error_code``) so the fallback classifier can key off a
    real status code with full fidelity rather than reverse-engineering the
    error's string. Returns None when no integer status is present.
    """
    for attr in ("status", "status_code", "error_code"):
        val = getattr(exc, attr, None)
        if isinstance(val, bool):
            continue
        if isinstance(val, int):
            return val
    return None


def classify_send_error(exc: BaseException) -> "SendResult":
    """Pure, dependency-free fallback classifier for a send exception.

    Maps an exception into a :class:`SendResult` carrying a
    :class:`SendErrorKind` and derived ``retryable`` flag, keying primarily off
    the HTTP/platform status code (highest fidelity) and falling back to a
    small set of generic, cross-platform substrings. It is deliberately
    conservative: anything it cannot confidently classify becomes
    ``UNKNOWN`` (retryable), preserving the historical retry-everything default.

    Adapters that know their native exception types should override
    :meth:`BasePlatformAdapter.classify_error` for higher fidelity; this
    ensures adapters that don't still behave correctly for standard HTTP cases.
    """
    error = str(exc)
    status = _error_status_code(exc)

    kind: SendErrorKind
    if status is not None:
        if status == 429:
            kind = SendErrorKind.RATE_LIMITED
        elif status == 401:
            kind = SendErrorKind.AUTH_FATAL
        elif status == 403:
            kind = SendErrorKind.FORBIDDEN
        elif status in (404, 410):
            kind = SendErrorKind.TARGET_NOT_FOUND
        elif status == 400:
            kind = SendErrorKind.INVALID_REQUEST
        elif 500 <= status < 600 or status == 408:
            kind = SendErrorKind.TRANSIENT
        else:
            kind = SendErrorKind.UNKNOWN
    elif isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        kind = SendErrorKind.TRANSIENT
    else:
        kind = _classify_by_text(error)

    return SendResult(
        ok=False,
        error=error,
        error_kind=kind,
        retryable=_retryable_for_kind(kind),
    )


#: Generic, cross-platform substrings used only when no status code / typed
#: exception is available. Kept intentionally small and lower-cased; adapters
#: own the high-fidelity mapping via ``classify_error``.
_TEXT_RATE_LIMITED = ("too many requests", "rate limit", "rate_limited", "flood")
_TEXT_FORBIDDEN = (
    "forbidden",
    "blocked",
    "kicked",
    "not enough rights",
    "no rights to send",
)
_TEXT_TARGET_NOT_FOUND = (
    "chat not found",
    "channel not found",
    "peer_id_invalid",
    "user is deactivated",
    "group chat was deleted",
)
_TEXT_AUTH_FATAL = (
    "unauthorized",
    "invalid token",
    "invalid_auth",
    "token_revoked",
    "not_authed",
    "authentication failed",
)
_TEXT_TRANSIENT = (
    "timeout",
    "timed out",
    "temporarily unavailable",
    "service unavailable",
    "connection reset",
    "connection refused",
    "bad gateway",
    "gateway timeout",
)


def _classify_by_text(error: str) -> SendErrorKind:
    """Classify a send error from its message when no status code is present."""
    text = error.lower()
    for pat in _TEXT_RATE_LIMITED:
        if pat in text:
            return SendErrorKind.RATE_LIMITED
    for pat in _TEXT_TARGET_NOT_FOUND:
        if pat in text:
            return SendErrorKind.TARGET_NOT_FOUND
    for pat in _TEXT_AUTH_FATAL:
        if pat in text:
            return SendErrorKind.AUTH_FATAL
    for pat in _TEXT_FORBIDDEN:
        if pat in text:
            return SendErrorKind.FORBIDDEN
    for pat in _TEXT_TRANSIENT:
        if pat in text:
            return SendErrorKind.TRANSIENT
    return SendErrorKind.UNKNOWN


@dataclass
class SendResult:
    """Result of a single outbound send/edit through an adapter.

    A small, transport-neutral value returned by :meth:`BasePlatformAdapter.send`
    and the default delivery helpers so callers can react uniformly regardless
    of platform.

    Attributes:
        ok: Whether the send succeeded.
        message_id: Platform message id of the last message sent (if any). For
            a chunked delivery this is the id of the final chunk.
        chat_id: The chat/channel the message was delivered to.
        message_ids: All platform message ids produced (one per chunk).
        error: Human-readable error string when ``ok`` is False.
        error_kind: Structured, machine-readable classification of *why* the
            send failed (see :class:`SendErrorKind`). ``None`` on success or
            when a legacy adapter reports a failure without classifying it.
        retryable: Whether the failure is worth retrying. Derived from
            ``error_kind`` (permanent kinds → False); defaults True so an
            unclassified failure preserves the historical retry-everything
            behaviour rather than being silently dropped.
        retry_after: Suggested seconds to wait before retrying (from the
            platform's rate-limit response, if provided).
        metadata: Additional platform-specific result details.
    """

    ok: bool = True
    message_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None
    error_kind: Optional[SendErrorKind] = None
    retryable: bool = True
    retry_after: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dictionary."""
        return {
            "ok": self.ok,
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "message_ids": list(self.message_ids),
            "error": self.error,
            "error_kind": self.error_kind.value if self.error_kind else None,
            "retryable": self.retryable,
            "retry_after": self.retry_after,
            "metadata": self.metadata,
        }


def _chunk_text(text: str, max_length: int) -> List[str]:
    """Split *text* into chunks of at most *max_length* characters.

    Prefers paragraph then line then hard-split boundaries. Pure and
    dependency-free; a subclass can override :meth:`BasePlatformAdapter.chunk`
    to use a richer platform-aware splitter.
    """
    if not text:
        return []
    if max_length <= 0 or len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    current = ""
    for para in re.split(r"\n\n", text):
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(para) <= max_length:
            current = para
            continue
        # Paragraph itself too long — split on lines, then hard-split.
        for line in para.split("\n"):
            cand = (current + "\n" + line) if current else line
            if len(cand) <= max_length:
                current = cand
                continue
            if current:
                chunks.append(current)
                current = ""
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current = line
    if current:
        chunks.append(current)
    return chunks


class BasePlatformAdapter(ABC):
    """Inheritable base class for gateway platform/channel adapters.

    Subclasses implement a **minimal abstract contract** (four methods) and
    inherit **capability-driven default behaviour** (chunking, retry/backoff,
    typing heartbeat, edit/delete fallbacks, formatting). Override any default
    only when the platform can do better.

    Declare platform features by setting the class attribute
    :attr:`capabilities` to a :class:`PlatformCapabilities` instance. The
    default delivery path reads capabilities via ``getattr`` so it degrades
    gracefully when a flag is absent.
    """

    #: Platform capabilities descriptor. Subclasses override with their own.
    capabilities: PlatformCapabilities = PlatformCapabilities()

    #: Max retry attempts for the default resilient delivery loop.
    max_retries: int = 3
    #: Base backoff (seconds) for exponential retry when no ``retry_after``.
    retry_base_delay: float = 0.5

    # ------------------------------------------------------------------ #
    # Required contract — subclasses MUST implement these four primitives. #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Establish the platform connection.

        Args:
            is_reconnect: True when re-establishing after a drop.

        Returns:
            True if the connection was established successfully.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down the platform connection and release resources."""
        ...

    @abstractmethod
    async def send(
        self,
        chat_id: Any,
        content: Union[str, Dict[str, Any]],
        *,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a single message to *chat_id* (one API call, no chunking).

        This is the low-level primitive the default delivery machinery builds
        on. Implementations should send *content* as-is and return a
        :class:`SendResult`. Chunking/retry/typing are handled by
        :meth:`deliver`; implementers need not repeat them here.
        """
        ...

    @abstractmethod
    async def get_chat_info(self, chat_id: Any) -> Dict[str, Any]:
        """Return metadata about a chat/channel (at least an ``id`` key)."""
        ...

    # ------------------------------------------------------------------ #
    # Inbound run/supervision contract seam.                              #
    #                                                                     #
    # The base defines *where* an adapter's inbound run loop lives so the #
    # wrapper's supervision layer (ConnectionMonitor / ChannelSupervisor  #
    # / ChannelHealthMonitor) can wrap it uniformly for every channel,    #
    # rather than each adapter hand-rolling its own reconnect loop. The   #
    # concrete supervisor engine stays in the wrapper to keep core        #
    # protocol-only and dependency-light; core owns only the seam.        #
    # ------------------------------------------------------------------ #

    #: Whether inbound supervision (auto-reconnect + health restart) should
    #: wrap this adapter's run loop by default. Adapters that manage their own
    #: reconnect loop internally may set this False to opt out.
    supervised_inbound: bool = True

    async def start(self) -> None:
        """Establish the connection and run the inbound loop until stopped.

        This is the seam the wrapper's supervision layer wraps: an adapter's
        ``start`` should run its inbound source (poll/listen/socket) and only
        return when the channel is stopped cleanly, raising on an unexpected
        drop so the supervisor can reconnect with backoff. Concrete adapters
        override this with their platform run loop.
        """
        raise NotImplementedError(
            "adapter must implement start() to run its inbound loop"
        )

    async def stop(self) -> None:
        """Signal the inbound loop to stop and tear down the connection.

        Default delegates to :meth:`disconnect`. Adapters with an explicit
        stop event override this to unblock their run loop first.
        """
        await self.disconnect()

    # ------------------------------------------------------------------ #
    # Identity canonicalization seam.                                     #
    #                                                                     #
    # The gateway keys each conversation on the platform-supplied user id.#
    # When a platform changes the *native* id for the *same human*        #
    # (WhatsApp JID→LID migration, a renamed handle-as-id, a              #
    # phone-number↔UUID alias flip) the raw id changes and the session    #
    # would silently fork — history/memory/run-state orphaned. This seam  #
    # lets an adapter map a volatile raw id to a stable canonical id      #
    # *before* it becomes part of the session key; the resolver's         #
    # explicit link/pairing lookup then runs on the stabilised id.        #
    #                                                                     #
    # It fulfils ``IdentityCanonicalizerProtocol`` (praisonaiagents.      #
    # gateway.protocols) so an adapter *is* its own canonicalizer: pass   #
    # ``self`` where that protocol is accepted.                           #
    # ------------------------------------------------------------------ #

    def canonicalize(self, platform: str, raw_user_id: str) -> str:
        """Map a raw, potentially-volatile platform id to a stable canonical id.

        Consulted on the session-key path *before* link/pairing resolution so
        an alias/format change for the *same* human (e.g. WhatsApp's JID→LID
        migration, a number↔UUID alias flip) collapses to one stable session
        key — preserving transcript, memory and in-flight run-state — instead
        of silently forking the conversation.

        This is the :class:`~praisonaiagents.gateway.protocols.
        IdentityCanonicalizerProtocol` method, so a ``BasePlatformAdapter``
        conforms structurally and can be handed anywhere that protocol is
        accepted.

        Default is the identity function, so adapters that do not override this
        are fully backward-compatible (the raw id keys the session exactly as
        before). Implementations MUST be deterministic and total: return the
        raw id unchanged when no canonical form is known, never raise.
        """
        return raw_user_id

    # ------------------------------------------------------------------ #
    # Capability helpers                                                  #
    # ------------------------------------------------------------------ #

    def _cap(self, name: str, default: Any) -> Any:
        """Read a capability flag with a fallback default."""
        return getattr(self.capabilities, name, default)

    @property
    def max_message_length(self) -> int:
        """Platform max message length (0 = unlimited)."""
        return int(self._cap("max_message_length", 4096) or 0)

    @property
    def supports_edit(self) -> bool:
        """Whether the platform supports in-place message edits."""
        return bool(self._cap("supports_edit", False))

    @property
    def supports_typing(self) -> bool:
        """Whether the platform supports typing indicators."""
        return bool(self._cap("supports_typing", False))

    # ------------------------------------------------------------------ #
    # Default-implemented, capability-driven — override only to improve.  #
    # ------------------------------------------------------------------ #

    def format_message(self, text: str) -> str:
        """Render *text* for the platform's declared ``markdown_dialect``.

        This is the seam that finally *consumes* the ``markdown_dialect``
        capability every adapter advertises: the default keys off
        ``capabilities.markdown_dialect`` and returns text rendered in that
        flavour (e.g. MarkdownV2-escaped for Telegram, Slack ``mrkdwn`` for
        Slack) so replies render correctly and are never dropped by a transport
        that rejects unescaped specials. The default dialect ``"markdown"``
        yields a safe plain-text reduction, so existing adapters are unaffected.

        Adapters that need the transport ``parse_mode`` (e.g. Telegram's
        ``"MarkdownV2"``) can call :func:`~praisonaiagents.bots.format_for_dialect`
        directly in their send path; override this method to change formatting.
        """
        from .format import format_for_dialect

        rendered, _parse_mode = format_for_dialect(
            text, self._cap("markdown_dialect", "markdown")
        )
        return rendered

    def chunk(self, text: str) -> List[str]:
        """Split *text* to respect the platform max length.

        Default uses a paragraph/line-aware splitter. Override to use a
        richer platform-aware chunker (e.g. code-fence preserving).
        """
        return _chunk_text(text, self.max_message_length)

    async def send_typing(self, chat_id: Any) -> None:
        """Send a typing indicator. Default no-op unless capability set."""
        return None

    async def edit_message(
        self,
        chat_id: Any,
        message_id: str,
        content: Union[str, Dict[str, Any]],
    ) -> SendResult:
        """Edit an existing message.

        Default behaviour when the platform does not support edits: report
        ``ok=False`` with a "not supported" error so the caller can re-send.
        Platforms that support edits should override this.
        """
        if not self.supports_edit:
            return SendResult(
                ok=False,
                chat_id=chat_id,
                error="edit_not_supported",
                metadata={"message_id": message_id},
            )
        raise NotImplementedError(
            "capabilities.supports_edit is True but edit_message is not "
            "implemented; override edit_message in the adapter."
        )

    async def delete_message(self, chat_id: Any, message_id: str) -> bool:
        """Delete a message. Default: not supported → returns False."""
        return False

    def classify_error(self, exc: BaseException) -> SendResult:
        """Map a native send exception into a classified :class:`SendResult`.

        This is the seam adapters override to translate their platform SDK's
        exception types and status codes into the shared
        :class:`SendErrorKind` taxonomy with full fidelity — done once at the
        boundary where that information is available, rather than
        reverse-engineered from a string later in the delivery loop.

        The default delegates to the pure, status/text-aware
        :func:`classify_send_error`, so an adapter that does not override still
        behaves correctly for standard HTTP cases and only *provably permanent*
        failures short-circuit the retry loop.
        """
        return classify_send_error(exc)

    async def deliver(
        self,
        chat_id: Any,
        content: Union[str, Dict[str, Any]],
        *,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        typing: bool = True,
    ) -> SendResult:
        """Robustly deliver *content*, inheriting all shared machinery.

        Applies (all capability-gated, via :meth:`send`):
        - per-platform formatting (:meth:`format_message`);
        - long-message chunking (:meth:`chunk`) when *content* is text;
        - typing heartbeat before the first chunk (if supported);
        - retry with exponential backoff honouring ``retry_after``.

        Non-text (dict) content is passed straight through to :meth:`send`
        without chunking/formatting.
        """
        if typing and self.supports_typing:
            try:
                await self.send_typing(chat_id)
            except Exception:
                pass

        if isinstance(content, str):
            formatted = self.format_message(content)
            chunks = self.chunk(formatted)
        else:
            chunks = [content]  # type: ignore[list-item]

        aggregate = SendResult(ok=True, chat_id=chat_id)
        for index, chunk in enumerate(chunks):
            result = await self._send_with_retry(
                chat_id,
                chunk,
                reply_to=reply_to if index == 0 else None,
                metadata=metadata,
            )
            if not result.ok:
                result.message_ids = aggregate.message_ids + result.message_ids
                return result
            if result.message_id:
                aggregate.message_ids.append(result.message_id)
                aggregate.message_id = result.message_id
        aggregate.metadata = {"chunks": len(chunks)}
        return aggregate

    async def _send_with_retry(
        self,
        chat_id: Any,
        content: Union[str, Dict[str, Any]],
        *,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send one chunk with retry/backoff, honouring the error taxonomy.

        Failures are classified once (via :meth:`classify_error` for raised
        exceptions, or read from the ``SendResult`` an adapter returns) into a
        :class:`SendErrorKind`. Only ``retryable`` failures are retried with
        backoff; a provably-permanent failure (forbidden / target-not-found /
        auth-fatal / invalid-request) short-circuits immediately so a blocked
        user or deleted chat no longer burns the full retry budget. The caller
        can act on ``result.error_kind`` (e.g. mark the target dead by kind).
        """
        last: SendResult = SendResult(ok=False, chat_id=chat_id, error="unsent")
        attempts = max(1, int(self.max_retries))
        for attempt in range(attempts):
            try:
                result = await self.send(
                    chat_id, content, reply_to=reply_to, metadata=metadata
                )
            except Exception as exc:  # transport error — classify then decide
                result = self.classify_error(exc)
                result.chat_id = chat_id
            if result.ok:
                return result
            last = result
            # Short-circuit provably-permanent failures: no point backing off
            # and re-sending to a blocked user / deleted chat / bad token.
            if not result.retryable:
                return result
            if attempt < attempts - 1:
                delay = result.retry_after
                if delay is None:
                    delay = self.retry_base_delay * (2 ** attempt)
                if delay and delay > 0:
                    await asyncio.sleep(delay)
        return last
