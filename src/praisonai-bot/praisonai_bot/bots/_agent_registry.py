"""Phone-number → agent routing registry (gateway/bot layer).

Issue #2859 asks for the ability to *assign a phone number to an agent* so an
inbound WhatsApp/SMS message can be routed to the agent responsible for that
number. Routing is a **channel/gateway** concern, not a core ``Agent`` identity
attribute — the agent itself never reads its own number. This registry keeps the
mapping where the dispatch happens (the bot layer), mirroring OpenClaw's
"route inbound channels/accounts/peers to isolated agents" model.

Usage::

    from praisonai_bot.bots import AgentRegistry
    from praisonaiagents import Agent

    support = Agent(name="support", instructions="Be helpful")
    sales = Agent(name="sales", instructions="Sell things")

    registry = AgentRegistry()
    registry.assign("+1 (415) 555-0123", support)
    registry.assign("+442071838750", sales)

    # Gateway resolves an inbound number to the right agent:
    agent = registry.resolve("+14155550123")  # -> support

Numbers are normalised to a canonical E.164-ish key (leading ``+`` preserved,
all other non-digits stripped) so cosmetic differences in formatting resolve to
the same agent. Lookups fall back to ``default_agent`` (when provided) and
finally to ``None``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

_NON_DIGITS = re.compile(r"[^0-9]")


def normalize_number(number: Optional[str]) -> Optional[str]:
    """Return a canonical phone-number key, or ``None`` when blank.

    Strips whitespace and formatting characters (spaces, dashes, parens, dots)
    while preserving a single leading ``+``. ``"+1 (415) 555-0123"`` and
    ``"+14155550123"`` both normalise to ``"+14155550123"``.
    """
    if not isinstance(number, str):
        return None
    stripped = number.strip()
    if not stripped:
        return None
    has_plus = stripped.startswith("+")
    digits = _NON_DIGITS.sub("", stripped)
    if not digits:
        return None
    return ("+" + digits) if has_plus else digits


class AgentRegistry:
    """A thread-unsafe, in-memory phone-number → agent routing table.

    Lightweight by design: it holds references to already-constructed agents
    and a normalised-number index. It performs no I/O and adds no dependencies,
    so a gateway can build one per process and consult it on every inbound
    message.

    Args:
        default_agent: Optional fallback returned by :meth:`resolve` when an
            inbound number is unknown. When ``None``, unknown numbers resolve
            to ``None`` and the caller decides how to handle them.
    """

    def __init__(self, default_agent: Optional[Any] = None) -> None:
        self._by_number: Dict[str, Any] = {}
        self._default_agent = default_agent

    def assign(self, number: str, agent: Any) -> str:
        """Assign ``number`` to ``agent`` and return the normalised key.

        Re-assigning a number replaces the previous agent for that number.

        Raises:
            ValueError: if ``number`` normalises to empty (blank/no digits).
        """
        key = normalize_number(number)
        if key is None:
            raise ValueError(f"invalid phone number: {number!r}")
        self._by_number[key] = agent
        return key

    def unassign(self, number: str) -> bool:
        """Remove any agent assigned to ``number``.

        Returns ``True`` if a mapping was removed, ``False`` otherwise.
        """
        key = normalize_number(number)
        if key is None:
            return False
        return self._by_number.pop(key, None) is not None

    def resolve(self, number: Optional[str]) -> Optional[Any]:
        """Return the agent assigned to ``number``.

        Falls back to ``default_agent`` when the number is unknown or blank,
        and to ``None`` when no default is configured.
        """
        key = normalize_number(number)
        if key is not None:
            agent = self._by_number.get(key)
            if agent is not None:
                return agent
        return self._default_agent

    def numbers(self) -> List[str]:
        """Return all assigned (normalised) numbers."""
        return list(self._by_number.keys())

    def __contains__(self, number: object) -> bool:
        if not isinstance(number, str):
            return False
        key = normalize_number(number)
        return key is not None and key in self._by_number

    def __len__(self) -> int:
        return len(self._by_number)

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        return iter(self._by_number.items())


__all__ = ["AgentRegistry", "normalize_number"]
