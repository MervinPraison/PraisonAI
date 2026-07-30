"""
Agent Adapter

Publishes PraisonAI :class:`~praisonaiagents.Agent` instances as MCP tools so
any MCP client (Claude, Cursor, ChatGPT, …) can converse with *your* agents —
server-side agents only. The client chooses *which* agent to call, never its
instructions or persona.

Published tools:
  - ``ask_{agent_name}(message, session_id?, user_id?)`` — one per agent.
  - ``list_agents()`` — discovery (names + descriptions).

Session semantics: the client carries an opaque ``session_id``. When omitted a
fresh id is minted per call (never a shared sticky session — that leaks history
across clients). Per-session conversation history is kept in-adapter and applied
to the agent for the turn, then the new turns are persisted back.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TOOL_NAME_SANITIZE = re.compile(r"[^a-zA-Z0-9_]")


def _safe_tool_name(name: str) -> str:
    """Turn an arbitrary agent name into a valid MCP tool suffix."""
    cleaned = _TOOL_NAME_SANITIZE.sub("_", (name or "agent").strip())
    cleaned = cleaned.strip("_") or "agent"
    return cleaned.lower()


class _SessionStore:
    """Thread-safe in-memory transcript store keyed by session id.

    Exposes a per-session lock so a single ``load → run → save`` turn is
    serialized against concurrent turns for the *same* session (otherwise two
    overlapping calls both read the same transcript and the later save discards
    the other's completed turn). Turns for *different* sessions never contend.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}
        self._session_locks: Dict[str, threading.Lock] = {}

    def lock_for(self, session_id: str) -> threading.Lock:
        with self._lock:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._session_locks[session_id] = lock
            return lock

    def load(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def save(self, session_id: str, history: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._sessions[session_id] = list(history)

    def list_sessions(self) -> List[str]:
        with self._lock:
            return list(self._sessions.keys())


def register_agents(server: Any, agents: List[Any]) -> None:
    """Register ``agents`` as MCP tools on ``server``'s tool registry.

    Args:
        server: an :class:`MCPServer` (uses its ``_tool_registry``) or any
            object exposing a ``register`` compatible tool registry.
        agents: list of PraisonAI ``Agent`` instances (or objects exposing
            ``chat``/``achat`` plus a ``name``).
    """
    registry = getattr(server, "_tool_registry", server)
    store = _SessionStore()

    catalog: List[Dict[str, str]] = []
    used_suffixes: Dict[str, int] = {}

    for agent in agents:
        raw_name = getattr(agent, "name", None) or "agent"
        suffix = _safe_tool_name(raw_name)
        # Disambiguate distinct agents whose names normalize to the same suffix
        # (e.g. "Support", "support", "sup-port", or two unnamed agents) so a
        # later registration never silently shadows an earlier agent's tool.
        seen = used_suffixes.get(suffix, 0)
        used_suffixes[suffix] = seen + 1
        if seen:
            suffix = f"{suffix}_{seen + 1}"
        tool_name = f"ask_{suffix}"
        description = (
            getattr(agent, "role", None)
            or getattr(agent, "instructions", None)
            or f"Ask the {raw_name} agent."
        )
        if isinstance(description, str) and "\n" in description:
            description = description.split("\n")[0]
        catalog.append({"name": raw_name, "description": str(description)})

        registry.register(
            name=tool_name,
            handler=_make_ask_handler(agent, store, tool_name),
            description=f"Ask the {raw_name} agent.",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message for the agent."},
                    "session_id": {
                        "type": "string",
                        "description": "Opaque session id for conversation continuity. Omit to start a new session.",
                    },
                    "user_id": {"type": "string", "description": "Optional caller id."},
                },
                "required": ["message"],
            },
        )
        logger.debug("Registered agent tool: %s", tool_name)

    def list_agents() -> Dict[str, Any]:
        """List the agents available on this MCP server."""
        return {"agents": catalog}

    registry.register(
        name="list_agents",
        handler=list_agents,
        description="List the agents available on this MCP server.",
        input_schema={"type": "object", "properties": {}},
    )
    logger.info("Registered %d agent(s) as MCP tools", len(agents))


def _make_ask_handler(agent: Any, store: _SessionStore, tool_name: str):
    async def ask(
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Mint a fresh id when omitted — never fall back to a shared session.
        sid = session_id or uuid.uuid4().hex
        # Namespace the transcript by tool so reusing the *same* client-supplied
        # session_id across different ask_* agents never mixes their histories.
        store_key = f"{tool_name}:{sid}"

        # Serialize the load → run → save turn for this session so overlapping
        # calls can't both read the same transcript and clobber each other.
        turn_lock = store.lock_for(store_key)
        turn_lock.acquire()
        try:
            history = store.load(store_key)

            # Isolate per-call so concurrent sessions never share mutable state.
            turn_agent = _isolated_agent(agent)
            try:
                turn_agent.chat_history = list(history)
            except Exception:
                pass

            text = await _run_turn(turn_agent, message)

            new_history = list(history)
            new_history.append({"role": "user", "content": message})
            new_history.append({"role": "assistant", "content": text})
            store.save(store_key, new_history)
        finally:
            turn_lock.release()

        return {
            "text": text,
            "structuredContent": {"session_id": sid, "status": "ok"},
        }

    return ask


def _isolated_agent(agent: Any) -> Any:
    """Best-effort shallow copy so per-session state is not shared."""
    try:
        clone = copy.copy(agent)
        clone.chat_history = []
        return clone
    except Exception:
        return agent


async def _run_turn(agent: Any, message: str) -> str:
    """Run one turn, preferring the async path, and coerce the result to text."""
    achat = getattr(agent, "achat", None)
    if achat is not None:
        result = await achat(message)
    else:
        chat = getattr(agent, "chat", None) or getattr(agent, "start", None)
        if chat is None:
            raise ValueError("Agent does not expose chat/achat/start")
        result = chat(message)
    return result if isinstance(result, str) else str(result)
