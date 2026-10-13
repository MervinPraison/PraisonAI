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
import inspect
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
            recorded as a pass by the core runtime. Each member is cloned via
            ``clone_for_channel`` so a member shared with another room or
            route never has its history/tools swapped concurrently; members
            that cannot be cloned are left out (they pass) rather than shared.

    Example::

        room = GatewayRoom(
            RoomConfig(name="standup", roster=["researcher", "critic"]),
            {"researcher": researcher, "critic": critic},
        )
        Bot("telegram", agent=room).start()
    """

    def __init__(self, config: RoomConfig, agents: Mapping[str, Any]) -> None:
        self.config = config
        self.agents = {}
        for aid, agent in agents.items():
            member = _private(aid, agent)
            if member is not None:
                self.agents[aid] = member
        self.name = f"{ROOM_ROUTE_PREFIX}{config.name}"
        # Swapped in/out per session by BotSessionManager (durable transcript).
        self.chat_history: List[Dict[str, Any]] = []
        # Speaker ids for non-roster events; never collide with a member id.
        self._human = _outsider("user", config.roster)
        self._system = _outsider("summary", config.roster)
        # Route tool policy narrowing (see ``tools``); ``None`` = unrestricted.
        self._allowed_tools: Optional[set] = None

    # ── route tool policy (BotSessionManager._apply_tool_policy) ────────
    @property
    def tools(self) -> List[Any]:
        """Union of member tools, so a route ``tool_policy`` can scope them."""
        out: List[Any] = []
        for agent in self.agents.values():
            out.extend(getattr(agent, "tools", None) or [])
        if self._allowed_tools is not None:
            out = [t for t in out if id(t) in self._allowed_tools]
        return out

    @tools.setter
    def tools(self, value: List[Any]) -> None:
        # The session assigns the filtered subset for one turn, then restores
        # the full list; a full list clears the restriction.
        allowed = {id(t) for t in value or []}
        everything = {
            id(t) for a in self.agents.values() for t in (getattr(a, "tools", None) or [])
        }
        self._allowed_tools = None if everything <= allowed else allowed

    # ── transcript <-> chat_history ─────────────────────────────────────
    # Members are stored as ``{"role": "assistant", "content": "<id>: <text>"}``
    # because session stores persist only role/content (extra keys are dropped).
    def _to_events(self, history: List[Dict[str, Any]]) -> List[RoomEvent]:
        roster = set(self.config.roster)
        events: List[RoomEvent] = []
        for msg in history or []:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = str(msg.get("content") or "")
            if role == "assistant":
                speaker, sep, text = content.partition(": ")
                if sep and speaker in roster:
                    events.append(RoomEvent(speaker=speaker, content=text))
            elif role == "user":
                events.append(RoomEvent(speaker=self._human, content=content))
            elif role == "system" and content:
                # Compaction summary: context for members, not a human turn
                # (the planner only reacts to the trailing human message).
                events.append(RoomEvent(speaker=self._system, content=content))
        return events

    def _speaker(self, agent_id: str, agent: Any, blocking: bool, opts: Dict[str, Any]):
        cancel_token = opts.get("cancel_token")

        async def reply(transcript: str) -> str:
            if cancel_token is not None and cancel_token.is_set():
                raise InterruptedError(f"room {self.config.name!r} run cancelled")
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
            # Decide narrowing once per turn: the session may restore the full
            # tool list (clearing ``_allowed_tools``) while this call still runs,
            # and the restore below must not depend on that shared state.
            allowed = self._allowed_tools
            saved_tools = getattr(agent, "tools", None)
            narrowed = allowed is not None and bool(saved_tools)
            if narrowed:
                agent.tools = [t for t in saved_tools if id(t) in allowed]
            try:
                if blocking or not hasattr(agent, "achat"):
                    # Sync path: already on an executor thread (see ``chat``),
                    # so call ``agent.chat`` directly rather than binding the
                    # member's async clients to a throwaway event loop.
                    out = agent.chat(prompt, **_supported(agent.chat, opts))
                else:
                    out = await agent.achat(prompt, **_supported(agent.achat, opts))
            finally:
                if saved is not None:
                    agent.chat_history = saved
                if narrowed:
                    agent.tools = saved_tools
            return "" if out is None else str(getattr(out, "output", out))

        return reply

    # ── agent-shaped surface consumed by BotSessionManager ──────────────
    async def achat(
        self,
        prompt: str,
        attachments: Optional[List[str]] = None,
        cancel_token: Any = None,
        **_: Any,
    ) -> str:
        return await self._run(prompt, False, attachments, cancel_token)

    async def _run(
        self, prompt: str, blocking: bool, attachments: Any, cancel_token: Any
    ) -> str:
        opts = {k: v for k, v in (("attachments", attachments), ("cancel_token", cancel_token)) if v}
        room = Room(
            self.config,
            {aid: self._speaker(aid, a, blocking, opts) for aid, a in self.agents.items()},
        )
        room.transcript = self._to_events(self.chat_history)
        turns = await room.on_message(RoomEvent(speaker=self._human, content=prompt))

        spoken = [t for t in turns if t.content and not t.passed]
        history = list(self.chat_history or [])
        history.append({"role": "user", "content": prompt})
        history.extend(
            {"role": "assistant", "content": f"{t.speaker}: {t.content}"} for t in spoken
        )
        self.chat_history = history
        return "\n\n".join(f"**{t.speaker}**: {t.content}" for t in spoken)

    async def astart(self, prompt: str, **kwargs: Any) -> str:
        return await self.achat(prompt, **kwargs)

    def chat(
        self,
        prompt: str,
        attachments: Optional[List[str]] = None,
        cancel_token: Any = None,
        **_: Any,
    ) -> str:
        """Sync entry point (the session runs this in an executor thread)."""
        return asyncio.run(self._run(prompt, True, attachments, cancel_token))

    def start(self, prompt: str, **kwargs: Any) -> str:
        return self.chat(prompt, **kwargs)


def _outsider(base: str, roster: List[str]) -> str:
    """Return ``base`` suffixed until it is not a roster id."""
    while base in roster:
        base += "_"
    return base


def _private(agent_id: str, agent: Any) -> Optional[Any]:
    """Return the room's own member copy, or ``None`` if it cannot be isolated.

    Each turn swaps the member's ``chat_history``/``tools``; doing that on an
    instance shared with other routes or rooms would leak state into them.
    """
    clone = getattr(agent, "clone_for_channel", None)
    if callable(clone):
        try:
            return clone()
        except Exception as e:
            logger.error("Room member %r could not be cloned; it will pass: %s", agent_id, e)
            return None
    logger.error(
        "Room member %r has no clone_for_channel(); it will pass instead of "
        "sharing a mutable instance", agent_id,
    )
    return None


def _supported(fn: Any, opts: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the options ``fn`` accepts (named or via ``**kwargs``)."""
    if not opts:
        return {}
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return dict(opts)
    return {k: v for k, v in opts.items() if k in params}


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
