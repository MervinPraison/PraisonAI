"""Pure turn-planner protocol + reference planner for conversation rooms.

Issue #4917. Everything here is pure and dependency-free (stdlib + typing): the
planner takes an immutable ``(roster, transcript)`` snapshot and names the next
agent to speak. Same input -> same output, so a gateway that persists the
transcript can reconstruct the identical schedule after a restart with no
double-execution and no lost turn. The wrapper owns the transcript store,
durable delivery and platform adapters; it merely *enacts* the plan this
module returns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, runtime_checkable

__all__ = [
    "RoomEvent",
    "RoomTurnPlannerProtocol",
    "RoundRobinRoomPlanner",
    "extract_mentions",
]

# ``@name`` addressing. Names are agent ids: letters, digits, underscore, dash
# and dot. A leading ``@`` must not be glued to a preceding word character so
# email-like ``foo@bar`` is not mistaken for a mention.
_MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9][\w\-.]*)")


def extract_mentions(text: str) -> List[str]:
    """Return the ordered, de-duplicated ``@name`` mentions found in ``text``.

    Pure helper shared by planners and (optionally) the wrapper. Case is
    preserved; duplicates are collapsed keeping first-seen order so addressing
    is deterministic.
    """
    if not text:
        return []
    seen: dict = {}
    for match in _MENTION_RE.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen[name] = None
    return list(seen.keys())


@dataclass(frozen=True)
class RoomEvent:
    """One immutable message in a room's shared transcript.

    Attributes:
        speaker: id of who produced the message — an agent id from the roster
            or any non-roster id (e.g. a human participant).
        content: the message text. Used to detect ``@name`` addressing.
        round: the turn-taking round this event belongs to. Round 0 is the
            opening round seeded by the human message; agent replies to the
            opener are round 0, replies admitted by ``@``-mentions are round 1,
            and so on.
        passed: ``True`` when the speaker was scheduled but explicitly passed
            (produced no substantive message). A pass still consumes the turn
            so the planner advances instead of re-scheduling the same agent.
    """

    speaker: str
    content: str = ""
    round: int = 0
    passed: bool = False


@runtime_checkable
class RoomTurnPlannerProtocol(Protocol):
    """Contract for deciding who speaks next in a room.

    Implementations MUST be pure and deterministic: given the same ``roster``
    and ``transcript`` they MUST return the same result, and MUST NOT perform
    I/O. This is what makes a room restart-safe — the gateway persists the
    transcript and replays the planner to rebuild the exact schedule.
    """

    def plan_next(
        self,
        roster: Sequence[str],
        transcript: Sequence[RoomEvent],
    ) -> Optional[str]:
        """Return the id of the next agent to speak, or ``None`` when settled.

        ``None`` means the current activity is complete and the room should
        wait for the next human message.
        """
        ...


@dataclass
class RoundRobinRoomPlanner:
    """Default bounded, deterministic room planner (Issue #4917).

    Turn-taking rules:

    * **Round 0 (opening).** After a human message every rostered agent speaks
      once, in roster order. This is the "everyone on round 0" default.
    * **Later rounds (addressing).** A round *N+1* admits only the agents that
      were ``@``-mentioned by an agent during round *N* — and only agents that
      are actually on the roster. Mentions are honoured in roster order and an
      agent speaks at most once per round.
    * **Bounded.** Hard caps stop a room ever looping unbounded:
        - ``max_rounds`` — no turns are scheduled at or beyond this round.
        - ``max_messages`` — no turns once the transcript reaches this many
          events (human + agent, counting passes).

    Determinism: the plan is a pure function of ``(roster, transcript)``. It
    never reads a clock, RNG or external state, so replaying a persisted
    transcript yields the identical next speaker.
    """

    max_rounds: int = 3
    max_messages: int = 20

    def __post_init__(self) -> None:
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        if self.max_messages < 1:
            raise ValueError("max_messages must be >= 1")

    def plan_next(
        self,
        roster: Sequence[str],
        transcript: Sequence[RoomEvent],
    ) -> Optional[str]:
        roster_list = list(roster)
        if not roster_list:
            return None
        roster_set = set(roster_list)

        # Scope all accounting to the *current activity*: the slice of the
        # transcript from the last human (non-roster) message onward. A durable
        # room transcript accumulates many activities; each new human message
        # opens a fresh round-0 fan-out and resets the message cap, so a settled
        # room reliably restarts when the next human speaks and can never be
        # permanently disabled by lifetime history.
        last_human = -1
        for idx, ev in enumerate(transcript):
            if ev.speaker not in roster_set:
                last_human = idx
        if last_human < 0:
            # A room only starts once a human (non-roster) message has been seen.
            return None
        activity = transcript[last_human:]

        # Message cap (counts every event in the current activity, passes
        # included) — bounds a single human-initiated activity, not lifetime.
        if len(activity) >= self.max_messages:
            return None

        # Determine the round currently being filled: the highest round present
        # in the current activity. New agent turns are always scheduled into
        # that round until it is complete, then the next round opens.
        current_round = max((ev.round for ev in activity), default=0)

        for rnd in range(current_round, self.max_rounds):
            speaker = self._next_in_round(roster_list, roster_set, activity, rnd)
            if speaker is not None:
                return speaker
            # Round ``rnd`` is settled; a later round only exists if it has
            # admitted speakers via @mentions. Keep scanning forward.
        return None

    @staticmethod
    def _next_in_round(
        roster_list: List[str],
        roster_set: set,
        transcript: Sequence[RoomEvent],
        rnd: int,
    ) -> Optional[str]:
        """Return the next roster agent eligible to speak in round ``rnd``.

        Round 0 admits every rostered agent (opening round). Any later round
        admits only agents ``@``-mentioned by an agent during the *previous*
        round. In all rounds an agent speaks at most once, and admitted agents
        are honoured in roster order for determinism.
        """
        spoken = {ev.speaker for ev in transcript if ev.round == rnd}

        if rnd == 0:
            admitted = roster_list
        else:
            admitted = []
            for ev in transcript:
                if ev.round != rnd - 1 or ev.speaker not in roster_set:
                    continue
                for name in extract_mentions(ev.content):
                    if name in roster_set and name not in admitted:
                        admitted.append(name)
            if not admitted:
                return None

        for name in roster_list:
            if name in admitted and name not in spoken:
                return name
        return None
