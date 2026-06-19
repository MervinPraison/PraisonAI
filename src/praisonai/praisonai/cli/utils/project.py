"""
Project identity utilities for CLI session scoping.

Provides functions to identify the current project context for scoped sessions.
"""

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Optional


def get_git_root(path: Optional[str] = None) -> Optional[Path]:
    """
    Find the git repository root from the given path.
    
    Args:
        path: Starting path (defaults to cwd)
        
    Returns:
        Path to git root, or None if not in a git repo
    """
    start_path = Path(path) if path else Path.cwd()
    
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=start_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_project_id(path: Optional[str] = None) -> str:
    """
    Generate a stable project identifier.
    
    Uses git root path if available, falls back to current directory.
    Returns a short hash for scoped session storage.
    
    Args:
        path: Starting path (defaults to cwd)
        
    Returns:
        Short project hash (8 chars)
    """
    # Try git root first
    git_root = get_git_root(path)
    if git_root:
        project_path = str(git_root.resolve())
    else:
        # Fall back to current directory
        project_path = str(Path(path).resolve() if path else Path.cwd().resolve())
    
    # Generate short hash
    return hashlib.sha256(project_path.encode()).hexdigest()[:8]


def get_project_name(path: Optional[str] = None) -> str:
    """
    Get a human-readable project name.
    
    Args:
        path: Starting path (defaults to cwd)
        
    Returns:
        Project directory name
    """
    git_root = get_git_root(path)
    if git_root:
        return git_root.name
    
    current_path = Path(path) if path else Path.cwd()
    return current_path.name


def get_project_sessions_dir(path: Optional[str] = None) -> Path:
    """
    Get project-scoped session directory.
    
    Args:
        path: Starting path (defaults to cwd)
        
    Returns:
        Path to project sessions directory
    """
    from praisonaiagents.paths import get_sessions_dir
    
    project_id = get_project_id(path)
    return get_sessions_dir() / f"projects/{project_id}"


def build_cli_memory_config(
    session_id: Optional[str] = None,
    auto_save: Optional[str] = None,
):
    """Build MemoryConfig for CLI session continuity."""
    if not session_id and not auto_save:
        return None
    from praisonaiagents import MemoryConfig

    name = session_id or auto_save
    return MemoryConfig(
        auto_save=auto_save or name,
        history=True,
        session_id=name,
    )


def apply_cli_session_continuity(agent, session_id: Optional[str]) -> None:
    """Wire an agent to the project session store for CLI continuity."""
    if not session_id:
        return

    from ..state.project_sessions import get_project_session_store

    store = get_project_session_store()
    agent._session_id = session_id
    agent._session_store = store
    agent._session_store_initialized = True
    agent._history_enabled = True
    agent._history_session_id = session_id
    
    # Don't pre-populate chat_history - the mixin will load it from _session_store
    # when _history_enabled=True, avoiding duplicate history injection