"""
Session Handler for CLI.

Provides session management for multi-turn conversations.
Usage: praisonai session list
       praisonai session show <name>
       praisonai session resume <name>
       praisonai session delete <name>
"""

from typing import Any, Dict, List
from .base import CommandHandler


class SessionHandler(CommandHandler):
    """
    Handler for session command.
    
    Manages conversation sessions using FileMemory.
    
    Example:
        praisonai session list
        praisonai session show my-project
        praisonai session resume my-project
        praisonai session delete my-project
    """
    
    def __init__(self, verbose: bool = False, user_id: str = "praison"):
        super().__init__(verbose)
        self.user_id = user_id
        self._memory = None
    
    @property
    def feature_name(self) -> str:
        return "session"
    
    def get_actions(self) -> List[str]:
        return ["list", "show", "resume", "delete", "help"]
    
    def get_help_text(self) -> str:
        return """
Session Commands:
  praisonai session list                 - List all saved sessions
  praisonai session show <name>          - Show session details
  praisonai session resume <name>        - Resume a session (load into memory)
  praisonai session delete <name>        - Delete a session

Sessions store conversation history for multi-turn interactions.
Use --auto-save <name> flag when running agents to auto-save sessions.
"""
    
    def _get_memory(self):
        """Get FileMemory instance lazily."""
        if self._memory is None:
            try:
                from praisonaiagents.memory.file_memory import FileMemory
                self._memory = FileMemory(user_id=self.user_id)
            except ImportError:
                self.print_status(
                    "Session requires praisonaiagents. Install with: pip install praisonaiagents",
                    "error"
                )
                return None
        return self._memory
    
    def action_list(self, args: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        List all saved sessions.
        
        Returns:
            List of session info dicts
        """
        memory = self._get_memory()
        if not memory:
            return []
        
        try:
            sessions = memory.list_sessions()
            
            if sessions:
                from rich.table import Table
                from rich.console import Console
                
                console = Console()
                table = Table(title="Saved Sessions")
                table.add_column("Name", style="cyan")
                table.add_column("Saved At", style="green")
                table.add_column("Messages", style="yellow")
                table.add_column("Has History", style="magenta")
                
                for s in sessions:
                    table.add_row(
                        s.get("name", ""),
                        s.get("saved_at", "")[:19] if s.get("saved_at") else "",
                        str(s.get("short_term_count", 0)),
                        "✅" if s.get("has_conversation") else "❌"
                    )
                
                console.print(table)
            else:
                self.print_status("No sessions found. Use --auto-save <name> when running agents.", "warning")
            
            return sessions
        except Exception as e:
            self.print_status(f"Failed to list sessions: {e}", "error")
            return []
    
    def action_show(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Show session details.
        
        Args:
            args: List containing session name
            
        Returns:
            Session data dict
        """
        if not args:
            self.print_status("Usage: praisonai session show <name>", "error")
            return {}
        
        memory = self._get_memory()
        if not memory:
            return {}
        
        name = args[0]
        
        try:
            session_data = memory.resume_session(name)
            
            print(f"\n📊 Session: {name}")
            print(f"Saved at: {session_data.get('saved_at_iso', 'Unknown')}")
            print(f"User ID: {session_data.get('user_id', 'Unknown')}")
            print(f"Short-term items: {len(session_data.get('short_term', []))}")
            print(f"Conversation messages: {len(session_data.get('conversation_history', []))}")
            
            # Show last few messages
            history = session_data.get('conversation_history', [])
            if history:
                print(f"\nLast {min(5, len(history))} messages:")
                for msg in history[-5:]:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')[:100]
                    if len(msg.get('content', '')) > 100:
                        content += "..."
                    print(f"  [{role}]: {content}")
            
            return session_data
        except FileNotFoundError:
            self.print_status(f"Session '{name}' not found", "error")
            return {}
        except Exception as e:
            self.print_status(f"Failed to show session: {e}", "error")
            return {}
    
    def action_resume(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Resume a session (load into memory).
        
        Args:
            args: List containing session name
            
        Returns:
            Session data dict
        """
        if not args:
            self.print_status("Usage: praisonai session resume <name>", "error")
            return {}
        
        memory = self._get_memory()
        if not memory:
            return {}
        
        name = args[0]
        
        try:
            session_data = memory.resume_session(name)
            self.print_status(f"✅ Session '{name}' resumed", "success")
            print(f"   Loaded {len(session_data.get('short_term', []))} memory items")
            print(f"   Loaded {len(session_data.get('conversation_history', []))} conversation messages")
            return session_data
        except FileNotFoundError:
            self.print_status(f"Session '{name}' not found", "error")
            return {}
        except Exception as e:
            self.print_status(f"Failed to resume session: {e}", "error")
            return {}
    
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
        
        memory = self._get_memory()
        if not memory:
            return False
        
        name = args[0]
        
        try:
            if memory.delete_session(name):
                self.print_status(f"✅ Session '{name}' deleted", "success")
                return True
            else:
                self.print_status(f"Session '{name}' not found", "error")
                return False
        except Exception as e:
            self.print_status(f"Failed to delete session: {e}", "error")
            return False
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """Execute session command action."""
        return super().execute(action, action_args, **kwargs)
