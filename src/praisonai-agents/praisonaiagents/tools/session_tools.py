"""Session management and search tools.

This module provides tools for searching session history and managing
conversation context.
"""

import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class SessionTools:
    """Tools for session history and context management."""
    
    def __init__(self, workspace=None):
        """Initialize SessionTools.
        
        Args:
            workspace: Optional Workspace instance for path containment
        """
        self._workspace = workspace
    
    def session_search(self, query: str, limit: int = 10, 
                      session_id: str = None) -> str:
        """Search through session history for relevant conversations.
        
        Args:
            query: Search query text
            limit: Maximum number of results to return
            session_id: Specific session to search (optional)
            
        Returns:
            JSON string with search results
        """
        try:
            # No session-store backend is wired up yet. Return an empty, honest
            # result so the LLM cannot incorporate fabricated history.
            return json.dumps({
                "success": False,
                "query": query,
                "session_id": session_id,
                "results": [],
                "total_found": 0,
                "limit": limit,
                "error": "session_search is not configured: no session storage backend available",
            }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Error searching sessions: {e!s}"})


# Create default instance for direct function access
_session_tools = SessionTools()

def session_search(query: str, limit: int = 10, session_id: str = None) -> str:
    """Search through session history for relevant conversations.
    
    Args:
        query: Search query text
        limit: Maximum number of results to return
        session_id: Specific session to search (optional)
        
    Returns:
        JSON string with search results
    """
    return _session_tools.session_search(query, limit, session_id)


def create_session_tools(workspace=None) -> SessionTools:
    """Create SessionTools instance with optional workspace containment.
    
    Args:
        workspace: Optional Workspace instance for path containment
        
    Returns:
        SessionTools instance configured with workspace
    """
    return SessionTools(workspace=workspace)