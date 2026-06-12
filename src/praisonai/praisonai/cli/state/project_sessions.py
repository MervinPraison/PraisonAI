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
        project_id: Specific project ID to use instead of detecting from project_path
        
    Returns:
        ProjectSessionStore instance
    """
    if project_id:
        # Create store for specific project ID
        from praisonaiagents.paths import get_sessions_dir
        project_session_dir = get_sessions_dir() / f"projects/{project_id}"
        return ProjectSessionStore(str(project_session_dir))
    else:
        # Use current project path
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