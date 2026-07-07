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
from typing import Any, Dict, List, Optional, Union

from .protocols import PlatformCapabilities

__all__ = [
    "SendResult",
    "BasePlatformAdapter",
]


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
        retry_after: Suggested seconds to wait before retrying (from the
            platform's rate-limit response, if provided).
        metadata: Additional platform-specific result details.
    """

    ok: bool = True
    message_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None
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
            "retry_after": self.retry_after,
            "metadata": self.metadata,
        }


def _chunk_text(text: str, max_length: int) -> List[str]:
    """Split *text* into chunks of at most *max_length* characters.

    Prefers paragraph then line then hard-split boundaries. Pure and
    dependency-free; a subclass can override :meth:`BasePlatformAdapter.chunk`
    to use a richer platform-aware splitter.
    """
    if max_length <= 0 or len(text) <= max_length:
        return [text] if text else [""]

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
    return chunks if chunks else [""]


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
        """Apply per-platform formatting. Default: identity."""
        return text

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
        """Send one chunk with retry/backoff honouring ``retry_after``."""
        last: SendResult = SendResult(ok=False, chat_id=chat_id, error="unsent")
        attempts = max(1, int(self.max_retries))
        for attempt in range(attempts):
            try:
                result = await self.send(
                    chat_id, content, reply_to=reply_to, metadata=metadata
                )
            except Exception as exc:  # transport error — retry
                result = SendResult(ok=False, chat_id=chat_id, error=str(exc))
            if result.ok:
                return result
            last = result
            if attempt < attempts - 1:
                delay = result.retry_after
                if delay is None:
                    delay = self.retry_base_delay * (2 ** attempt)
                if delay and delay > 0:
                    await asyncio.sleep(delay)
        return last
