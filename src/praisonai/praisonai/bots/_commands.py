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
        "/help - Show this help message",
    ]
    if extra_commands:
        for cmd, desc in extra_commands.items():
            lines.append(f"/{cmd} - {desc}")
    lines.append(f"\nAgent: {agent_name}")
    lines.append(f"Model: {model}")
    return "\n".join(lines)
