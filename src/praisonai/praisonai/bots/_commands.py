"""
Shared chat command utilities for PraisonAI bots.

DRY: format_status() and format_help() are used identically across
Telegram, Discord, and Slack bots.  Keep them in one place.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent
    from ._run_control import SessionRunControl


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
