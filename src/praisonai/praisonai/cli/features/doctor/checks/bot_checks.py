"""
Bot-specific doctor checks for PraisonAI.

Registers checks for bot tokens, config validation, and channel probes.
"""

from __future__ import annotations

import os
import time
from typing import List

from ..models import CheckResult, CheckStatus, CheckCategory


def check_bot_tokens() -> CheckResult:
    """Check bot token environment variables."""
    token_vars = {
        "TELEGRAM_BOT_TOKEN": "Telegram",
        "DISCORD_BOT_TOKEN": "Discord",
        "SLACK_BOT_TOKEN": "Slack",
        "WHATSAPP_ACCESS_TOKEN": "WhatsApp",
    }
    found = []
    for var, name in token_vars.items():
        if os.environ.get(var):
            found.append(name)

    if found:
        return CheckResult(
            id="bot_tokens",
            title="Bot Tokens",
            category=CheckCategory.BOTS,
            status=CheckStatus.PASS,
            message=f"Found: {', '.join(found)}",
        )
    return CheckResult(
        id="bot_tokens",
        title="Bot Tokens",
        category=CheckCategory.BOTS,
        status=CheckStatus.WARN,
        message="No bot tokens found in environment",
        remediation="Set at least one: export TELEGRAM_BOT_TOKEN=your_token",
    )


def check_bot_config(config_path: str = "bot.yaml") -> CheckResult:
    """Check bot.yaml exists and is valid."""
    start = time.time()
    if not os.path.exists(config_path):
        return CheckResult(
            id="bot_config",
            title="Bot Config",
            category=CheckCategory.BOTS,
            status=CheckStatus.WARN,
            message=f"{config_path} not found",
            remediation="Run 'praisonai onboard' to create one",
            duration_ms=(time.time() - start) * 1000,
        )
    try:
        from praisonai.bots._config_schema import load_and_validate_bot_yaml
        load_and_validate_bot_yaml(config_path)
        return CheckResult(
            id="bot_config",
            title="Bot Config",
            category=CheckCategory.BOTS,
            status=CheckStatus.PASS,
            message=f"{config_path} valid",
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as e:
        return CheckResult(
            id="bot_config",
            title="Bot Config",
            category=CheckCategory.BOTS,
            status=CheckStatus.FAIL,
            message=f"Invalid: {str(e)[:200]}",
            remediation="Fix errors in bot.yaml or run 'praisonai onboard'",
            duration_ms=(time.time() - start) * 1000,
        )


def get_bot_checks() -> List[CheckResult]:
    """Run all bot-specific checks and return results."""
    return [
        check_bot_tokens(),
        check_bot_config(),
    ]
