"""
Approval backend resolver for PraisonAI CLI.

Maps CLI --approval flag values to approval backend instances.
Used by run, chat, and main CLI commands for DRY approval wiring.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Valid backend names for CLI help text
VALID_BACKENDS = ["console", "slack", "telegram", "discord", "webhook", "http", "agent", "auto", "none"]


def resolve_approval_backend(value: Optional[str]) -> Optional[Any]:
    """Resolve a CLI --approval flag value to an approval backend instance.

    Args:
        value: One of the backend names (slack, telegram, discord, webhook,
               http, console, auto, none) or None.  For webhook and http,
               additional config is read from environment variables.

    Returns:
        An approval backend instance, or None if disabled.

    Raises:
        ValueError: If the value is not a recognised backend name.
    """
    if value is None or value.lower() == "none":
        return None

    name = value.lower().strip()

    if name in ("true", "console"):
        from praisonaiagents.approval.backends import ConsoleBackend
        return ConsoleBackend()

    if name == "auto":
        from praisonaiagents.approval.backends import AutoApproveBackend
        return AutoApproveBackend()

    if name == "slack":
        from praisonai.bots import SlackApproval
        return SlackApproval()

    if name == "telegram":
        from praisonai.bots import TelegramApproval
        import os
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            raise ValueError(
                "TELEGRAM_CHAT_ID env var required for --approval telegram"
            )
        return TelegramApproval(chat_id=chat_id)

    if name == "discord":
        from praisonai.bots import DiscordApproval
        import os
        channel_id = os.environ.get("DISCORD_CHANNEL_ID", "")
        if not channel_id:
            raise ValueError(
                "DISCORD_CHANNEL_ID env var required for --approval discord"
            )
        return DiscordApproval(channel_id=channel_id)

    if name == "webhook":
        from praisonai.bots import WebhookApproval
        return WebhookApproval()

    if name == "http":
        from praisonai.bots import HTTPApproval
        return HTTPApproval()

    if name == "agent":
        from praisonaiagents.approval import AgentApproval
        from praisonaiagents import Agent
        reviewer = Agent(
            name="approval-reviewer",
            instructions=(
                "You are a security reviewer. Only approve low-risk read "
                "operations. Deny anything destructive. Respond with exactly "
                "one word: APPROVE or DENY"
            ),
        )
        return AgentApproval(approver_agent=reviewer)

    raise ValueError(
        f"Unknown approval backend: {value!r}. "
        f"Valid options: {', '.join(VALID_BACKENDS)}"
    )
