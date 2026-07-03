"""Channel approval backends for bot platforms (slack, telegram, discord, …)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

CHANNEL_BACKENDS = frozenset(
    {"slack", "telegram", "discord", "webhook", "http", "secure", "presentation"}
)


def resolve_channel_approval_backend(name: str) -> Any:
    """Resolve a channel-specific approval backend by name.

    Args:
        name: Lowercase backend id (slack, telegram, discord, webhook, http,
            secure, presentation).

    Raises:
        ValueError: If env vars are missing or the name is unknown.
    """
    if name == "slack":
        from praisonai_bot.bots import SlackApproval

        return SlackApproval()

    if name == "telegram":
        from praisonai_bot.bots import TelegramApproval

        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            raise ValueError(
                "TELEGRAM_CHAT_ID env var required for --approval telegram"
            )
        return TelegramApproval(chat_id=chat_id)

    if name == "discord":
        from praisonai_bot.bots import DiscordApproval

        channel_id = os.environ.get("DISCORD_CHANNEL_ID", "")
        if not channel_id:
            raise ValueError(
                "DISCORD_CHANNEL_ID env var required for --approval discord"
            )
        return DiscordApproval(channel_id=channel_id)

    if name == "webhook":
        from praisonai_bot.bots import WebhookApproval

        return WebhookApproval()

    if name == "http":
        from praisonai_bot.bots import HTTPApproval

        return HTTPApproval()

    if name in ("secure", "presentation"):
        from praisonai_bot.bots import ApprovalStore, PresentationApprovalBackend

        base = os.environ.get("PRAISONAI_HOME")
        state_dir = (Path(base) if base else Path.home() / ".praisonai") / "state"
        store = ApprovalStore(path=state_dir / "approvals.sqlite")

        actors_env = os.environ.get("PRAISONAI_APPROVAL_ACTORS", "").strip()
        allowed_actors = {a.strip() for a in actors_env.split(",") if a.strip()}
        if not allowed_actors:
            raise ValueError(
                "PRAISONAI_APPROVAL_ACTORS must list at least one actor id "
                "for --approval secure/presentation (comma-separated)."
            )
        return PresentationApprovalBackend(
            store=store,
            allowed_actors=allowed_actors,
        )

    raise ValueError(f"Unknown channel approval backend: {name!r}")
