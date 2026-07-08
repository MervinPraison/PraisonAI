"""
Bot-specific doctor checks for PraisonAI.

Registers checks for bot tokens, config validation, and channel probes.
"""

from __future__ import annotations

import os
import time
from typing import List

from ..models import CheckResult, CheckStatus, CheckCategory, CheckSeverity, DoctorConfig
from ..registry import register_check
from ._wrapper_checks import (
    skip_if_no_wrapper,
    skip_if_no_bot_package,
    bots_config_schema as _bots_config_schema,
)


@register_check(
    id="bot_tokens",
    title="Bot Tokens",
    description="Check bot token environment variables",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.MEDIUM,
)
def check_bot_tokens(config: DoctorConfig) -> CheckResult:
    """Check bot token environment variables."""
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_path = getattr(config, 'config_file', None) or resolve_bot_config_path("bot.yaml")
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


@register_check(
    id="bot_config",
    title="Bot Config",
    description="Check bot.yaml exists and is valid",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.MEDIUM,
)
def check_bot_config(config: DoctorConfig) -> CheckResult:
    """Check bot.yaml exists and is valid."""
    start = time.time()
    skipped = skip_if_no_wrapper("bot_config", "Bot Config", start=start)
    if skipped:
        return skipped
    skipped = skip_if_no_bot_package("bot_config", "Bot Config", start=start)
    if skipped:
        return skipped
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_path = getattr(config, 'config_file', None) or resolve_bot_config_path("bot.yaml")
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
        load_and_validate_bot_yaml = _bots_config_schema().load_and_validate_bot_yaml
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


@register_check(
    id="bot_security",
    title="Bot Security Config", 
    description="Check bot security configuration for safe defaults",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.HIGH,
)
def check_bot_security(config: DoctorConfig) -> CheckResult:
    """Check bot security configuration for safe defaults."""
    start = time.time()
    skipped = skip_if_no_wrapper("bot_security", "Bot Security Config", start=start)
    if skipped:
        return skipped
    skipped = skip_if_no_bot_package("bot_security", "Bot Security Config", start=start)
    if skipped:
        return skipped
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_path = getattr(config, 'config_file', None) or resolve_bot_config_path("bot.yaml")
    channel_warnings = []
    global_warnings = []
    
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
        config = _bots_config_schema().load_and_validate_bot_yaml(config_path)
        
        # Check for risky configurations across channels
        for channel_name, channel_config in config.channels.items():
            # Check for missing allowlists in production-like setups
            if not channel_config.allowlist and not channel_config.blocklist:
                channel_warnings.append(f"{channel_name}: No allowlist/blocklist configured")
            
            # Check for overly permissive group policies
            if channel_config.group_policy == "respond_all":
                channel_warnings.append(f"{channel_name}: group_policy='respond_all' - consider 'mention_only' for security")
        
        # Check for missing gateway pairing settings 
        gateway_secret = os.environ.get("PRAISONAI_GATEWAY_SECRET")
        if not gateway_secret:
            global_warnings.append("PRAISONAI_GATEWAY_SECRET not set - pairing codes will not persist across restarts")
        
        # Determine status
        all_warnings = channel_warnings + global_warnings
        if all_warnings:
            channel_count = len(channel_warnings)
            global_count = len(global_warnings)
            
            if channel_count > 0 and global_count > 0:
                message = f"Security recommendations: {channel_count} channel(s) and {global_count} global setting(s) could be improved"
            elif channel_count > 0:
                message = f"Security recommendations: {channel_count} channel(s) could use stricter defaults"
            else:
                message = f"Security recommendations: {global_count} global setting(s) could be improved"
            
            return CheckResult(
                id="bot_security",
                title="Bot Security Config",
                category=CheckCategory.BOTS,
                status=CheckStatus.WARN,
                message=message,
                details='\n'.join(all_warnings),
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
            
    except ValueError as e:
        return CheckResult(
            id="bot_security",
            title="Bot Security Config",
            category=CheckCategory.BOTS,
            status=CheckStatus.FAIL,
            message=f"Invalid bot security config: {str(e)[:100]}",
            details=str(e)[:200],
            remediation="Fix bot.yaml security settings and re-run doctor",
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


@register_check(
    id="multi_channel_tokens",
    title="Multi-Channel Token Configuration", 
    description="Check for duplicate tokens across channels and validate multi-channel setup",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.MEDIUM,
)
def check_multi_channel_tokens(config: DoctorConfig) -> CheckResult:
    """Check multi-channel token configuration for duplicates and naming conventions."""
    start = time.time()
    skipped = skip_if_no_wrapper("multi_channel_tokens", "Multi-Channel Token Configuration", start=start)
    if skipped:
        return skipped
    skipped = skip_if_no_bot_package("multi_channel_tokens", "Multi-Channel Token Configuration", start=start)
    if skipped:
        return skipped
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_path = getattr(config, 'config_file', None) or resolve_bot_config_path("bot.yaml")
    
    # Check if bot.yaml exists
    if not os.path.exists(config_path):
        return CheckResult(
            id="multi_channel_tokens",
            title="Multi-Channel Token Configuration",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message=f"{config_path} not found - multi-channel check skipped",
            duration_ms=(time.time() - start) * 1000,
        )
    
    try:
        config_data = _bots_config_schema().load_and_validate_bot_yaml(config_path)
        
        warnings = []
        errors = []
        
        # Extract token environment variables from channels
        channel_tokens = {}  # env_var -> [channel_keys_using_it]
        channel_platforms = {}  # platform -> [channel_keys]
        
        for channel_name, channel_config in config_data.channels.items():
            platform = channel_config.platform
            token_ref = channel_config.token
            
            # Track platforms
            if platform not in channel_platforms:
                channel_platforms[platform] = []
            channel_platforms[platform].append(channel_name)
            
            # Extract environment variable from token reference like ${TELEGRAM_BOT_TOKEN}
            if token_ref and token_ref.startswith("${") and token_ref.endswith("}"):
                env_var = token_ref[2:-1]  # Remove ${ and }
                if env_var not in channel_tokens:
                    channel_tokens[env_var] = []
                channel_tokens[env_var].append(channel_name)
        
        # Check for duplicate token usage by env var reference
        for env_var, channels in channel_tokens.items():
            if len(channels) > 1:
                errors.append(f"Token {env_var} is used by multiple channels: {', '.join(channels)}")

        # Also check duplicate token usage by resolved token value
        token_value_to_channels = {}  # token_value -> [channel_keys]
        for env_var, channels in channel_tokens.items():
            token_value = os.environ.get(env_var)
            if token_value:
                token_value_to_channels.setdefault(token_value, []).extend(channels)

        for _, channels in token_value_to_channels.items():
            unique_channels = sorted(set(channels))
            if len(unique_channels) > 1:
                errors.append(
                    f"Same bot token value is used by multiple channels: {', '.join(unique_channels)}"
                )
        
        # Check for multi-platform channels with good naming conventions
        for platform, channels in channel_platforms.items():
            if len(channels) > 1:
                # Multiple channels on same platform - check naming convention
                for channel_name in channels:
                    channel_config = config_data.channels[channel_name]
                    token_ref = channel_config.token
                    if token_ref and token_ref.startswith("${") and token_ref.endswith("}"):
                        env_var = token_ref[2:-1]
                        
                        # Check if follows naming convention: PLATFORM_ROLE_BOT_TOKEN
                        expected_pattern = f"{platform.upper()}_"
                        if not env_var.startswith(expected_pattern) or not env_var.endswith("_BOT_TOKEN"):
                            warnings.append(f"Channel '{channel_name}' token '{env_var}' doesn't follow naming convention '{platform.upper()}_<ROLE>_BOT_TOKEN'")
        
        # Check for missing tokens
        missing_tokens = []
        for env_var in channel_tokens.keys():
            if not os.environ.get(env_var):
                missing_tokens.append(env_var)
        
        # Determine status
        if errors:
            return CheckResult(
                id="multi_channel_tokens",
                title="Multi-Channel Token Configuration",
                category=CheckCategory.BOTS,
                status=CheckStatus.FAIL,
                message=f"Token configuration errors: {len(errors)} duplicate(s) found",
                details='\n'.join(errors + warnings),
                remediation="Each channel must have a unique bot token. Create separate bots in @BotFather and use unique environment variables.",
                duration_ms=(time.time() - start) * 1000,
            )
        elif warnings or missing_tokens:
            all_issues = warnings + [f"Missing token: {token}" for token in missing_tokens]
            return CheckResult(
                id="multi_channel_tokens",
                title="Multi-Channel Token Configuration",
                category=CheckCategory.BOTS,
                status=CheckStatus.WARN,
                message=f"Multi-channel setup with {len(all_issues)} recommendation(s)",
                details='\n'.join(all_issues),
                remediation="Consider following the naming convention PLATFORM_ROLE_BOT_TOKEN for clarity.",
                duration_ms=(time.time() - start) * 1000,
            )
        else:
            channel_count = sum(len(channels) for channels in channel_platforms.values())
            return CheckResult(
                id="multi_channel_tokens",
                title="Multi-Channel Token Configuration",
                category=CheckCategory.BOTS,
                status=CheckStatus.PASS,
                message=f"Multi-channel configuration looks good ({channel_count} channels)",
                duration_ms=(time.time() - start) * 1000,
            )
            
    except Exception as e:
        return CheckResult(
            id="multi_channel_tokens",
            title="Multi-Channel Token Configuration",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Error checking multi-channel config: {str(e)[:100]}",
            remediation="Fix bot.yaml syntax errors first",
            duration_ms=(time.time() - start) * 1000,
        )


