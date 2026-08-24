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
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class AckScope(str, Enum):
    """Scope gate for ack reactions.

    Controls which inbound messages get an ack reaction so busy groups
    aren't spammed with ⏳ on ambient chatter the bot never answers.

    - ``off``: never ack.
    - ``direct``: ack direct/DM messages only.
    - ``group_mentions``: ack DMs plus group messages that mention/reply the
      bot (default). Ambient group chatter is not acked.
    - ``group_all``: ack DMs plus any non-ambient group message.
    - ``all``: ack every message (legacy all-or-nothing behaviour).
    """
    off = "off"
    direct = "direct"
    group_mentions = "group-mentions"
    group_all = "group-all"
    all = "all"

    @classmethod
    def coerce(cls, value: Any, default: "AckScope") -> "AckScope":
        """Best-effort parse from a string/enum, falling back to ``default``."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower().replace("_", "-")
            for member in cls:
                if member.value == normalized:
                    return member
        return default


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
        scope: Which messages to ack (see :class:`AckScope`). Defaults to
            ``group-mentions`` so ambient group chatter is not acked.
    """

    def __init__(
        self,
        ack_emoji: str = "",
        done_emoji: str = "✅",
        scope: Any = AckScope.group_mentions,
    ) -> None:
        self._ack_emoji = ack_emoji
        self._done_emoji = done_emoji
        self._scope = AckScope.coerce(scope, AckScope.group_mentions)

    @property
    def enabled(self) -> bool:
        return bool(self._ack_emoji) and self._scope is not AckScope.off

    @property
    def scope(self) -> AckScope:
        return self._scope

    def should_ack(
        self, *, is_direct: bool, is_mention: bool, is_ambient: bool
    ) -> bool:
        """Whether a message matching this addressing context should be acked."""
        if not self._ack_emoji or self._scope is AckScope.off:
            return False
        if self._scope is AckScope.all:
            return True
        if self._scope is AckScope.direct:
            return is_direct
        if self._scope is AckScope.group_mentions:
            return is_direct or is_mention
        if self._scope is AckScope.group_all:
            return is_direct or not is_ambient
        return False

    def should_ack_message(self, message: Any, *, is_mention: bool = False) -> bool:
        """Derive addressing context from a ``BotMessage`` and gate the ack.

        Direct-vs-group is read from ``message.channel.channel_type``; a
        mention/reply is either passed explicitly by the adapter or inferred
        from ``message.reply_to``. Ambient == a group message that neither
        mentions nor replies the bot.
        """
        channel = getattr(message, "channel", None)
        channel_type = getattr(channel, "channel_type", "") if channel else ""
        is_direct = str(channel_type).lower() in ("dm", "private", "direct", "")
        mentioned = bool(is_mention) or bool(getattr(message, "reply_to", None))
        is_ambient = not is_direct and not mentioned
        return self.should_ack(
            is_direct=is_direct, is_mention=mentioned, is_ambient=is_ambient
        )

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
