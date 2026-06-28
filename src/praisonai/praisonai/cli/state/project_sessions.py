"""
Project-scoped session management for CLI.

Provides session continuity within project boundaries.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from praisonaiagents.session.store import DefaultSessionStore
from ..utils.project import get_project_id, get_project_name, get_project_sessions_dir


class ProjectSessionStore(DefaultSessionStore):
    """
    Project-scoped session store.
    
    Extends DefaultSessionStore to scope sessions to the current project.
    """
    
    def __init__(self, project_path: Optional[str] = None, **kwargs):
        """
        Initialize project-scoped session store.
        
        Args:
            project_path: Project root path (defaults to cwd)
            **kwargs: Additional arguments for DefaultSessionStore
        """
        self.project_path = project_path
        self.project_id = get_project_id(project_path)
        self.project_name = get_project_name(project_path)
        
        # Use project-specific session directory
        project_session_dir = get_project_sessions_dir(project_path)
        
        super().__init__(
            session_dir=str(project_session_dir),
            **kwargs
        )
    
    def get_last_session_id(self) -> Optional[str]:
        """
        Get the most recent session ID for this project.
        
        Returns:
            Session ID of the most recent session, or None if no sessions exist
        """
        sessions = self.list_sessions(limit=1)
        return sessions[0].get("session_id") if sessions else None
    
    def get_project_info(self) -> dict:
        """
        Get project information.
        
        Returns:
            Dictionary with project details
        """
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "project_path": self.project_path or str(Path.cwd()),
            "session_dir": self.session_dir,
        }


def get_project_session_store(project_path: Optional[str] = None, project_id: Optional[str] = None) -> ProjectSessionStore:
    """
    Get a project-scoped session store.
    
    Args:
        project_path: Project root path (defaults to cwd)
        project_id: Specific project ID to use (if provided, creates store for that project)
        
    Returns:
        ProjectSessionStore instance
    """
    if project_id:
        # Create store for specific project ID
        from praisonaiagents.paths import get_sessions_dir
        project_session_dir = get_sessions_dir() / f"projects/{project_id}"
        # Use DefaultSessionStore directly with the specific directory
        from praisonaiagents.session.store import DefaultSessionStore
        return DefaultSessionStore(session_dir=str(project_session_dir))
    else:
        # Use current project
        return ProjectSessionStore(project_path)


def session_exists_anywhere(session_id: str, project_path: Optional[str] = None) -> bool:
    """Return True if a session exists in the project store or global store.

    Resume must work regardless of whether the session was created via the
    project-scoped ``run --continue`` path or the global default store (e.g.
    sessions created by the gateway or interactive TUI). This mirrors the
    lookup semantics of ``rehydrate_session`` (Issue #2274).
    """
    try:
        if get_project_session_store(project_path).session_exists(session_id):
            return True
    except Exception:
        pass

    try:
        from praisonaiagents.session.store import get_default_session_store

        return get_default_session_store().session_exists(session_id)
    except Exception:
        return False


def find_last_session(project_path: Optional[str] = None) -> Optional[str]:
    """
    Find the last session ID for the current project.
    
    Args:
        project_path: Project root path (defaults to cwd)
        
    Returns:
        Session ID or None if no sessions exist
    """
    store = get_project_session_store(project_path)
    return store.get_last_session_id()


def build_cli_memory_config(
    session_id: Optional[str] = None,
    auto_save: Optional[str] = None,
):
    """Build MemoryConfig for ``praison run`` project-scoped session continuity."""
    if not session_id and not auto_save:
        return None

    from praisonaiagents import MemoryConfig

    sid = session_id or auto_save
    return MemoryConfig(session_id=sid, auto_save=auto_save, history=True)


def apply_cli_session_continuity(agent, session_id: str, project_path: Optional[str] = None, auto_save: Optional[str] = None) -> None:
    """Wire an agent to the project session store and restore prior history."""
    store = get_project_session_store(project_path)
    agent._session_store = store
    agent._session_id = session_id
    agent._history_enabled = True
    agent._history_session_id = session_id
    if auto_save is not None:
        agent.auto_save = auto_save

    history = store.get_chat_history(session_id) or []
    if history:
        existing = {(m.get("role"), m.get("content")) for m in agent.chat_history}
        for msg in history:
            entry = {"role": msg["role"], "content": msg["content"]}
            key = (entry["role"], entry["content"])
            if key not in existing:
                agent.chat_history.append(entry)
                existing.add(key)
        agent._auto_save_last_index = len(agent.chat_history)

    # Persist model/agent so a later resume is deterministic regardless of the
    # flags/config in effect at resume time (Issue #2274).
    try:
        model = getattr(agent, "llm", None)
        fields = {"agent_name": getattr(agent, "name", None)}
        if isinstance(model, str):
            fields["model"] = model
        else:
            # Object-based LLM configs (e.g. a LiteLLM instance) expose the
            # model name via a `model` attribute; persist it when available so
            # resume stays deterministic for non-string configs (Issue #2274).
            model_name = getattr(model, "model", None)
            if isinstance(model_name, str):
                fields["model"] = model_name
        store.update_session_metadata(session_id, **fields)
    except Exception:
        pass

    agent._session_store_initialized = True


def _empty_usage() -> Dict[str, Any]:
    """A zeroed cumulative-usage record."""
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
        "cost": 0.0,
        "requests": 0,
    }


def read_session_usage(
    session_id: str, project_path: Optional[str] = None
) -> Dict[str, Any]:
    """Read the persisted cumulative usage totals for a session.

    Returns a dict with ``input_tokens``/``output_tokens``/``cached_tokens``/
    ``total_tokens``/``cost``/``requests``. Missing values default to zero so
    callers can render a total even for never-tracked sessions (Issue #2421).
    """
    usage = _empty_usage()
    try:
        store = get_project_session_store(project_path)
        if not store.session_exists(session_id):
            return usage
        data = store.get_session(session_id)
        metadata = dict(getattr(data, "metadata", {}) or {})
    except Exception:
        return usage

    stored = metadata.get("usage")
    if isinstance(stored, dict):
        for key in usage:
            if isinstance(stored.get(key), (int, float)):
                usage[key] = stored[key]
    # Back-compat with the flat fields surfaced by list_sessions/to_dict.
    if not usage["total_tokens"] and isinstance(metadata.get("total_tokens"), (int, float)):
        usage["total_tokens"] = metadata["total_tokens"]
    if not usage["cost"] and isinstance(metadata.get("cost"), (int, float)):
        usage["cost"] = metadata["cost"]
    return usage


def format_usage_footer(usage: Dict[str, Any]) -> str:
    """Render a compact one-line usage footer, e.g.
    ``1,240 in / 3,980 out · $0.0140``.
    """
    usage = usage or _empty_usage()
    in_tok = int(usage.get("input_tokens", 0) or 0)
    out_tok = int(usage.get("output_tokens", 0) or 0)
    cost = float(usage.get("cost", 0.0) or 0.0)
    return f"{in_tok:,} in / {out_tok:,} out \u00b7 ${cost:.4f}"


def accumulate_session_usage(
    session_id: str,
    model: Optional[str] = None,
    project_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Accumulate the global token collector's usage into a session record.

    Reads per-call token usage already aggregated by
    ``praisonaiagents.telemetry.token_collector`` for this run, prices it via
    the CLI cost tracker, and merges the deltas into the session's persisted
    ``usage`` metadata so cumulative ``cost``/``tokens`` survive resume
    (Issue #2421). Also mirrors flat ``total_tokens``/``cost`` fields that
    ``list_sessions`` already surfaces.

    Best-effort: any failure leaves the session untouched and returns the
    current (possibly unchanged) totals.
    """
    current = read_session_usage(session_id, project_path)
    try:
        from praisonaiagents.telemetry.token_collector import get_token_collector

        summary = get_token_collector().get_session_summary()
    except Exception:
        return current

    totals = (summary or {}).get("total_metrics") or {}
    delta_in = int(totals.get("input_tokens", 0) or 0)
    delta_out = int(totals.get("output_tokens", 0) or 0)
    delta_cached = int(totals.get("cached_tokens", 0) or 0)
    delta_total = int(totals.get("total_tokens", 0) or 0)
    delta_requests = int((summary or {}).get("total_interactions", 0) or 0)

    if not (delta_in or delta_out or delta_total):
        return current

    delta_cost = 0.0
    try:
        from ..features.cost_tracker import get_pricing

        pricing = get_pricing(model or "default")
        delta_cost = pricing.calculate_cost(delta_in, delta_out)
    except Exception:
        delta_cost = 0.0

    updated = {
        "input_tokens": current["input_tokens"] + delta_in,
        "output_tokens": current["output_tokens"] + delta_out,
        "cached_tokens": current["cached_tokens"] + delta_cached,
        "total_tokens": current["total_tokens"] + (delta_total or (delta_in + delta_out)),
        "cost": round(current["cost"] + delta_cost, 6),
        "requests": current["requests"] + delta_requests,
    }

    try:
        store = get_project_session_store(project_path)
        store.update_session_metadata(
            session_id,
            usage=updated,
            total_tokens=updated["total_tokens"],
            cost=updated["cost"],
        )
        # Avoid double-counting if accumulate is called again in-process.
        from praisonaiagents.telemetry.token_collector import get_token_collector

        get_token_collector().reset()
    except Exception:
        return current

    return updated