"""Conversation-room turn coordination for multi-agent chats (Issue #4917).

PraisonAI's gateway binds a single ``Agent`` per conversation. A *room* is the
live, message-driven counterpart of :class:`~praisonaiagents.agents.agents.AgentTeam`:
a declared roster of agents that take turns in one shared chat transcript.

Coordinating turn order over a shared, restart-safe transcript is
infrastructure, not a prompt. The only part of that infrastructure that must be
**pure and deterministic** — so a gateway restart reconstructs the exact same
schedule from durable state — is the *turn planner*. That contract belongs in
core (mirroring ``gateway.plan_pressure_evictions`` and the ``workflows``
process planners); the heavy transcript store, durable outbox and platform
delivery live in the ``praisonai-bot`` wrapper.

This module is intentionally lightweight: **no heavy imports, no I/O**. It
contains a protocol, a minimal event/roster model and a reference planner:

* :class:`RoomEvent` — one immutable message in the shared transcript.
* :class:`RoomTurnPlannerProtocol` — ``plan_next(roster, transcript) -> str|None``.
* :func:`extract_mentions` — parse ``@name`` addressing between participants.
* :class:`RoundRobinRoomPlanner` — the default bounded, deterministic planner:
  round 0 lets every rostered agent speak once; later rounds admit **only**
  agents an earlier agent ``@``-mentioned, with hard caps on rounds/messages so
  a room can never loop unbounded.
"""

from .protocols import (
    RoomEvent,
    RoomTurnPlannerProtocol,
    RoundRobinRoomPlanner,
    extract_mentions,
)

__all__ = [
    "RoomEvent",
    "RoomTurnPlannerProtocol",
    "RoundRobinRoomPlanner",
    "extract_mentions",
]
