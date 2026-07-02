"""
Gateway-specific doctor checks for PraisonAI.

Validates gateway/bot configuration, performs migrations, and checks security.
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

from ..models import CheckResult, CheckStatus, CheckCategory, CheckSeverity, DoctorConfig
from ..registry import register_check
from ._wrapper_checks import skip_if_no_wrapper


def _bots_config_schema():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.bots._config_schema")


@register_check(
    id="gateway_config_validation",
    title="Gateway Config Validation",
    description="Validate gateway/bot configuration files",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.HIGH,
)
def check_gateway_config_validation(config: DoctorConfig) -> CheckResult:
    """Validate gateway/bot configuration using canonical schema."""
    start = time.time()
    skipped = skip_if_no_wrapper("gateway_config_validation", "Gateway Config Validation", start=start)
    if skipped:
        return skipped
    
    # Check multiple possible config locations
    config_paths = []
    if hasattr(config, 'config_file') and config.config_file:
        config_paths.append(config.config_file)
    
    # Check common locations
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_paths.extend([
        resolve_bot_config_path("gateway.yaml"),
        resolve_bot_config_path("bot.yaml"),
        "gateway.yaml",
        "bot.yaml",
    ])
    
    # Find first existing config
    config_path = None
    for path in config_paths:
        if os.path.exists(path):
            config_path = path
            break
            
    if not config_path:
        return CheckResult(
            id="gateway_config_validation",
            title="Gateway Config Validation",
            category=CheckCategory.BOTS,
            status=CheckStatus.WARN,
            message="No gateway/bot config found",
            remediation="Run 'praisonai onboard' to create bot.yaml",
            duration_ms=(time.time() - start) * 1000,
        )
        
    try:
        load_and_validate_gateway_yaml = _bots_config_schema().load_and_validate_gateway_yaml
        validated_config = load_and_validate_gateway_yaml(config_path)
        
        channel_count = len(validated_config.channels)
        agent_count = 1 if validated_config.agent else 0
        if validated_config.agents:
            agent_count = len(validated_config.agents)
            
        return CheckResult(
            id="gateway_config_validation", 
            title="Gateway Config Validation",
            category=CheckCategory.BOTS,
            status=CheckStatus.PASS,
            message=f"{config_path} valid ({channel_count} channels, {agent_count} agents)",
            duration_ms=(time.time() - start) * 1000,
        )
    except ValueError as e:
        return CheckResult(
            id="gateway_config_validation",
            title="Gateway Config Validation",
            category=CheckCategory.BOTS,
            status=CheckStatus.FAIL,
            message=f"Invalid config: {str(e)[:100]}",
            details=str(e),
            remediation="Fix validation errors in your config file",
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as e:
        return CheckResult(
            id="gateway_config_validation",
            title="Gateway Config Validation",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Error validating config: {str(e)[:100]}",
            remediation="Check config file syntax",
            duration_ms=(time.time() - start) * 1000,
        )


@register_check(
    id="gateway_security",
    title="Gateway Security Settings",
    description="Check gateway security configuration",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.HIGH,
)
def check_gateway_security(config: DoctorConfig) -> CheckResult:
    """Check gateway security settings for safe defaults."""
    start = time.time()
    skipped = skip_if_no_wrapper("gateway_security", "Gateway Security Settings", start=start)
    if skipped:
        return skipped
    
    # Find config file
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_path = None
    for path in [resolve_bot_config_path("gateway.yaml"), resolve_bot_config_path("bot.yaml"), "gateway.yaml", "bot.yaml"]:
        if os.path.exists(path):
            config_path = path
            break
            
    if not config_path:
        return CheckResult(
            id="gateway_security",
            title="Gateway Security Settings",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message="No config found - security check skipped",
            duration_ms=(time.time() - start) * 1000,
        )
        
    try:
        load_and_validate_gateway_yaml = _bots_config_schema().load_and_validate_gateway_yaml
        validated_config = load_and_validate_gateway_yaml(config_path)
        
        security_issues = []
        warnings = []
        
        for channel_name, channel in validated_config.channels.items():
            # Check for open allowlists (CRITICAL)
            if not channel.allowed_users and not channel.allowlist and not channel.blocklist:
                security_issues.append(
                    f"{channel_name}: No user restrictions - bot responds to EVERYONE!"
                )
                
            # Check for overly permissive group policies (WARNING)
            if channel.group_policy == "respond_all":
                warnings.append(
                    f"{channel_name}: Using 'respond_all' - consider 'mention_only'"
                )
                
            # Check for missing tokens
            if not channel.token:
                security_issues.append(
                    f"{channel_name}: No token configured"
                )
                
        # Check gateway auth token
        if not os.environ.get("GATEWAY_AUTH_TOKEN"):
            warnings.append("GATEWAY_AUTH_TOKEN not set - gateway has no authentication")
            
        if security_issues:
            return CheckResult(
                id="gateway_security",
                title="Gateway Security Settings",
                category=CheckCategory.BOTS,
                status=CheckStatus.FAIL,
                message=f"Critical security issues: {len(security_issues)} problem(s)",
                details="\n".join(security_issues + warnings),
                remediation="Add allowed_users to restrict bot access. Use 'mention_only' for groups.",
                duration_ms=(time.time() - start) * 1000,
            )
        elif warnings:
            return CheckResult(
                id="gateway_security",
                title="Gateway Security Settings",
                category=CheckCategory.BOTS,
                status=CheckStatus.WARN,
                message=f"Security recommendations: {len(warnings)} improvement(s)",
                details="\n".join(warnings),
                remediation="Consider stricter security settings",
                duration_ms=(time.time() - start) * 1000,
            )
        else:
            return CheckResult(
                id="gateway_security",
                title="Gateway Security Settings",
                category=CheckCategory.BOTS,
                status=CheckStatus.PASS,
                message="Security configuration looks good",
                duration_ms=(time.time() - start) * 1000,
            )
            
    except Exception as e:
        return CheckResult(
            id="gateway_security",
            title="Gateway Security Settings",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Error checking security: {str(e)[:100]}",
            remediation="Fix config errors first",
            duration_ms=(time.time() - start) * 1000,
        )


@register_check(
    id="gateway_config_migration",
    title="Gateway Config Migration",
    description="Check if config needs migration to canonical format",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.MEDIUM,
)
def check_gateway_config_migration(config: DoctorConfig) -> CheckResult:
    """Check if configuration needs migration to canonical format."""
    start = time.time()
    skipped = skip_if_no_wrapper("gateway_config_migration", "Gateway Config Migration", start=start)
    if skipped:
        return skipped
    
    # Find config file
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_path = None
    for path in [resolve_bot_config_path("gateway.yaml"), resolve_bot_config_path("bot.yaml"), "gateway.yaml", "bot.yaml"]:
        if os.path.exists(path):
            config_path = path
            break
            
    if not config_path:
        return CheckResult(
            id="gateway_config_migration",
            title="Gateway Config Migration",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message="No config found - migration check skipped",
            duration_ms=(time.time() - start) * 1000,
        )
        
    try:
        import yaml
        import copy
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        
        # Deep copy to preserve original for comparison
        original = copy.deepcopy(raw)
            
        migrate_legacy_config = _bots_config_schema().migrate_legacy_config
        migrated = migrate_legacy_config(copy.deepcopy(original))
        
        # Check if migration changed anything
        if migrated != original:
            changes = []
            
            # Detect specific migrations
            if "platform" in raw and "token" in raw and "channels" not in raw:
                changes.append("Single-bot format can be migrated to multi-channel format")
                
            if "platforms" in raw and "channels" not in raw:
                changes.append("BotOS platforms format can be migrated to channels format")
                
            # Check for string allowed_users
            if "channels" in raw:
                for channel_name, channel in raw["channels"].items():
                    if isinstance(channel.get("allowed_users"), str):
                        changes.append(f"{channel_name}: allowed_users string → list migration available")
                        
            return CheckResult(
                id="gateway_config_migration",
                title="Gateway Config Migration",
                category=CheckCategory.BOTS,
                status=CheckStatus.WARN,
                message=f"Config can be migrated: {len(changes)} change(s)",
                details="\n".join(changes),
                remediation="Run 'praisonai gateway migrate' to update config to latest format",
                duration_ms=(time.time() - start) * 1000,
            )
        else:
            return CheckResult(
                id="gateway_config_migration",
                title="Gateway Config Migration",
                category=CheckCategory.BOTS,
                status=CheckStatus.PASS,
                message="Config uses current format",
                duration_ms=(time.time() - start) * 1000,
            )
            
    except Exception as e:
        return CheckResult(
            id="gateway_config_migration",
            title="Gateway Config Migration",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Error checking migration: {str(e)[:100]}",
            remediation="Fix config syntax errors first",
            duration_ms=(time.time() - start) * 1000,
        )


@register_check(
    id="gateway_env_substitution",
    title="Gateway Environment Variables",
    description="Check environment variable substitution in config",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.MEDIUM,
)
def check_gateway_env_substitution(config: DoctorConfig) -> CheckResult:
    """Check that environment variables referenced in config are set."""
    start = time.time()
    skipped = skip_if_no_wrapper("gateway_env_substitution", "Gateway Environment Variables", start=start)
    if skipped:
        return skipped
    
    # Find config file
    from praisonai_code.cli._paths import resolve_bot_config_path
    config_path = None
    for path in [resolve_bot_config_path("gateway.yaml"), resolve_bot_config_path("bot.yaml"), "gateway.yaml", "bot.yaml"]:
        if os.path.exists(path):
            config_path = path
            break
            
    if not config_path:
        return CheckResult(
            id="gateway_env_substitution",
            title="Gateway Environment Variables",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message="No config found - env check skipped",
            duration_ms=(time.time() - start) * 1000,
        )
        
    try:
        import re
        from praisonai_code.cli.utils.env_utils import load_env_file
        
        # Load .env file first to ensure all env vars are available
        try:
            load_env_file()
        except:
            pass  # .env file might not exist, continue anyway
        
        with open(config_path) as f:
            content = f.read()
            
        # Find all ${VAR} references
        env_refs = re.findall(r'\$\{([^}]+)\}', content)
        
        if not env_refs:
            return CheckResult(
                id="gateway_env_substitution",
                title="Gateway Environment Variables",
                category=CheckCategory.BOTS,
                status=CheckStatus.PASS,
                message="No environment variables referenced",
                duration_ms=(time.time() - start) * 1000,
            )
            
        # Check which are set
        missing = []
        found = []
        for env_var in sorted(set(env_refs)):
            if env_var in os.environ:
                found.append(env_var)
            else:
                missing.append(env_var)
                
        if missing:
            return CheckResult(
                id="gateway_env_substitution",
                title="Gateway Environment Variables",
                category=CheckCategory.BOTS,
                status=CheckStatus.FAIL,
                message=f"Missing environment variables: {len(missing)}",
                details=f"Not set: {', '.join(missing)}",
                remediation=f"Set missing variables: {' '.join(f'export {v}=...' for v in missing)}",
                duration_ms=(time.time() - start) * 1000,
            )
        else:
            return CheckResult(
                id="gateway_env_substitution",
                title="Gateway Environment Variables",
                category=CheckCategory.BOTS,
                status=CheckStatus.PASS,
                message=f"All {len(found)} environment variables are set",
                duration_ms=(time.time() - start) * 1000,
            )
            
    except Exception as e:
        return CheckResult(
            id="gateway_env_substitution",
            title="Gateway Environment Variables",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Error checking env vars: {str(e)[:100]}",
            remediation="Check config file access",
            duration_ms=(time.time() - start) * 1000,
        )