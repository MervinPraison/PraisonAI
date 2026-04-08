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


def check_bot_security(config_path: str = "bot.yaml") -> CheckResult:
    """Check bot security configuration for safe defaults."""
    start = time.time()
    warnings = []
    issues = []
    
    # Check if bot.yaml exists
    if not os.path.exists(config_path):
        return CheckResult(
            id="bot_security",
            title="Bot Security Config",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message=f"{config_path} not found - security check skipped",
            duration_ms=(time.time() - start) * 1000,
        )
    
    try:
        from praisonai.bots._config_schema import load_and_validate_bot_yaml
        config = load_and_validate_bot_yaml(config_path)
        
        # Check for risky configurations across channels
        for channel_name, channel_config in config.channels.items():
            # Check for missing allowlists in production-like setups
            if not channel_config.allowlist and not channel_config.blocklist:
                warnings.append(f"{channel_name}: No allowlist/blocklist configured")
            
            # Check for overly permissive group policies
            if channel_config.group_policy == "respond_all":
                warnings.append(f"{channel_name}: group_policy='respond_all' - consider 'mention_only' for security")
        
        # Check for missing gateway pairing settings 
        gateway_secret = os.environ.get("PRAISONAI_GATEWAY_SECRET")
        if not gateway_secret:
            warnings.append("PRAISONAI_GATEWAY_SECRET not set - pairing codes will not persist across restarts")
        
        # Determine status
        if issues:
            return CheckResult(
                id="bot_security",
                title="Bot Security Config",
                category=CheckCategory.BOTS,
                status=CheckStatus.FAIL,
                message=f"Security issues found: {'; '.join(issues[:3])}",
                details='\n'.join(issues + warnings) if warnings else '\n'.join(issues),
                remediation="Review bot.yaml security settings and OpenClaw-style pairing documentation",
                duration_ms=(time.time() - start) * 1000,
            )
        elif warnings:
            return CheckResult(
                id="bot_security",
                title="Bot Security Config",
                category=CheckCategory.BOTS,
                status=CheckStatus.WARN,
                message=f"Security recommendations: {len(warnings)} channel(s) could use stricter defaults",
                details='\n'.join(warnings),
                remediation="Consider allowlists for DM security and 'mention_only' group policy. See security docs for safe defaults.",
                duration_ms=(time.time() - start) * 1000,
            )
        else:
            return CheckResult(
                id="bot_security",
                title="Bot Security Config",
                category=CheckCategory.BOTS,
                status=CheckStatus.PASS,
                message="Security configuration looks good",
                duration_ms=(time.time() - start) * 1000,
            )
            
    except Exception as e:
        return CheckResult(
            id="bot_security",
            title="Bot Security Config",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Error checking security: {str(e)[:100]}",
            remediation="Fix bot.yaml syntax errors first",
            duration_ms=(time.time() - start) * 1000,
        )


def get_bot_checks() -> List[CheckResult]:
    """Run all bot-specific checks and return results."""
    return [
        check_bot_tokens(),
        check_bot_config(),
        check_bot_security(),
    ]
