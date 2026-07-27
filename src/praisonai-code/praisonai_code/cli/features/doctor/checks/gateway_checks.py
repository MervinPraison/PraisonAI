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
from ._wrapper_checks import (
    skip_if_no_wrapper,
    skip_if_no_bot_package,
    bots_config_schema as _bots_config_schema,
)


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
    skipped = skip_if_no_bot_package("gateway_config_validation", "Gateway Config Validation", start=start)
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
    skipped = skip_if_no_bot_package("gateway_security", "Gateway Security Settings", start=start)
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
    skipped = skip_if_no_bot_package("gateway_config_migration", "Gateway Config Migration", start=start)
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


def _find_gateway_config_path(config: DoctorConfig) -> Optional[str]:
    """Resolve gateway/bot config path, honouring ``--file`` first."""
    config_paths: List[str] = []
    if getattr(config, "config_file", None):
        config_paths.append(config.config_file)

    from praisonai_code.cli._paths import resolve_bot_config_path

    config_paths.extend([
        resolve_bot_config_path("gateway.yaml"),
        resolve_bot_config_path("bot.yaml"),
        "gateway.yaml",
        "bot.yaml",
    ])

    for path in config_paths:
        if path and os.path.exists(path):
            return path
    return None


@register_check(
    id="gateway_shell_readiness",
    title="Gateway Shell Readiness",
    description="Validate allow_shell wiring offline (no LLM)",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.HIGH,
)
def check_gateway_shell_readiness(config: DoctorConfig) -> CheckResult:
    """Offline shell wiring check for channels with ``allow_shell: true``."""
    start = time.time()
    skipped = skip_if_no_wrapper(
        "gateway_shell_readiness", "Gateway Shell Readiness", start=start
    )
    if skipped:
        return skipped
    skipped = skip_if_no_bot_package(
        "gateway_shell_readiness", "Gateway Shell Readiness", start=start
    )
    if skipped:
        return skipped

    config_path = _find_gateway_config_path(config)
    if not config_path:
        return CheckResult(
            id="gateway_shell_readiness",
            title="Gateway Shell Readiness",
            category=CheckCategory.BOTS,
            status=CheckStatus.WARN,
            message="No gateway/bot config found",
            remediation="Run 'praisonai onboard' or pass --file /path/to/bot.yaml",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from praisonai_code._bot_bridge import import_bot_module

        preflight = import_bot_module("praisonai_bot.gateway.preflight")
        result = preflight.run_shell_readiness_check(config_path)
    except Exception as exc:
        return CheckResult(
            id="gateway_shell_readiness",
            title="Gateway Shell Readiness",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Shell readiness check failed: {str(exc)[:100]}",
            duration_ms=(time.time() - start) * 1000,
        )

    if result.ok:
        return CheckResult(
            id="gateway_shell_readiness",
            title="Gateway Shell Readiness",
            category=CheckCategory.BOTS,
            status=CheckStatus.PASS,
            message=result.message,
            duration_ms=(time.time() - start) * 1000,
        )

    return CheckResult(
        id="gateway_shell_readiness",
        title="Gateway Shell Readiness",
        category=CheckCategory.BOTS,
        status=CheckStatus.FAIL,
        message=result.message,
        details="\n".join(result.issues) if result.issues else None,
        remediation="Fix allow_shell / auto_approve_shell settings in bot.yaml",
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    id="gateway_channel_probe",
    title="Gateway Channel Probe",
    description="Live credential probe for configured channels",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.HIGH,
    requires_deep=True,
)
def check_gateway_channel_probe(config: DoctorConfig) -> CheckResult:
    """Live platform credential probe (``auth.test``, ``getMe``, etc.)."""
    import asyncio

    start = time.time()
    skipped = skip_if_no_wrapper(
        "gateway_channel_probe", "Gateway Channel Probe", start=start
    )
    if skipped:
        return skipped
    skipped = skip_if_no_bot_package(
        "gateway_channel_probe", "Gateway Channel Probe", start=start
    )
    if skipped:
        return skipped

    config_path = _find_gateway_config_path(config)
    if not config_path:
        return CheckResult(
            id="gateway_channel_probe",
            title="Gateway Channel Probe",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message="No gateway/bot config found",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from praisonai_code._bot_bridge import import_bot_module

        preflight = import_bot_module("praisonai_bot.gateway.preflight")
        channels = preflight.load_channels_mapping(config_path)
        if not channels:
            return CheckResult(
                id="gateway_channel_probe",
                title="Gateway Channel Probe",
                category=CheckCategory.BOTS,
                status=CheckStatus.SKIP,
                message="No channels configured",
                duration_ms=(time.time() - start) * 1000,
            )
        results = asyncio.run(preflight.probe_channels(channels))
    except Exception as exc:
        return CheckResult(
            id="gateway_channel_probe",
            title="Gateway Channel Probe",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Probe failed: {str(exc)[:100]}",
            duration_ms=(time.time() - start) * 1000,
        )

    lines = []
    failed = []
    for name, probe in results.items():
        if getattr(probe, "ok", False):
            identity = getattr(probe, "bot_username", None) or ""
            detail = f"@{identity}" if identity else getattr(probe, "platform", name)
            lines.append(f"{name}: OK ({detail})")
        else:
            err = getattr(probe, "error", None) or "unknown error"
            lines.append(f"{name}: FAIL ({err})")
            failed.append(name)

    if failed:
        return CheckResult(
            id="gateway_channel_probe",
            title="Gateway Channel Probe",
            category=CheckCategory.BOTS,
            status=CheckStatus.FAIL,
            message=f"{len(failed)} channel probe(s) failed",
            details="\n".join(lines),
            remediation=(
                "Fix channel tokens or run: "
                f"praisonai gateway test --config {config_path}"
            ),
            duration_ms=(time.time() - start) * 1000,
        )

    return CheckResult(
        id="gateway_channel_probe",
        title="Gateway Channel Probe",
        category=CheckCategory.BOTS,
        status=CheckStatus.PASS,
        message=f"All {len(results)} channel probe(s) passed",
        details="\n".join(lines),
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    id="gateway_duplicate_services",
    title="Gateway Duplicate Services",
    description="Scan for competing gateway services and shared Slack tokens",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.HIGH,
    requires_deep=True,
)
def check_gateway_duplicate_services(config: DoctorConfig) -> CheckResult:
    """Detect duplicate LaunchAgents and shared token fingerprints."""
    start = time.time()
    skipped = skip_if_no_wrapper(
        "gateway_duplicate_services", "Gateway Duplicate Services", start=start
    )
    if skipped:
        return skipped
    skipped = skip_if_no_bot_package(
        "gateway_duplicate_services", "Gateway Duplicate Services", start=start
    )
    if skipped:
        return skipped

    config_path = _find_gateway_config_path(config)
    if not config_path:
        return CheckResult(
            id="gateway_duplicate_services",
            title="Gateway Duplicate Services",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message="No gateway/bot config found",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from praisonai_code._bot_bridge import import_bot_module

        preflight = import_bot_module("praisonai_bot.gateway.preflight")
        result = preflight.check_duplicates(config_path)
    except Exception as exc:
        return CheckResult(
            id="gateway_duplicate_services",
            title="Gateway Duplicate Services",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Duplicate scan failed: {str(exc)[:100]}",
            duration_ms=(time.time() - start) * 1000,
        )

    lines = list(result.warnings)
    for service in result.services:
        if service.running:
            lines.append(f"{service.label}: running (pid={service.pid})")

    if not result.ok:
        return CheckResult(
            id="gateway_duplicate_services",
            title="Gateway Duplicate Services",
            category=CheckCategory.BOTS,
            status=CheckStatus.WARN,
            message="Possible competing gateway or shared token detected",
            details="\n".join(lines) if lines else None,
            remediation=(
                "Compare SLACK_APP_TOKEN across services; stop duplicate gateways "
                "before messaging Slack."
            ),
            duration_ms=(time.time() - start) * 1000,
        )

    return CheckResult(
        id="gateway_duplicate_services",
        title="Gateway Duplicate Services",
        category=CheckCategory.BOTS,
        status=CheckStatus.PASS,
        message="No duplicate gateway conflicts detected",
        details="\n".join(lines) if lines else None,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    id="gateway_no_inbound_recent",
    title="Gateway Recent Inbound",
    description="Check for recent inbound delivery in gateway logs",
    category=CheckCategory.BOTS,
    severity=CheckSeverity.MEDIUM,
    requires_deep=True,
)
def check_gateway_no_inbound_recent(config: DoctorConfig) -> CheckResult:
    """Warn when no inbound mentions appear in recent gateway logs."""
    start = time.time()
    skipped = skip_if_no_wrapper(
        "gateway_no_inbound_recent", "Gateway Recent Inbound", start=start
    )
    if skipped:
        return skipped
    skipped = skip_if_no_bot_package(
        "gateway_no_inbound_recent", "Gateway Recent Inbound", start=start
    )
    if skipped:
        return skipped

    config_path = _find_gateway_config_path(config)
    if not config_path:
        return CheckResult(
            id="gateway_no_inbound_recent",
            title="Gateway Recent Inbound",
            category=CheckCategory.BOTS,
            status=CheckStatus.SKIP,
            message="No gateway/bot config found",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from praisonai_code._bot_bridge import import_bot_module

        preflight = import_bot_module("praisonai_bot.gateway.preflight")
        inbound = preflight.check_inbound(config_path, since="10m")
    except Exception as exc:
        return CheckResult(
            id="gateway_no_inbound_recent",
            title="Gateway Recent Inbound",
            category=CheckCategory.BOTS,
            status=CheckStatus.ERROR,
            message=f"Inbound check failed: {str(exc)[:100]}",
            duration_ms=(time.time() - start) * 1000,
        )

    if inbound.ok:
        detail = f"{inbound.mentions_in_window} mention(s) in last 10m"
        if inbound.last_mention_at:
            detail += f"; last at {inbound.last_mention_at}"
        return CheckResult(
            id="gateway_no_inbound_recent",
            title="Gateway Recent Inbound",
            category=CheckCategory.BOTS,
            status=CheckStatus.PASS,
            message=detail,
            duration_ms=(time.time() - start) * 1000,
        )

    return CheckResult(
        id="gateway_no_inbound_recent",
        title="Gateway Recent Inbound",
        category=CheckCategory.BOTS,
        status=CheckStatus.WARN,
        message="No inbound delivery in recent logs",
        details=inbound.hint,
        remediation=(
            "Send a Slack @mention to your bot, then run: "
            f"praisonai gateway test --config {config_path} --check-inbound --since 5m"
        ),
        duration_ms=(time.time() - start) * 1000,
    )