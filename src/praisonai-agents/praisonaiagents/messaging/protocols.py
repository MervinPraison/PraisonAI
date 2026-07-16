"""
Agent mailbox protocols for PraisonAI Agents.

Defines the contract for *addressed* agent-to-agent messaging: send a message
to a named recipient agent and receive/subscribe to your inbox. This is the
piece the existing primitives lack:

- ``bus/bus.py`` publish/subscribe filters by event *type* and only carries a
  ``source`` origin label (no ``recipient``/``target``).
- ``kanban`` comments are a shared *board* (task-scoped, pull-based), not
  sender -> named-recipient delivery.
- ``handoff`` is a synchronous parent -> child call-and-return.

This follows AGENTS.md §3.2 Protocol-First Design:
- Protocols define WHAT (interface contract)
- Implementations define HOW (concrete behavior)
- Core SDK has the protocol + a light in-process default; the wrapper
  (praisonai) can add a heavy Redis-backed implementation for cross-host
  fleets under an ``agent:`` namespace.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass
class AgentMessage:
    """An addressed message between two agents.

    Attributes:
        sender: Address of the sending agent.
        recipient: Address of the receiving agent.
        body: Arbitrary message payload (str, dict, etc.).
        id: Unique message identifier.
        ts: Unix timestamp when the message was created.
        correlation_id: Optional id to correlate request/response pairs.
    """

    sender: str
    recipient: str
    body: Any
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = field(default_factory=time.time)
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message to a plain dict."""
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "body": self.body,
            "ts": self.ts,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        """Create a message from a plain dict."""
        return cls(
            sender=data["sender"],
            recipient=data["recipient"],
            body=data.get("body"),
            id=data.get("id", str(uuid.uuid4())),
            ts=data.get("ts", time.time()),
            correlation_id=data.get("correlation_id"),
        )


@runtime_checkable
class AgentMailboxProtocol(Protocol):
    """Protocol contract for addressed agent-to-agent mailboxes.

    Implementations route a message from a sender to a *named recipient* and
    let the recipient pull (``receive``) or subscribe (``subscribe``) to its
    inbox. The core SDK ships an in-process default; the wrapper may provide a
    Redis-backed implementation with the same interface for cross-process or
    cross-host fleets.
    """

    def send(
        self,
        recipient: str,
        body: Any,
        *,
        sender: str,
        correlation_id: str | None = None,
    ) -> str:
        """Send a message to a named recipient agent.

        Args:
            recipient: Address of the receiving agent.
            body: Message payload.
            sender: Address of the sending agent.
            correlation_id: Optional id to correlate a reply.

        Returns:
            The id of the delivered message.
        """
        ...

    def receive(self, agent_id: str, *, limit: int = 50) -> list[AgentMessage]:
        """Drain up to ``limit`` pending messages for an agent (oldest first).

        Args:
            agent_id: Address of the receiving agent.
            limit: Maximum number of messages to return.

        Returns:
            List of delivered messages (removed from the inbox).
        """
        ...

    def subscribe(
        self,
        agent_id: str,
        callback: Callable[[AgentMessage], None],
    ) -> None:
        """Register a callback fired when a message is delivered to ``agent_id``.

        Args:
            agent_id: Address of the receiving agent.
            callback: Function invoked with each delivered message.
        """
        ...
