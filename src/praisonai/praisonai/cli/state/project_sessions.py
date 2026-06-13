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


def apply_cli_session_continuity(agent, session_id: str, project_path: Optional[str] = None) -> None:
    """
    Bind an agent to the project-scoped session store and restore prior turns.

    CLI ``run --continue/--session`` discovers sessions in the project store but
    agents default to the global store unless explicitly wired here.
    """
    store = get_project_session_store(project_path)
    agent._session_store = store
    agent._session_id = session_id
    if not getattr(agent, "auto_save", None):
        agent.auto_save = session_id

    history = store.get_chat_history(session_id)
    if history and not agent.chat_history:
        agent.chat_history = [
            {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            for msg in history
        ]
        agent._auto_save_last_index = len(agent.chat_history)