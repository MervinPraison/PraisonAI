"""
Single session resolver for the PraisonAI CLI (Issue #3133).

Every ``session`` sub-command and every ``run`` continuation flag must resolve
the *same* session by the same id. Historically ``list``/``resume``/``--continue``
read the project-scoped + global ``DefaultSessionStore`` (JSON message files),
while ``show``/``delete``/``export`` read a second, independent ``SessionManager``
(dir-per-session), so an id resumable via one path was invisible to the other.

This module funnels ``show``/``delete``/``export`` through the *same* stores
that ``list``/``resume`` already use, so id → session is unambiguous. A
best-effort fallback to the legacy ``SessionManager`` store is kept during a
deprecation window so pre-existing ``SessionManager`` sessions remain
manageable.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResolvedSession:
    """A coherent view of a CLI session resolved from the canonical store.

    Attributes:
        session_id: The resolved session id.
        agent_name: Persisted agent name, if known.
        model: Persisted model/provider, if known.
        chat_history: Prior conversation as ``[{"role", "content"}, ...]``.
        metadata: Additional persisted metadata.
        message_count: Number of stored messages.
        created_at / updated_at: ISO timestamps, if known.
        found: Whether a stored session was actually located.
    """

    session_id: str
    agent_name: Optional[str] = None
    model: Optional[str] = None
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    found: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "model": self.model,
            "chat_history": self.chat_history,
            "metadata": self.metadata,
            "message_count": self.message_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "found": self.found,
        }


def _canonical_stores(project_path: Optional[str] = None):
    """Yield the canonical CLI session stores, project-scoped first then global.

    Delegates to the single source of truth in ``project_sessions`` so that
    ``show``/``delete``/``export`` address the *exact same* stores, in the same
    order, that ``list``/``resume``/``--continue`` use — by construction, not
    by two hand-kept copies of the list (Issue #3201, extends #3133).
    """
    try:
        from .project_sessions import canonical_cli_stores

        return canonical_cli_stores(project_path)
    except Exception:
        return []


def _store_for(session_id: str, project_path: Optional[str] = None):
    """Return the first canonical store that holds ``session_id`` (or None)."""
    for store in _canonical_stores(project_path):
        try:
            if store.session_exists(session_id):
                return store
        except Exception:
            continue
    return None


def resolve_session(
    session_id: str,
    project_path: Optional[str] = None,
) -> ResolvedSession:
    """Resolve a session id to a coherent view from the canonical CLI store.

    Searches the project-scoped store then the global default store — the same
    stores ``list``/``resume``/``--continue`` use — then falls back to the
    legacy ``SessionManager`` store so pre-existing sessions stay manageable.

    Returns a :class:`ResolvedSession`; ``found`` is ``False`` when no store
    holds the id.
    """
    store = _store_for(session_id, project_path)
    if store is not None:
        # The id lives in a canonical store; that store owns this identity.
        # If reading it fails we surface not-found *for this record* rather than
        # silently falling through to a different same-id session in another
        # store or the legacy store (Issue #3133 — one id, one session).
        try:
            data = store.get_session(session_id)
        except Exception:
            return ResolvedSession(session_id=session_id, found=False)
        if data is not None:
            metadata = dict(getattr(data, "metadata", {}) or {})
            try:
                chat_history = data.get_chat_history()
            except Exception:
                chat_history = []
            return ResolvedSession(
                session_id=session_id,
                agent_name=getattr(data, "agent_name", None) or metadata.get("agent_name"),
                model=metadata.get("model") or metadata.get("llm"),
                chat_history=chat_history,
                metadata=metadata,
                message_count=len(getattr(data, "messages", []) or []),
                created_at=getattr(data, "created_at", None),
                updated_at=getattr(data, "updated_at", None),
                found=True,
            )
        return ResolvedSession(session_id=session_id, found=False)

    # Deprecation-window fallback: legacy SessionManager dir-per-session store.
    legacy = _legacy_get(session_id)
    if legacy is not None:
        return legacy

    return ResolvedSession(session_id=session_id, found=False)


def delete_session(session_id: str, project_path: Optional[str] = None) -> bool:
    """Delete a session from the store that actually holds it (Issue #3133).

    Deletes from the *first* canonical store carrying the id — the same store
    :func:`resolve_session` selects — so a project-scoped delete never removes
    an unrelated same-id session living only in the global store. The delete is
    only counted when the store confirms removal (its ``delete_session`` returns
    ``True``), so an I/O failure is not reported as success. The legacy store is
    always swept too, so a shadow legacy record can't resurface a session the
    CLI just reported as deleted. Returns True if anything was actually removed.
    """
    deleted = False
    store = _store_for(session_id, project_path)
    if store is not None:
        try:
            deleted = bool(store.delete_session(session_id))
        except Exception:
            deleted = False

    # Always sweep the legacy store: a canonical delete alone would leave a
    # duplicate legacy record that reappears via the fallback on the next
    # resolve (Issue #3133 zombie sessions).
    legacy_deleted = _legacy_delete(session_id)
    return deleted or legacy_deleted


def export_session(
    session_id: str,
    format: str = "md",
    project_path: Optional[str] = None,
) -> Optional[str]:
    """Export a session resolved from the canonical store (Issue #3133).

    Returns the exported content, or ``None`` when the id resolves nowhere.
    Falls back to the legacy ``SessionManager`` export for legacy-only sessions.
    """
    resolved = resolve_session(session_id, project_path)
    if not resolved.found:
        return None

    if resolved.metadata.get("__legacy_session_manager__"):
        return _legacy_export(session_id, format)

    if format == "json":
        return json.dumps(resolved.to_dict(), indent=2, default=str)

    lines = [
        f"# Session: {resolved.agent_name or resolved.session_id}",
        "",
        f"- **Session ID**: {resolved.session_id}",
        f"- **Agent**: {resolved.agent_name or '-'}",
        f"- **Model**: {resolved.model or '-'}",
        f"- **Created**: {resolved.created_at or '-'}",
        f"- **Updated**: {resolved.updated_at or '-'}",
        f"- **Messages**: {resolved.message_count}",
        "",
        "## Conversation",
        "",
    ]
    for msg in resolved.chat_history:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        lines.append(f"### {role}")
        if content:
            lines.append(f"\n{content}")
        lines.append("")

    return "\n".join(lines)


def _legacy_get(session_id: str) -> Optional[ResolvedSession]:
    """Read a session from the legacy ``SessionManager`` store (best-effort)."""
    try:
        from .sessions import get_session_manager

        manager = get_session_manager()
        meta = manager.get(session_id)
    except Exception:
        return None
    if not meta:
        return None
    metadata = {"__legacy_session_manager__": True}
    return ResolvedSession(
        session_id=meta.session_id,
        agent_name=meta.name,
        metadata=metadata,
        message_count=meta.event_count,
        created_at=meta.created_at.isoformat() if meta.created_at else None,
        updated_at=meta.updated_at.isoformat() if meta.updated_at else None,
        found=True,
    )


def _legacy_delete(session_id: str) -> bool:
    """Delete from the legacy ``SessionManager`` store (best-effort)."""
    try:
        from .sessions import get_session_manager

        return get_session_manager().delete(session_id)
    except Exception:
        return False


def _legacy_export(session_id: str, format: str) -> Optional[str]:
    """Export via the legacy ``SessionManager`` store (best-effort)."""
    try:
        from .sessions import get_session_manager

        return get_session_manager().export(session_id, format=format)
    except Exception:
        return None
