"""
Deterministic session resume helper for the PraisonAI CLI.

Provides a single, shared entry point (`rehydrate_session`) used by both the
Typer (`praisonai run`, `praisonai session resume`) and legacy entry points so
that resuming a session restores the exact prior conversational state:
messages, the persisted model/provider, and the selected agent.

The conversation substrate already lives in the core session store
(`praisonaiagents.session.store.DefaultSessionStore`). This wrapper module only
adds CLI wiring + command parity; it does not duplicate persistence logic.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RehydratedSession:
    """Fully rehydrated session state for a deterministic CLI resume.

    Attributes:
        session_id: The resolved session ID that was restored.
        chat_history: Prior conversation as ``[{"role", "content"}, ...]``.
        model: Persisted model/provider used for the session, if known.
        agent_name: Persisted agent name for the session, if known.
        metadata: Any additional persisted metadata (tokens, cost, source...).
        usage: Cumulative token/cost totals restored from metadata so resume
            continues accumulating instead of resetting (Issue #2421).
        found: Whether a stored session was actually located.
    """

    session_id: str
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    model: Optional[str] = None
    agent_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    found: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "chat_history": self.chat_history,
            "model": self.model,
            "agent_name": self.agent_name,
            "metadata": self.metadata,
            "usage": self.usage,
            "found": self.found,
        }


def _candidate_stores(project_path: Optional[str] = None):
    """Yield session stores to search, project-scoped first then global.

    Resume must work regardless of whether the session was created via the
    project-scoped ``run --continue`` path or the global session store.
    """
    stores = []
    try:
        from ..state.project_sessions import get_project_session_store

        stores.append(get_project_session_store(project_path))
    except Exception:
        pass

    try:
        from praisonaiagents.session.store import get_default_session_store

        stores.append(get_default_session_store())
    except Exception:
        pass

    return stores


def rehydrate_session(
    session_id: str,
    project_path: Optional[str] = None,
) -> RehydratedSession:
    """Rehydrate full conversational state for a session id.

    Searches the project-scoped store first, then the global default store, so
    the same helper serves ``run --continue/--session`` and
    ``session resume <id>`` with identical semantics.

    Args:
        session_id: The session ID to restore.
        project_path: Optional project root (defaults to cwd).

    Returns:
        A :class:`RehydratedSession`. ``found`` is ``False`` when no stored
        session matched (callers should treat that as "start fresh").
    """
    for store in _candidate_stores(project_path):
        try:
            if not store.session_exists(session_id):
                continue
        except Exception:
            continue

        try:
            data = store.get_session(session_id)
        except Exception:
            continue

        chat_history = data.get_chat_history() if data else []
        metadata = dict(getattr(data, "metadata", {}) or {})
        model = metadata.get("model") or metadata.get("llm")
        agent_name = getattr(data, "agent_name", None) or metadata.get("agent_name")

        # Resolve usage through the same store-preference order used when
        # accumulating (prefer the store whose record already carries usage), so
        # a resumed globally-stored session restores the real cumulative totals
        # instead of a project shadow record's empty/stale usage (Issue #2421).
        usage: Dict[str, Any] = {}
        try:
            from ..state.project_sessions import read_session_usage

            resolved = read_session_usage(session_id, project_path)
            if isinstance(resolved, dict) and (
                resolved.get("total_tokens") or resolved.get("cost")
            ):
                usage = resolved
        except Exception:
            usage = {}

        if not usage:
            stored = metadata.get("usage")
            if isinstance(stored, dict):
                usage = dict(stored)
            else:
                if isinstance(metadata.get("total_tokens"), (int, float)):
                    usage["total_tokens"] = metadata["total_tokens"]
                if isinstance(metadata.get("cost"), (int, float)):
                    usage["cost"] = metadata["cost"]

        return RehydratedSession(
            session_id=session_id,
            chat_history=chat_history,
            model=model,
            agent_name=agent_name,
            metadata=metadata,
            usage=usage,
            found=True,
        )

    return RehydratedSession(session_id=session_id, found=False)
