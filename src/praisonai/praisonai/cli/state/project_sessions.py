"""
Project-scoped session management for CLI.

Provides session continuity within project boundaries.
"""

import os
from pathlib import Path
from typing import List, Optional

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
        if isinstance(model, str):
            store.update_session_metadata(
                session_id,
                model=model,
                agent_name=getattr(agent, "name", None),
            )
    except Exception:
        pass

    agent._session_store_initialized = True