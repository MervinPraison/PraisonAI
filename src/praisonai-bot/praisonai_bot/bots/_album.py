"""
Inbound media-album coalescing for gateway bots (Issue #3298).

When a user sends several photos/files together (a "media album"), chat
platforms deliver them as multiple separate inbound updates in quick
succession, all sharing one group identifier (Telegram's
``media_group_id``). Handled naively, each update becomes its own agent
turn, so the agent never sees the album as one multimodal input.

This module mirrors the proven text-debounce design in
:mod:`._debounce`: it buffers the media parts belonging to the same group
and, after a short window of silence, flushes them once so a single turn
carries every attachment.

Usage::

    coalescer = AlbumCoalescer(window_ms=1200, max_items=10)
    merged = await coalescer.collect(group_key, attachments, caption)
    if merged is None:
        return  # this update's media was buffered into a sibling's turn
    # merged.attachments -> all album parts; merged.caption -> first caption

``group_key`` is ``None`` for a standalone (non-album) message, in which
case ``collect`` returns immediately with just that update's own parts.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from .._lockmap import LockMap

logger = logging.getLogger(__name__)


@dataclass
class MergedAlbum:
    """Result of coalescing an inbound media album into one turn."""

    attachments: List[str]
    caption: str


@dataclass
class _Group:
    attachments: List[str] = field(default_factory=list)
    caption: str = ""
    future: Optional[asyncio.Future] = None
    timer: Optional[asyncio.TimerHandle] = None


class AlbumCoalescer:
    """Per-group inbound media-album coalescer.

    Buffers the media parts of updates sharing a ``group_key`` and flushes
    them as a single :class:`MergedAlbum` after ``window_ms`` of silence,
    or immediately once ``max_items`` parts have accumulated (so a slow
    trickle never stalls the reply). Exactly one caller per group receives
    the merged result; the rest receive ``None`` because their media has
    already been folded into that turn.

    Args:
        window_ms: Debounce window in milliseconds. ``0`` disables
            coalescing (every update returns its own parts immediately).
        max_items: Upper bound on attachments buffered per group; flush is
            forced once reached to bound latency and memory. This is a
            deliberate safety cap: if a single album exceeds ``max_items``,
            it is delivered as more than one merged turn rather than growing
            unbounded. The default (10) covers a full Telegram album, so
            splitting only happens when an operator lowers the cap on purpose.
    """

    def __init__(
        self,
        window_ms: int = 0,
        max_items: int = 10,
        on_orphan: Optional[Callable[[List[str]], None]] = None,
    ) -> None:
        self._window_s = max(0, window_ms) / 1000.0
        self._max_items = max(1, max_items)
        self._groups: Dict[str, _Group] = {}
        self._locks = LockMap()
        # Called with a merged album's attachments when its flushed result is
        # never consumed (the owning turn was cancelled/abandoned) so buffered
        # temp files are cleaned up instead of leaking.
        self._on_orphan = on_orphan

    async def collect(
        self,
        group_key: Optional[str],
        attachments: List[str],
        caption: str = "",
    ) -> Optional[MergedAlbum]:
        """Buffer *attachments* for *group_key* and maybe return the merge.

        Returns a :class:`MergedAlbum` for the single caller that owns the
        flushed turn, ``None`` for sibling updates whose media was folded
        into that turn. A standalone message (``group_key`` falsy) or a
        disabled window returns its own parts immediately.
        """
        if not group_key or self._window_s <= 0:
            return MergedAlbum(attachments=list(attachments), caption=caption)

        lock = self._locks.get(group_key)
        async with lock:
            loop = asyncio.get_running_loop()
            group = self._groups.get(group_key)
            first = group is None
            if first:
                group = _Group(future=loop.create_future())
                self._groups[group_key] = group

            group.attachments.extend(attachments)
            # Keep the first non-empty caption as the album's prompt.
            if caption and not group.caption:
                group.caption = caption

            if group.timer is not None:
                group.timer.cancel()

            # Force an immediate flush once the group is full, otherwise
            # (re)arm the silence window.
            if len(group.attachments) >= self._max_items:
                self._flush(group_key)
            else:
                group.timer = loop.call_later(
                    self._window_s, self._flush, group_key
                )

            owner_future = group.future if first else None

        if owner_future is None:
            # A sibling update: its media is buffered into the owner's turn.
            return None
        # If the owning update is cancelled while awaiting, the future is
        # cancelled too; a subsequent flush / ``cancel_all`` then sees a
        # ``done()`` future and reclaims the buffered temp files via the
        # orphan hook (see ``_flush``), so the album is never leaked.
        return await owner_future

    def _reclaim(self, attachments: List[str]) -> None:
        """Hand orphaned album temp files to the cleanup hook, if any."""
        if not attachments or self._on_orphan is None:
            return
        try:
            self._on_orphan(list(attachments))
        except Exception:  # pragma: no cover - cleanup must never raise
            logger.debug("album orphan cleanup failed", exc_info=True)

    def _flush(self, group_key: str) -> None:
        """Resolve the owning future with the merged album for *group_key*."""
        group = self._groups.pop(group_key, None)
        if group is None:
            return
        if group.timer is not None:
            group.timer.cancel()
        merged = MergedAlbum(
            attachments=group.attachments, caption=group.caption
        )
        if group.future is not None and not group.future.done():
            group.future.set_result(merged)
        else:
            # No live owner is awaiting this album (its update was already
            # cancelled/abandoned), so its buffered temp files would leak —
            # reclaim them via the cleanup hook.
            self._reclaim(merged.attachments)

    @property
    def pending_count(self) -> int:
        """Number of groups with buffered, not-yet-flushed media."""
        return len(self._groups)

    def cancel_all(self) -> int:
        """Flush all pending groups (used on shutdown). Returns count."""
        count = 0
        for group_key in list(self._groups.keys()):
            self._flush(group_key)
            count += 1
        return count


def resolve_album_window_ms(config) -> int:
    """Resolve the album coalescing window (ms) from a runtime bot config.

    The core ``BotConfig`` has no album fields, so the operator value is
    carried through ``config.metadata["media_group_window_ms"]`` (mirroring
    ``resolve_max_inbound_media_bytes``). Falls back to a direct attribute,
    then ``0`` (disabled) so behaviour is unchanged unless opted in.
    """
    return _resolve_int(config, "media_group_window_ms", default=0)


def resolve_album_max_items(config) -> int:
    """Resolve the max attachments buffered per album from a bot config.

    Read from ``config.metadata["media_group_max"]`` (or a direct
    attribute), defaulting to 10 — enough for a full Telegram album while
    bounding latency/memory.
    """
    return _resolve_int(config, "media_group_max", default=10)


def _resolve_int(config, key: str, default: int) -> int:
    metadata = getattr(config, "metadata", None)
    if isinstance(metadata, dict) and key in metadata:
        try:
            return int(metadata[key])
        except (TypeError, ValueError):
            pass
    value = getattr(config, key, None)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
