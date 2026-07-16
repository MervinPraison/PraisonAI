"""
In-process default implementation of the agent mailbox protocol.

Single process, multiple agents. Reuses the existing ``EventBus`` for optional
push notifications and keeps a per-recipient inbox for pull-based ``receive``.
Thread-safe and dependency-free, so it works with zero external deps.

For cross-process / cross-host fleets, the wrapper (praisonai) can provide a
Redis-backed implementation of ``AgentMailboxProtocol`` with the same API.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Any, Callable, Deque, Dict, List, Optional

from .protocols import AgentMessage


class InProcessMailbox:
    """Addressed, in-process mailbox for agent-to-agent messaging.

    Implements :class:`AgentMailboxProtocol`. Each recipient has its own inbox
    (a bounded deque). ``send`` enqueues to the recipient's inbox and fires any
    registered subscriber callbacks; ``receive`` drains the inbox.
    """

    def __init__(self, *, max_inbox: int = 1000) -> None:
        """Initialize the mailbox.

        Args:
            max_inbox: Maximum queued messages per recipient (oldest dropped).
        """
        self._max_inbox = max_inbox
        self._inboxes: Dict[str, Deque[AgentMessage]] = defaultdict(
            lambda: deque(maxlen=max_inbox)
        )
        self._subscribers: Dict[str, List[Callable[[AgentMessage], None]]] = defaultdict(list)
        self._lock = threading.RLock()

    def send(
        self,
        recipient: str,
        body: Any,
        *,
        sender: str,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Send a message to a named recipient agent.

        Returns:
            The id of the delivered message.
        """
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            body=body,
            correlation_id=correlation_id,
        )
        with self._lock:
            self._inboxes[recipient].append(message)
            callbacks = list(self._subscribers.get(recipient, ()))

        # Fire subscriber callbacks outside the lock to avoid re-entrancy issues.
        for callback in callbacks:
            try:
                callback(message)
            except Exception:  # pragma: no cover - defensive; one bad sub shouldn't break delivery
                import logging

                logging.getLogger(__name__).exception(
                    "Error in mailbox subscriber for %s", recipient
                )
        return message.id

    def receive(self, agent_id: str, *, max: int = 50) -> List[AgentMessage]:
        """Drain up to ``max`` pending messages for an agent (oldest first)."""
        with self._lock:
            inbox = self._inboxes.get(agent_id)
            if not inbox:
                return []
            count = min(max, len(inbox))
            return [inbox.popleft() for _ in range(count)]

    def subscribe(
        self,
        agent_id: str,
        callback: Callable[[AgentMessage], None],
    ) -> None:
        """Register a callback fired when a message is delivered to ``agent_id``."""
        with self._lock:
            self._subscribers[agent_id].append(callback)

    def pending(self, agent_id: str) -> int:
        """Return the number of undelivered messages for an agent."""
        with self._lock:
            inbox = self._inboxes.get(agent_id)
            return len(inbox) if inbox else 0
