"""
Session Handler for CLI.

Provides session management for multi-turn conversations.
Usage: praisonai session start "project-x"
       praisonai session list
       praisonai session resume "project-x"
"""

import os
from typing import Any, Dict, List
from .base import CommandHandler


class SessionHandler(CommandHandler):
    """
    Handler for session command.
    
    Manages conversation sessions for multi-turn interactions.
    
    Example:
        praisonai session start my-project
        praisonai session list
        praisonai session resume my-project
        praisonai session delete my-project
    """
    
    def __init__(self, verbose: bool = False, workspace: str = None):
        super().__init__(verbose)
        self.workspace = workspace or os.path.join(os.path.expanduser("~"), ".praison", "sessions")
        os.makedirs(self.workspace, exist_ok=True)
        self._session = None
    
    @property
    def feature_name(self) -> str:
        return "session"
    
    def get_actions(self) -> List[str]:
        return ["start", "list", "resume", "delete", "info", "help"]
    
    def get_help_text(self) -> str:
        return """
Session Commands:
  praisonai session start <name>         - Start a new session
  praisonai session list                 - List all sessions
  praisonai session resume <name>        - Resume an existing session
  praisonai session delete <name>        - Delete a session
  praisonai session info <name>          - Show session details

Sessions enable multi-turn conversations with context preservation.
"""
    
    def _get_session_class(self):
        """Get Session class lazily."""
        try:
            from praisonaiagents import Session
            return Session
        except ImportError:
            self.print_status(
                "Session requires praisonaiagents. Install with: pip install praisonaiagents",
                "error"
            )
            return None
    
    def _get_session_path(self, name: str) -> str:
        """Get path for a session file."""
        return os.path.join(self.workspace, f"{name}.json")
    
    def action_start(self, args: List[str], **kwargs) -> Any:
        """
        Start a new session.
        
        Args:
            args: List containing session name
            
        Returns:
            Session instance or None
        """
        if not args:
            self.print_status("Usage: praisonai session start <name>", "error")
            return None
        
        Session = self._get_session_class()
        if not Session:
            return None
        
        name = args[0]
        session_path = self._get_session_path(name)
        
        if os.path.exists(session_path):
            self.print_status(f"Session '{name}' already exists. Use 'resume' to continue.", "warning")
            return None
        
        try:
            session = Session(session_id=name)
            self._session = session
            self.print_status(f"✅ Session '{name}' started", "success")
            return session
        except Exception as e:
            self.print_status(f"Failed to start session: {e}", "error")
            return None
    
    def action_list(self, args: List[str], **kwargs) -> List[str]:
        """
        List all sessions.
        
        Returns:
            List of session names
        """
        sessions = []
        
        try:
            for file in os.listdir(self.workspace):
                if file.endswith('.json'):
                    sessions.append(file[:-5])  # Remove .json extension
            
            if sessions:
                self.print_status("\n📋 Available Sessions:", "info")
                for name in sessions:
                    self.print_status(f"  - {name}", "info")
            else:
                self.print_status("No sessions found", "warning")
            
            return sessions
        except Exception as e:
            self.print_status(f"Failed to list sessions: {e}", "error")
            return []
    
    def action_resume(self, args: List[str], **kwargs) -> Any:
        """
        Resume an existing session.
        
        Args:
            args: List containing session name
            
        Returns:
            Session instance or None
        """
        if not args:
            self.print_status("Usage: praisonai session resume <name>", "error")
            return None
        
        Session = self._get_session_class()
        if not Session:
            return None
        
        name = args[0]
        session_path = self._get_session_path(name)
        
        if not os.path.exists(session_path):
            self.print_status(f"Session '{name}' not found", "error")
            return None
        
        try:
            session = Session(session_id=name)
            if hasattr(session, 'load'):
                session.load(session_path)
            self._session = session
            self.print_status(f"✅ Session '{name}' resumed", "success")
            return session
        except Exception as e:
            self.print_status(f"Failed to resume session: {e}", "error")
            return None
    
    def action_delete(self, args: List[str], **kwargs) -> bool:
        """
        Delete a session.
        
        Args:
            args: List containing session name
            
        Returns:
            True if successful
        """
        if not args:
            self.print_status("Usage: praisonai session delete <name>", "error")
            return False
        
        name = args[0]
        session_path = self._get_session_path(name)
        
        if not os.path.exists(session_path):
            self.print_status(f"Session '{name}' not found", "error")
            return False
        
        try:
            os.remove(session_path)
            self.print_status(f"✅ Session '{name}' deleted", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to delete session: {e}", "error")
            return False
    
    def action_info(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Show session info.
        
        Args:
            args: List containing session name
            
        Returns:
            Dictionary of session info
        """
        if not args:
            self.print_status("Usage: praisonai session info <name>", "error")
            return {}
        
        name = args[0]
        session_path = self._get_session_path(name)
        
        if not os.path.exists(session_path):
            self.print_status(f"Session '{name}' not found", "error")
            return {}
        
        try:
            import json
            with open(session_path, 'r') as f:
                data = json.load(f)
            
            info = {
                "name": name,
                "path": session_path,
                "messages": len(data.get('messages', [])),
                "created": data.get('created_at', 'Unknown')
            }
            
            self.print_status(f"\n📊 Session '{name}' Info:", "info")
            for key, value in info.items():
                self.print_status(f"  {key}: {value}", "info")
            
            return info
        except Exception as e:
            self.print_status(f"Failed to get session info: {e}", "error")
            return {}
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """Execute session command action."""
        return super().execute(action, action_args, **kwargs)
