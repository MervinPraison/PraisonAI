"""Gateway enactment of a core conversation room (Issue #5768).

Core ships the pure turn planner and a storage-agnostic :class:`~praisonaiagents.rooms.Room`.
:class:`GatewayRoom` makes a room usable over a live platform by presenting it
as an *agent-shaped* route target (``chat`` / ``achat`` / ``astart`` +
``chat_history``). That lets it slot in exactly where a single agent is bound
today — ``routes: {group: room:standup}``, ``Bot(agent=room)`` or
``BotOS(agent=room)`` — and reuse the existing session machinery unchanged:

* **Durable transcript** — the room transcript lives in ``chat_history``, which
  :class:`~praisonai_bot.bots._session.BotSessionManager` swaps in per
  user/chat and persists through its configured session store. A restart
  reloads it and the deterministic planner replays the same schedule.
* **Single writer** — the session's per-agent lock serialises turns per room.
* **Delivery** — the combined reply is returned like any agent reply, so it
  flows through the adapter's existing (outbox-backed) delivery path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Mapping, Optional

from praisonaiagents.rooms import Room, RoomConfig, RoomEvent

logger = logging.getLogger(__name__)

ROOM_ROUTE_PREFIX = "room:"


class GatewayRoom:
    """Run a :class:`RoomConfig` roster as a single agent-shaped route target.

    Args:
        config: Room roster + planner caps (``RoomConfig``).
        agents: Mapping of agent id -> Agent. Roster ids missing here are
            recorded as a pass by the core runtime.

    Example::

        room = GatewayRoom(
            RoomConfig(name="standup", roster=["researcher", "critic"]),
            {"researcher": researcher, "critic": critic},
        )
        Bot("telegram", agent=room).start()
    """

    def __init__(self, config: RoomConfig, agents: Mapping[str, Any]) -> None:
        self.config = config
        self.agents = dict(agents)
        self.name = f"{ROOM_ROUTE_PREFIX}{config.name}"
        # Swapped in/out per session by BotSessionManager (durable transcript).
        self.chat_history: List[Dict[str, Any]] = []
        roster = set(config.roster)
        self._human = "user" if "user" not in roster else "human"

    # ── transcript <-> chat_history ─────────────────────────────────────
    def _to_events(self, history: List[Dict[str, Any]]) -> List[RoomEvent]:
        roster = set(self.config.roster)
        events: List[RoomEvent] = []
        for msg in history or []:
            if not isinstance(msg, dict):
                continue
            speaker = msg.get("name")
            if speaker in roster:
                events.append(
                    RoomEvent(
                        speaker=speaker,
                        content=str(msg.get("content") or ""),
                        round=int(msg.get("round", 0) or 0),
                        passed=bool(msg.get("passed", False)),
                    )
                )
            elif msg.get("role") == "user":
                events.append(
                    RoomEvent(speaker=self._human, content=str(msg.get("content") or ""))
                )
        return events

    def _speaker(self, agent_id: str, agent: Any, blocking: bool):
        async def reply(transcript: str) -> str:
            prompt = (
                f"You are @{agent_id} in the multi-agent room "
                f"'{self.config.name}' with {', '.join('@' + a for a in self.config.roster)}. "
                f"Mention @name to hand another participant a turn.\n\n"
                f"Conversation so far:\n{transcript}\n\n@{agent_id}:"
            )
            # The transcript is the context; keep the member's own history from
            # leaking across rooms/sessions by running each turn on a clean slate.
            saved = getattr(agent, "chat_history", None)
            if saved is not None:
                agent.chat_history = []
            try:
                if blocking or not hasattr(agent, "achat"):
                    # Sync path: already on an executor thread (see ``chat``),
                    # so call ``agent.chat`` directly rather than binding the
                    # member's async clients to a throwaway event loop.
                    out = agent.chat(prompt)
                else:
                    out = await agent.achat(prompt)
            finally:
                if saved is not None:
                    agent.chat_history = saved
            return "" if out is None else str(getattr(out, "output", out))

        return reply

    # ── agent-shaped surface consumed by BotSessionManager ──────────────
    async def achat(self, prompt: str, **_: Any) -> str:
        return await self._run(prompt, blocking=False)

    async def _run(self, prompt: str, blocking: bool) -> str:
        room = Room(
            self.config,
            {aid: self._speaker(aid, a, blocking) for aid, a in self.agents.items()},
        )
        room.transcript = self._to_events(self.chat_history)
        turns = await room.on_message(RoomEvent(speaker=self._human, content=prompt))

        history = list(self.chat_history or [])
        history.append({"role": "user", "content": prompt})
        for t in turns:
            history.append(
                {
                    "role": "assistant",
                    "name": t.speaker,
                    "content": t.content,
                    "round": t.round,
                    "passed": t.passed,
                }
            )
        self.chat_history = history
        spoken = [t for t in turns if t.content and not t.passed]
        return "\n\n".join(f"**{t.speaker}**: {t.content}" for t in spoken)

    async def astart(self, prompt: str, **kwargs: Any) -> str:
        return await self.achat(prompt, **kwargs)

    def chat(self, prompt: str, **kwargs: Any) -> str:
        """Sync entry point (the session runs this in an executor thread)."""
        return asyncio.run(self._run(prompt, blocking=True))

    def start(self, prompt: str, **kwargs: Any) -> str:
        return self.chat(prompt, **kwargs)


def build_rooms(
    rooms_cfg: Optional[Mapping[str, Any]], agents: Mapping[str, Any]
) -> Dict[str, GatewayRoom]:
    """Build ``{"room:<name>": GatewayRoom}`` from a parsed ``rooms:`` YAML block."""
    rooms: Dict[str, GatewayRoom] = {}
    for name, data in (rooms_cfg or {}).items():
        config = RoomConfig.from_dict(str(name), data or {})
        missing = [a for a in config.roster if a not in agents]
        if missing:
            logger.warning(
                "Room %r: roster ids %s are not defined under 'agents:' and will pass",
                config.name,
                missing,
            )
        members = {a: agents[a] for a in config.roster if a in agents}
        rooms[f"{ROOM_ROUTE_PREFIX}{config.name}"] = GatewayRoom(config, members)
    return rooms
