"""Room config + a minimal, storage-agnostic runtime that *enacts* the planner.

Issue #5067. The pure turn planner (:mod:`praisonaiagents.rooms.protocols`)
decides *who* speaks next; it was previously orphaned — nothing consumed it. A
room needs one more thing to be usable end-to-end: something that appends each
message to a transcript and drains :meth:`RoomTurnPlannerProtocol.plan_next`,
running the scheduled agent each turn.

This module supplies that piece while staying faithful to the package's
"no heavy imports, no I/O" contract: the transcript is an in-memory list and the
agents are injected as a mapping of ``id -> async callable``. The *durable*
transcript store, platform delivery and CLI/YAML surface remain a wrapper
(``praisonai-bot``) concern; the wrapper can subclass or wrap :class:`Room`,
persist :attr:`Room.transcript`, and replay it after a restart — determinism of
the planner guarantees the identical schedule resumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

from .protocols import RoomEvent, RoomTurnPlannerProtocol, RoundRobinRoomPlanner

__all__ = ["RoomConfig", "Room"]


# An agent turn: given the rendered transcript, produce this speaker's reply.
AgentReply = Callable[[str], Awaitable[str]]


@dataclass
class RoomConfig:
    """Declarative description of a conversation room (roster + planner caps).

    A room is the live, message-driven counterpart of ``AgentTeam``: a named
    roster of agent ids that take bounded, ``@``-addressed turns in one shared
    transcript. This is the small, pure config the wrapper binds to a
    channel/thread exactly where a single ``agent`` is bound today; the planner
    itself already exists in :mod:`praisonaiagents.rooms.protocols`.

    Attributes:
        name: Room identifier (used when binding to a channel, e.g. ``room:standup``).
        roster: Ordered agent ids that take turns.
        planner: Planner selector; ``"round_robin"`` -> :class:`RoundRobinRoomPlanner`.
        max_rounds: Hard cap on turn-taking rounds (passed to the planner).
        max_messages: Hard cap on messages per human-initiated activity.
    """

    name: str
    roster: List[str] = field(default_factory=list)
    planner: str = "round_robin"
    max_rounds: int = 3
    max_messages: int = 20

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RoomConfig.name must be a non-empty string")
        if self.planner != "round_robin":
            raise ValueError(
                f"Unknown room planner {self.planner!r}; expected 'round_robin'"
            )
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        if self.max_messages < 1:
            raise ValueError("max_messages must be >= 1")

    def build_planner(self) -> RoomTurnPlannerProtocol:
        """Construct the planner this config selects."""
        return RoundRobinRoomPlanner(
            max_rounds=self.max_rounds, max_messages=self.max_messages
        )

    def to_dict(self) -> Dict[str, object]:
        """Convert to a plain dict (for YAML round-tripping / diagnostics)."""
        return {
            "name": self.name,
            "roster": list(self.roster),
            "planner": self.planner,
            "max_rounds": self.max_rounds,
            "max_messages": self.max_messages,
        }

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, object]) -> "RoomConfig":
        """Create from a parsed ``rooms.<name>`` YAML mapping.

        Accepts either ``roster:`` or the issue's ``agents:`` key for the list of
        agent ids so the declarative surface reads naturally.
        """
        data = data or {}
        roster = data.get("roster")
        if roster is None:
            roster = data.get("agents", [])
        return cls(
            name=name,
            roster=[str(a) for a in (roster or [])],
            planner=str(data.get("planner", "round_robin")),
            max_rounds=int(data.get("max_rounds", 3)),
            max_messages=int(data.get("max_messages", 20)),
        )


class Room:
    """Minimal storage-agnostic runtime that enacts the turn planner.

    :class:`Room` owns the (in-memory) transcript and drains the planner: after
    each incoming :class:`RoomEvent` it repeatedly asks the planner for the next
    speaker and runs that agent, appending the reply, until the planner settles.
    It performs no I/O and holds no durable state — the wrapper supplies durable
    persistence/delivery by subclassing or wrapping this and persisting
    :attr:`transcript`. Because the planner is pure, replaying a persisted
    transcript resumes the identical schedule.

    Args:
        config: The room's roster + planner caps.
        agents: Mapping of agent id -> async callable ``reply(prompt) -> str``.
            Typically wraps ``Agent.achat``. Only ids in ``config.roster`` are
            scheduled; unknown roster ids are skipped (treated as a pass).
        planner: Optional planner override (defaults to ``config.build_planner()``).
        render: Optional transcript renderer -> the prompt handed to each agent.
    """

    def __init__(
        self,
        config: RoomConfig,
        agents: Dict[str, AgentReply],
        planner: Optional[RoomTurnPlannerProtocol] = None,
        render: Optional[Callable[[List[RoomEvent]], str]] = None,
    ) -> None:
        self.config = config
        self.agents = agents
        self.planner = planner or config.build_planner()
        self._render = render or self._default_render
        self.transcript: List[RoomEvent] = []

    @staticmethod
    def _default_render(transcript: List[RoomEvent]) -> str:
        """Render the transcript as ``speaker: content`` lines."""
        return "\n".join(
            f"{ev.speaker}: {ev.content}" for ev in transcript if ev.content
        )

    def _scheduled_round(self, speaker: str) -> int:
        """Round the planner scheduled ``speaker`` into for the current activity.

        Mirrors :class:`RoundRobinRoomPlanner`: round 0 admits every rostered
        agent; a later round admits only agents ``@``-mentioned during the
        previous round. The scheduled round is the smallest round at/after the
        activity's current round where ``speaker`` is admitted and has not yet
        spoken — the same round the planner is filling when it returns them.
        """
        from .protocols import extract_mentions

        roster_set = set(self.config.roster)
        last_human = -1
        for idx, ev in enumerate(self.transcript):
            if ev.speaker not in roster_set:
                last_human = idx
        activity = self.transcript[last_human:] if last_human >= 0 else []
        current_round = max((ev.round for ev in activity), default=0)

        for rnd in range(current_round, self.config.max_rounds):
            spoken = {ev.speaker for ev in activity if ev.round == rnd}
            if rnd == 0:
                admitted = set(roster_set)
            else:
                admitted = set()
                for ev in activity:
                    if ev.round != rnd - 1 or ev.speaker not in roster_set:
                        continue
                    for name in extract_mentions(ev.content):
                        if name in roster_set:
                            admitted.add(name)
            if speaker in admitted and speaker not in spoken:
                return rnd
        return current_round

    async def on_message(self, event: RoomEvent) -> List[RoomEvent]:
        """Append ``event`` then drain the plan, returning the agent replies.

        Each new human (non-roster) message opens a fresh round-0 activity; the
        planner scopes its accounting to messages since that last human turn, so
        a settled room reliably restarts when the next human speaks.
        """
        self.transcript.append(event)
        produced: List[RoomEvent] = []
        while True:
            nxt = self.planner.plan_next(self.config.roster, self.transcript)
            if nxt is None:
                break
            rnd = self._scheduled_round(nxt)
            reply = self.agents.get(nxt)
            if reply is None:
                # Unknown roster id: record a pass so the planner advances
                # instead of re-scheduling the same missing agent forever.
                turn = RoomEvent(speaker=nxt, content="", round=rnd, passed=True)
            else:
                content = await reply(self._render(self.transcript))
                turn = RoomEvent(speaker=nxt, content=content or "", round=rnd)
            self.transcript.append(turn)
            produced.append(turn)
        return produced
