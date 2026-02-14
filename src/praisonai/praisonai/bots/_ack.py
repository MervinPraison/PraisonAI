"""
Ack reaction helpers for PraisonAI bots.

Reacts to inbound messages with a configurable emoji (e.g. ⏳) to
acknowledge receipt, then swaps to a "done" emoji (e.g. ✅) when
the agent response is sent.  Inspired by OpenClaw's ack-reactions.ts.

Usage::

    ack = AckReactor(ack_emoji="⏳", done_emoji="✅")
    ctx = await ack.ack(channel_id, message_id, react_fn)
    # ... process message ...
    await ack.done(ctx, channel_id, message_id, react_fn, unreact_fn)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


@dataclass
class AckContext:
    """Tracks state for a single ack-reaction lifecycle."""
    acked: bool = False
    emoji: str = ""


class AckReactor:
    """Lightweight ack-reaction manager.

    Args:
        ack_emoji: Emoji to react with on message receipt (empty = disabled).
        done_emoji: Emoji to react with on completion (default "✅").
    """

    def __init__(self, ack_emoji: str = "", done_emoji: str = "✅") -> None:
        self._ack_emoji = ack_emoji
        self._done_emoji = done_emoji

    @property
    def enabled(self) -> bool:
        return bool(self._ack_emoji)

    async def ack(
        self,
        react_fn: Callable[..., Coroutine],
        **kwargs: Any,
    ) -> AckContext:
        """React with ack emoji.  Returns context for later ``done()``.

        Args:
            react_fn: Platform-specific async function to add a reaction.
                Called as ``await react_fn(emoji=self._ack_emoji, **kwargs)``.
            **kwargs: Extra args forwarded to react_fn (chat_id, message_id, etc).
        """
        ctx = AckContext()
        if not self.enabled:
            return ctx
        try:
            await react_fn(emoji=self._ack_emoji, **kwargs)
            ctx.acked = True
            ctx.emoji = self._ack_emoji
        except Exception as e:
            logger.debug(f"AckReactor: failed to ack: {e}")
        return ctx

    async def done(
        self,
        ctx: AckContext,
        react_fn: Callable[..., Coroutine],
        unreact_fn: Optional[Callable[..., Coroutine]] = None,
        **kwargs: Any,
    ) -> None:
        """Swap ack emoji for done emoji.

        Args:
            ctx: AckContext returned from ``ack()``.
            react_fn: Async function to add a reaction.
            unreact_fn: Async function to remove a reaction (optional).
            **kwargs: Extra args forwarded to react/unreact fns.
        """
        if not ctx.acked:
            return
        # Remove ack emoji
        if unreact_fn:
            try:
                await unreact_fn(emoji=ctx.emoji, **kwargs)
            except Exception as e:
                logger.debug(f"AckReactor: failed to remove ack: {e}")
        # Add done emoji
        if self._done_emoji:
            try:
                await react_fn(emoji=self._done_emoji, **kwargs)
            except Exception as e:
                logger.debug(f"AckReactor: failed to add done: {e}")
