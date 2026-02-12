"""
Per-user session isolation for PraisonAI bots.

Bots share a single Agent instance but each user needs independent
chat history.  BotSessionManager swaps the agent's ``chat_history``
before and after every call so conversations never leak between users.

Thread-safety: an ``asyncio.Lock`` per user serialises concurrent
calls from the same user; different users run in parallel.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

logger = logging.getLogger(__name__)


class BotSessionManager:
    """Lightweight per-user session store for bot agents.

    Usage inside a bot message handler::

        session_mgr = BotSessionManager()
        response = await session_mgr.chat(agent, user_id, text)

    The manager:
    1. Saves the agent's current ``chat_history``.
    2. Loads the user's history (or ``[]`` for a new user).
    3. Calls ``agent.chat(prompt)`` (via ``run_in_executor``).
    4. Saves the updated history back to the user store.
    5. Restores the agent's original history.

    ``/new`` command → call ``session_mgr.reset(user_id)``.
    """

    def __init__(self, max_history: int = 100) -> None:
        self._histories: Dict[str, List[Dict[str, Any]]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._max_history = max_history

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for *user_id*."""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    async def chat(
        self,
        agent: "Agent",
        user_id: str,
        prompt: str,
    ) -> str:
        """Run ``agent.chat(prompt)`` with *user_id*-scoped history.

        The call is wrapped in ``run_in_executor`` so the sync LLM
        round-trip never blocks the event loop.
        """
        lock = self._get_lock(user_id)
        async with lock:
            # Swap histories
            saved_history = agent.chat_history
            agent.chat_history = list(self._histories.get(user_id, []))

            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, agent.chat, prompt)
            finally:
                # Persist user history and restore agent's original
                user_history = agent.chat_history
                if self._max_history > 0 and len(user_history) > self._max_history:
                    user_history = user_history[-self._max_history:]
                self._histories[user_id] = user_history
                agent.chat_history = saved_history

            return response

    def reset(self, user_id: str) -> bool:
        """Clear a user's session history.  Returns True if it existed."""
        existed = user_id in self._histories
        self._histories.pop(user_id, None)
        return existed

    def reset_all(self) -> int:
        """Clear all user sessions.  Returns the count cleared."""
        count = len(self._histories)
        self._histories.clear()
        return count

    @property
    def active_sessions(self) -> int:
        """Number of users with stored history."""
        return len(self._histories)

    def get_user_ids(self) -> List[str]:
        """List user IDs with active sessions."""
        return list(self._histories.keys())
