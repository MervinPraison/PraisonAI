"""
Shared chat command utilities for PraisonAI bots.

DRY: format_status() and format_help() are used identically across
Telegram, Discord, and Slack bots.  Keep them in one place.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Set, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from praisonaiagents import Agent
    from ._run_control import SessionRunControl


class CommandAccessPolicy:
    """Manages per-command access control for bot commands."""
    
    ALWAYS_ALLOWED = {"help", "whoami"}
    
    def __init__(
        self, 
        admin_users: Optional[Set[str]] = None,
        user_allowed_commands: Optional[Set[str]] = None
    ):
        """Initialize command access policy.
        
        Args:
            admin_users: Set of user IDs who can run any command
            user_allowed_commands: Set of commands regular users can run.
                None means all commands allowed (backward compatibility)
        """
        self.admin_users = admin_users or set()
        self.user_allowed_commands = user_allowed_commands
    
    def can_run(self, user_id: str, command: str) -> bool:
        """Check if user can run a specific command.
        
        Args:
            user_id: User identifier
            command: Command name (without prefix)
            
        Returns:
            True if user can run the command
        """
        # Admins can run any command
        if user_id in self.admin_users:
            return True
        
        # Always-allowed commands are available to everyone
        if command in self.ALWAYS_ALLOWED:
            return True
        
        # If no restrictions, all commands are allowed
        if self.user_allowed_commands is None:
            return True
        
        # Check if command is in user's allowed list
        return command in self.user_allowed_commands
    
    def get_allowed_commands(self, user_id: str, all_commands: Set[str]) -> Set[str]:
        """Get list of commands a user is allowed to run.
        
        Args:
            user_id: User identifier
            all_commands: Set of all available commands
            
        Returns:
            Set of command names the user can run
        """
        if user_id in self.admin_users:
            return all_commands
        
        if self.user_allowed_commands is None:
            return all_commands
        
        return self.ALWAYS_ALLOWED | (self.user_allowed_commands & all_commands)


class CommandRegistry:
    """Unified command registry for all bot adapters."""
    
    def __init__(self):
        """Initialize the command registry."""
        self._commands: Dict[str, Dict[str, Any]] = {}
        self._initialize_builtin_commands()
    
    def _initialize_builtin_commands(self):
        """Register built-in commands."""
        self.register("help", {"description": "Show help message", "builtin": True})
        self.register("status", {"description": "Show bot status", "builtin": True})
        self.register("new", {"description": "Reset conversation session", "builtin": True})
        self.register("stop", {"description": "Cancel current agent task", "builtin": True})
        self.register("whoami", {"description": "Show your user info and permissions", "builtin": True})
    
    def register(
        self, 
        command: str, 
        metadata: Optional[Dict[str, Any]] = None,
        handler: Optional[Callable] = None
    ) -> None:
        """Register a command.
        
        Args:
            command: Command name (without prefix)
            metadata: Command metadata (description, category, etc.)
            handler: Optional command handler function
        """
        if metadata is None:
            metadata = {}
        
        self._commands[command] = {
            "handler": handler,
            **metadata
        }
    
    def unregister(self, command: str) -> bool:
        """Unregister a command.
        
        Args:
            command: Command name to unregister
            
        Returns:
            True if command was unregistered, False if not found
        """
        if command in self._commands and not self._commands[command].get("builtin"):
            del self._commands[command]
            return True
        return False
    
    def get_command(self, command: str) -> Optional[Dict[str, Any]]:
        """Get command metadata and handler.
        
        Args:
            command: Command name
            
        Returns:
            Command metadata dict or None if not found
        """
        return self._commands.get(command)
    
    def get_all_commands(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered commands.
        
        Returns:
            Dict of command name -> metadata
        """
        return self._commands.copy()
    
    def get_command_names(self) -> Set[str]:
        """Get set of all command names.
        
        Returns:
            Set of command names
        """
        return set(self._commands.keys())
    
    def format_help(
        self, 
        user_id: str,
        policy: Optional[CommandAccessPolicy] = None,
        agent: Optional["Agent"] = None,
        platform: str = "unknown"
    ) -> str:
        """Format help message showing available commands.
        
        Args:
            user_id: User requesting help
            policy: Access policy to filter commands
            agent: Current agent
            platform: Platform name
            
        Returns:
            Formatted help text
        """
        if policy:
            allowed = policy.get_allowed_commands(user_id, self.get_command_names())
        else:
            allowed = self.get_command_names()
        
        agent_name = agent.name if agent else "No agent"
        model = getattr(agent, "llm", "default") if agent else "default"
        
        lines = ["Available Commands"]
        
        # Sort commands for consistent display
        for cmd in sorted(allowed):
            cmd_info = self._commands.get(cmd, {})
            desc = cmd_info.get("description", "No description")
            lines.append(f"/{cmd} - {desc}")
        
        lines.append(f"\nAgent: {agent_name}")
        lines.append(f"Model: {model}")
        
        return "\n".join(lines)
    
    def format_whoami(
        self,
        user_id: str,
        username: Optional[str] = None,
        policy: Optional[CommandAccessPolicy] = None
    ) -> str:
        """Format whoami response showing user info and permissions.
        
        Args:
            user_id: User identifier
            username: User's display name
            policy: Access policy for permissions check
            
        Returns:
            Formatted whoami text
        """
        lines = ["User Information"]
        lines.append(f"User ID: {user_id}")
        
        if username:
            lines.append(f"Username: {username}")
        
        if policy:
            if user_id in policy.admin_users:
                lines.append("Role: Admin (all commands available)")
            else:
                lines.append("Role: User")
                allowed = policy.get_allowed_commands(user_id, self.get_command_names())
                lines.append(f"Allowed commands: {', '.join(sorted(allowed))}")
        else:
            lines.append("Role: User (no restrictions)")
        
        return "\n".join(lines)


# Global command registry instance
_global_registry = CommandRegistry()


def get_command_registry() -> CommandRegistry:
    """Get the global command registry instance.
    
    Returns:
        The global CommandRegistry instance
    """
    return _global_registry


def format_status(
    agent: Optional["Agent"],
    platform: str,
    started_at: Optional[float],
    is_running: bool,
) -> str:
    """Format a /status response string.

    Args:
        agent: The bot's agent (may be None).
        platform: Platform name (telegram, discord, slack).
        started_at: Epoch timestamp when bot started (None if not started).
        is_running: Whether the bot is currently running.
    """
    agent_name = agent.name if agent else "No agent"
    model = getattr(agent, "llm", "default") if agent else "default"
    uptime = ""
    if started_at:
        elapsed = int(time.time() - started_at)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{hours}h {minutes}m {seconds}s"
    return (
        f"Bot Status\n"
        f"Agent: {agent_name}\n"
        f"Model: {model}\n"
        f"Platform: {platform}\n"
        f"Uptime: {uptime}\n"
        f"Running: {is_running}"
    )


def format_help(
    agent: Optional["Agent"],
    platform: str,
    extra_commands: Optional[Dict[str, str]] = None,
) -> str:
    """Format a /help response string.

    Args:
        agent: The bot's agent (may be None).
        platform: Platform name.
        extra_commands: Dict of command_name -> description for custom commands.
    """
    agent_name = agent.name if agent else "No agent"
    model = getattr(agent, "llm", "default") if agent else "default"
    lines = [
        "Available Commands",
        "/status - Show bot status and info",
        "/new - Reset conversation session",
        "/stop - Cancel current agent task",
        "/help - Show this help message",
    ]
    if extra_commands:
        for cmd, desc in extra_commands.items():
            lines.append(f"/{cmd} - {desc}")
    lines.append(f"\nAgent: {agent_name}")
    lines.append(f"Model: {model}")
    return "\n".join(lines)


def handle_stop_command(session_manager, user_id: str) -> str:
    """Handle a /stop command to cancel an active run.
    
    This function works with both the legacy BotSessionManager approach
    and the newer SessionRunControl approach for maximum compatibility.
    
    Args:
        session_manager: BotSessionManager instance or SessionRunControl
        user_id: User ID to cancel run for
        
    Returns:
        Response message indicating success or failure
    """
    # Handle SessionRunControl (newer approach)
    if hasattr(session_manager, 'stop'):
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, need to use create_task
                task = asyncio.create_task(session_manager.stop(user_id))
                # This is a synchronous function, so we can't await
                # Return a message indicating async operation is happening
                return "⏳ Cancellation requested..."
            else:
                # No event loop, run synchronously
                stopped = asyncio.run(session_manager.stop(user_id))
                if stopped:
                    return "✅ Current task cancelled. Send a new message to start fresh."
                else:
                    return "ℹ️ No active task to cancel."
        except Exception as e:
            return f"❌ Error stopping task: {e}"
    
    # Handle BotSessionManager (legacy approach)
    elif hasattr(session_manager, 'cancel_run'):
        was_cancelled = session_manager.cancel_run(user_id, "user_stop_command")
        if was_cancelled:
            return "✅ Current task cancelled. Send a new message to start fresh."
        else:
            return "ℹ️ No active task to cancel."
    
    else:
        return "❌ Stop command not available (run control not enabled)"


async def handle_stop_command_async(
    user_id: str,
    run_control: Optional["SessionRunControl"] = None,
) -> str:
    """Async version of handle_stop_command for SessionRunControl.
    
    Args:
        user_id: User identifier
        run_control: SessionRunControl instance for managing runs
        
    Returns:
        Response message to send to user
    """
    if run_control is None:
        return "❌ Stop command not available (run control not enabled)"
        
    try:
        stopped = await run_control.stop(user_id)
        if stopped:
            return "✅ Current task cancelled. Send a new message to start fresh."
        else:
            return "ℹ️ No active task to cancel."
    except Exception as e:
        return f"❌ Error stopping task: {e}"


def handle_run_status_command(
    user_id: str,
    run_control: Optional["SessionRunControl"] = None,
) -> str:
    """Handle request for current run status.
    
    Args:
        user_id: User identifier
        run_control: SessionRunControl instance
        
    Returns:
        Status message
    """
    if run_control is None:
        return "Run control not enabled"
        
    try:
        status = run_control.get_run_status(user_id)
        
        if not status["is_running"]:
            pending_info = " (has queued message)" if status["has_pending"] else ""
            return f"💤 No active task{pending_info}"
            
        elapsed = status.get("elapsed_seconds", 0)
        elapsed_str = f"{elapsed//60}m {elapsed%60}s" if elapsed > 60 else f"{elapsed}s"
        
        pending_info = ""
        if status["has_pending"]:
            preview = status.get("pending_preview", "")
            pending_info = f"\n📝 Queued: {preview}"
            
        return f"⚡ Task running for {elapsed_str}{pending_info}"
    except Exception as e:
        return f"Error getting status: {e}"
