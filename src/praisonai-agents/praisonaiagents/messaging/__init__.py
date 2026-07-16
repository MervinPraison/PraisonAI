"""
Addressed agent-to-agent messaging for PraisonAI Agents.

Provides a first-class, *addressed* messaging primitive: send a message to a
named recipient agent and receive/subscribe to your inbox. This complements the
existing mechanisms rather than replacing them:

- ``bus`` — type-filtered, in-process pub/sub (no recipient addressing).
- ``kanban`` comments — shared task board (pull-based, task-scoped).
- ``handoff`` — synchronous parent -> child delegation.

Protocol-first (AGENTS.md §3.2): the core SDK ships the ``AgentMailboxProtocol``
contract plus a light in-process default (:class:`InProcessMailbox`). The
wrapper (praisonai) can add a heavy Redis-backed implementation for
cross-process / cross-host fleets under an ``agent:`` namespace.

Zero overhead: nothing is instantiated unless a mailbox is explicitly created.

Usage:
    from praisonaiagents.messaging import InProcessMailbox

    mailbox = InProcessMailbox()
    mailbox.send("writer", {"findings": data}, sender="researcher")
    msgs = mailbox.receive("writer")
"""

__all__ = [
    "AgentMessage",
    "AgentMailboxProtocol",
    "InProcessMailbox",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name in ("AgentMessage", "AgentMailboxProtocol"):
        from . import protocols

        return getattr(protocols, name)

    if name == "InProcessMailbox":
        from .inprocess import InProcessMailbox

        return InProcessMailbox

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
