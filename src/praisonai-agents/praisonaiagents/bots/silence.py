"""
Silence protocol for bot gateways.

Provides a canonical contract for agents to signal intentional silence
(no reply) in group/ambient channels. Zero dependencies.

Also provides :class:`BotLoopGuard`, a pure sliding-window pair-budget guard
that breaks runaway bot-to-bot reply loops (two bots answering each other
forever). Like :func:`praisonaiagents.bots.protocols.evaluate_channel_health`,
it is a dependency-free decision primitive: the wrapper/bot layer feeds it the
pair identities and drops the turn on a ``False`` verdict.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

SILENT_REPLY_TOKEN = "NO_REPLY"

_MARKERS = frozenset({"NO_REPLY", "[SILENT]", "SILENT"})


def is_intentional_silence_response(text: str | None) -> bool:
    """Check if a response is an intentional silence signal.
    
    True only when the reply is *exactly* a silence marker (not prose mentioning it).
    Blank/empty responses are NOT treated as deliberate silence.
    
    Args:
        text: The response text to check
        
    Returns:
        True if the response is exactly a silence token, False otherwise
        
    Examples:
        >>> is_intentional_silence_response("NO_REPLY")
        True
        >>> is_intentional_silence_response("[SILENT]")
        True
        >>> is_intentional_silence_response("I think NO_REPLY is good")
        False
        >>> is_intentional_silence_response("")
        False
        >>> is_intentional_silence_response(None)
        False
    """
    if not text:
        return False  # blank != deliberate silence
    
    normalized = text.strip().upper()
    
    # Check for exact match
    if normalized in _MARKERS:
        return True
    
    # Check for bracket-wrapped version (only for tokens that aren't already bracketed)
    if normalized.startswith("[") and normalized.endswith("]"):
        inner = normalized[1:-1]
        if inner == "SILENT":  # Only [SILENT] is a valid bracketed marker
            return True
    
    return False


@dataclass
class BotLoopPolicy:
    """Sliding-window pair budget for bot-to-bot loop protection.

    A gateway configured to accept bot-authored inbound messages (multi-bot
    rooms, cross-posted assistants, an @-mentioning bot) can ping-pong with
    another bot indefinitely: each reply is a valid admitted turn, so per-user
    serialisation, the admission ceiling and outbound rate limiting never break
    a strictly sequential A->B->A loop. This policy declares a per-pair budget
    that :class:`BotLoopGuard` enforces.

    Attributes:
        enabled: Whether the guard suppresses loops. When ``False`` the guard
            always allows the reply (legacy behaviour).
        max_events_per_window: Maximum number of bot-authored exchanges allowed
            for a single pair within ``window_seconds`` before the pair is put
            on cooldown. Must be >= 1.
        window_seconds: Length of the sliding window in seconds.
        cooldown_seconds: How long a pair stays suppressed once the budget is
            exceeded. During cooldown every reply to that pair is dropped.
    """

    enabled: bool = True
    max_events_per_window: int = 20
    window_seconds: float = 60.0
    cooldown_seconds: float = 60.0

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "BotLoopPolicy":
        """Build a policy from a config mapping (YAML/kwargs), tolerating None.

        Unknown keys are ignored so a forward-compatible config never breaks
        construction. ``None`` yields the enabled default policy.
        """
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", True)),
            max_events_per_window=int(data.get("max_events_per_window", 20)),
            window_seconds=float(data.get("window_seconds", 60.0)),
            cooldown_seconds=float(data.get("cooldown_seconds", 60.0)),
        )


def _pair_key(self_bot_id: str, sender_bot_id: str) -> Tuple[str, str]:
    """Canonical, direction-independent key for a participant pair.

    A<->B and B<->A collapse to one key so the budget counts the *exchange*,
    not each one-way hop, matching how a loop actually accrues.
    """
    a, b = str(self_bot_id), str(sender_bot_id)
    return (a, b) if a <= b else (b, a)


class BotLoopGuard:
    """Pure sliding-window pair-budget guard against bot-to-bot reply loops.

    Tracks each participant pair (our bot identity <-> the other sender's bot
    identity) in both directions. Once a pair exceeds
    ``policy.max_events_per_window`` bot-authored events inside
    ``policy.window_seconds`` it is suppressed for ``policy.cooldown_seconds``.

    Only bot-authored inbound turns should be observed: human-authored
    messages, single-bot deployments and normal below-budget bot replies are
    unaffected, so the guard is zero-cost on the common path (the caller simply
    skips :meth:`observe` when the sender is human).

    Zero dependencies; deterministic under an injected ``now`` for testing —
    exactly like :func:`evaluate_channel_health`.

    Example::

        guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=20))
        if sender_is_bot and not guard.observe(
            self_bot_id="mybot", sender_bot_id="otherbot", now=time.time()
        ):
            return  # drop the turn: record history like an admission drop
    """

    def __init__(self, policy: Optional[BotLoopPolicy] = None) -> None:
        self._policy = policy or BotLoopPolicy()
        # Per-pair event timestamps within the sliding window.
        self._events: Dict[Tuple[str, str], Deque[float]] = {}
        # Per-pair cooldown expiry timestamps.
        self._cooldowns: Dict[Tuple[str, str], float] = {}

    @property
    def enabled(self) -> bool:
        """Whether the guard actively suppresses loops."""
        return self._policy.enabled

    def observe(
        self,
        *,
        self_bot_id: str,
        sender_bot_id: str,
        now: Optional[float] = None,
    ) -> bool:
        """Record a bot-authored exchange and decide whether to allow the reply.

        Args:
            self_bot_id: Our bot's identity on the platform.
            sender_bot_id: The other (bot) sender's identity.
            now: Current timestamp (injectable for testing). Defaults to
                ``time.time()``.

        Returns:
            ``True`` to allow the reply, ``False`` to suppress it (the pair is
            in cooldown or just exceeded its budget). Always ``True`` when the
            policy is disabled.
        """
        if not self._policy.enabled:
            return True
        if now is None:
            now = time.time()

        key = _pair_key(self_bot_id, sender_bot_id)

        # Still cooling down? Suppress without recording, so a persistent
        # flood cannot keep resetting/extending the window mid-cooldown.
        cooldown_until = self._cooldowns.get(key)
        if cooldown_until is not None:
            if now < cooldown_until:
                return False
            # Cooldown elapsed: clear it and start a fresh window below.
            del self._cooldowns[key]
            self._events.pop(key, None)

        window = self._events.setdefault(key, deque())
        window.append(now)

        # Evict events older than the sliding window.
        cutoff = now - self._policy.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) > self._policy.max_events_per_window:
            # Budget exceeded: open a cooldown and suppress this reply.
            self._cooldowns[key] = now + self._policy.cooldown_seconds
            self._events.pop(key, None)
            return False

        return True

    def reset(self) -> None:
        """Clear all tracked pairs and cooldowns (e.g. on gateway restart)."""
        self._events.clear()
        self._cooldowns.clear()