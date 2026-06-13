"""
Runtime configuration migration checks.

Checks for legacy cli_backend configuration and provides migration to
the new model-scoped runtime configuration.
"""

import os
import yaml
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

from ..models import CheckCategory, CheckResult, CheckStatus, CheckSeverity
from ..registry import register_check


def _find_config_file(config_file: Optional[str] = None) -> Optional[Path]:
    """Find the configuration file to check."""
    if config_file:
        path = Path(config_file)
        return path if path.exists() else None
    
    # Search for common config files
    current_dir = Path.cwd()
    for filename in ["agents.yaml", "agents.yml", "config.yaml", "config.yml"]:
        path = current_dir / filename
        if path.exists():
            return path
    
    return None


def _load_config(config_path: Path) -> Dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise ValueError(f"Failed to load config file: {e}")


def _save_config(config_path: Path, config: Dict, create_backup: bool = True) -> str:
    """Save configuration to YAML file with optional backup."""
    backup_info = ""
    
    if create_backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_name(f"{config_path.stem}.backup.{timestamp}.yaml")
        shutil.copy2(config_path, backup_path)
        backup_info = f" (backup: {backup_path.name})"
    
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, indent=2)
    
    return backup_info


@register_check
def check_runtime_config_migration(config_file: Optional[str] = None, 
                                   fix: bool = False, 
                                   execute: bool = False) -> CheckResult:
    """
    Check for legacy cli_backend configuration and provide migration path.
    
    Args:
        config_file: Path to config file (if not provided, searches for common names)
        fix: Whether to apply fixes
        execute: Whether to actually execute the fixes (vs dry-run)
    """
    try:
        config_path = _find_config_file(config_file)
        if not config_path:
            return CheckResult(
                id="runtime.config_file_found",
                title="Configuration File Detection",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.SKIP,
                message="No configuration file found to check",
                details="Searched for: agents.yaml, agents.yml, config.yaml, config.yml in current directory",
                severity=CheckSeverity.INFO
            )
        
        # Load configuration
        try:
            config = _load_config(config_path)
        except ValueError as e:
            return CheckResult(
                id="runtime.config_load",
                title="Configuration File Loading",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.ERROR,
                message=f"Failed to load configuration file: {e}",
                severity=CheckSeverity.HIGH
            )
        
        # Import the migration functionality from praisonaiagents
        try:
            from praisonaiagents.runtime import collect_findings, apply_fixes
        except ImportError as e:
            return CheckResult(
                id="runtime.migration_unavailable",
                title="Migration System Availability",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.ERROR,
                message="Runtime migration system not available",
                details=f"Import error: {e}",
                remediation="Ensure praisonaiagents is properly installed with runtime migration support",
                severity=CheckSeverity.CRITICAL
            )
        
        # Collect findings
        findings = collect_findings(config)
        
        if not findings:
            return CheckResult(
                id="runtime.cli_backend_migration",
                title="Legacy cli_backend Configuration",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.PASS,
                message=f"No legacy cli_backend configuration found in {config_path.name}",
                severity=CheckSeverity.INFO
            )
        
        # Format findings
        finding_details = []
        for finding in findings:
            location = finding.context.get('location', 'unknown') if finding.context else 'unknown'
            value = finding.context.get('value', 'unknown') if finding.context else 'unknown'
            finding_details.append(f"- {location}: cli_backend={value}")
        
        details_text = f"Found {len(findings)} legacy cli_backend usage(s):\n" + "\n".join(finding_details)
        
        # Apply fixes if requested
        if fix and execute:
            try:
                fixed_config = apply_fixes(config)
                backup_info = _save_config(config_path, fixed_config, create_backup=True)
                
                return CheckResult(
                    id="runtime.cli_backend_migration",
                    title="Legacy cli_backend Configuration", 
                    category=CheckCategory.RUNTIME,
                    status=CheckStatus.PASS,
                    message=f"Migrated {len(findings)} legacy cli_backend configuration(s) in {config_path.name}{backup_info}",
                    details=details_text,
                    metadata={"findings_count": len(findings), "config_file": str(config_path)}
                )
            except Exception as e:
                return CheckResult(
                    id="runtime.cli_backend_migration",
                    title="Legacy cli_backend Configuration",
                    category=CheckCategory.RUNTIME,
                    status=CheckStatus.ERROR,
                    message=f"Failed to apply migration fixes: {e}",
                    details=details_text,
                    severity=CheckSeverity.HIGH
                )
        elif fix:
            # Dry run - show what would be done
            try:
                fixed_config = apply_fixes(config)
                preview = yaml.dump(fixed_config, default_flow_style=False, sort_keys=False, indent=2)
                
                return CheckResult(
                    id="runtime.cli_backend_migration",
                    title="Legacy cli_backend Configuration",
                    category=CheckCategory.RUNTIME,
                    status=CheckStatus.WARN,
                    message=f"Found {len(findings)} legacy cli_backend configuration(s) that can be migrated",
                    details=f"{details_text}\n\nPreview of migrated configuration:\n```yaml\n{preview}```",
                    remediation=f"Run: praisonai doctor runtime --fix --execute to apply migration",
                    metadata={"findings_count": len(findings), "config_file": str(config_path)}
                )
            except Exception as e:
                return CheckResult(
                    id="runtime.cli_backend_migration",
                    title="Legacy cli_backend Configuration",
                    category=CheckCategory.RUNTIME,
                    status=CheckStatus.ERROR,
                    message=f"Failed to preview migration fixes: {e}",
                    details=details_text,
                    severity=CheckSeverity.HIGH
                )
        else:
            # Just report the findings
            remediation_text = f"Run: praisonai doctor runtime --fix to preview migration, or --fix --execute to apply"
            
            return CheckResult(
                id="runtime.cli_backend_migration",
                title="Legacy cli_backend Configuration",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.WARN,
                message=f"Found {len(findings)} legacy cli_backend configuration(s) that should be migrated",
                details=details_text,
                remediation=remediation_text,
                severity=CheckSeverity.MEDIUM,
                metadata={"findings_count": len(findings), "config_file": str(config_path)}
            )
            
    except Exception as e:
        return CheckResult(
            id="runtime.cli_backend_migration",
            title="Legacy cli_backend Configuration",
            category=CheckCategory.RUNTIME,
            status=CheckStatus.ERROR,
            message=f"Runtime migration check failed: {e}",
            severity=CheckSeverity.HIGH
        )