"""
Runtime configuration migration checks.

Checks for legacy cli_backend configuration and provides migration to
the new model-scoped runtime configuration.
"""

import os
import yaml
import json
import shutil
import copy
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

from ..models import CheckCategory, CheckResult, CheckStatus, CheckSeverity, DoctorConfig
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
    
    # Serialize first to ensure it's valid YAML
    try:
        yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False, indent=2)
    except Exception as e:
        raise ValueError(f"Failed to serialize configuration to YAML: {e}")
    
    if create_backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_name(f"{config_path.stem}.backup.{timestamp}.yaml")
        shutil.copy2(config_path, backup_path)
        backup_info = f" (backup: {backup_path.name})"
    
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    
    return backup_info


@register_check(
    id="runtime.config_migration",
    title="Runtime Configuration Migration",
    description="Check for legacy cli_backend configuration and migrate to model-scoped runtime",
    category=CheckCategory.RUNTIME
)
def check_runtime_config_migration(config: DoctorConfig) -> CheckResult:
    """
    Check for legacy cli_backend configuration and provide migration path.
    
    Args:
        config: DoctorConfig instance with fix and execute flags
    """
    try:
        config_path = _find_config_file(config.config_file)
        
        # If user specified a file and it doesn't exist, return ERROR
        if config.config_file and not config_path:
            return CheckResult(
                id="runtime.config_file_found",
                title="Configuration File Check",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.ERROR,
                message=f"Specified configuration file not found: {config.config_file}",
                severity=CheckSeverity.HIGH
            )
        elif not config_path:
            return CheckResult(
                id="runtime.config_file_found",
                title="Configuration File Check",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.SKIP,
                message="No configuration file found to check",
                details="Searched for: agents.yaml, agents.yml, config.yaml, config.yml in current directory",
                severity=CheckSeverity.INFO
            )
        
        # Load configuration
        try:
            yaml_config = _load_config(config_path)
        except ValueError as e:
            return CheckResult(
                id="runtime.config_load",
                title="Configuration Load",
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
                id="runtime.config_migration",
                title="Runtime Configuration Migration",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.ERROR,
                message=f"Could not import migration tools: {e}",
                details="Ensure praisonaiagents is installed: pip install praisonaiagents",
                severity=CheckSeverity.HIGH
            )
        
        # Collect findings from all registered rules
        findings = collect_findings(yaml_config)
        
        if not findings:
            return CheckResult(
                id="runtime.config_migration",
                title="Runtime Configuration Migration",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.PASS,
                message=f"Configuration is up to date: {config_path.name}",
                details="No legacy cli_backend fields found",
                severity=CheckSeverity.INFO
            )
        
        # Prepare details about findings
        details = []
        for finding in findings:
            details.append(f"• {finding.description}")
            if finding.details:
                details.append(f"  {finding.details}")
        
        # If not fixing, just report findings
        if not config.fix:
            return CheckResult(
                id="runtime.config_migration",
                title="Runtime Configuration Migration",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.WARN,
                message=f"Found {len(findings)} legacy configuration(s) in {config_path.name}",
                details="\n".join(details),
                severity=CheckSeverity.MEDIUM,
                fix_suggestion="Run 'praisonai doctor runtime --fix' to migrate automatically"
            )
        
        # Apply fixes (dry-run or execute)
        try:
            migrated_config = apply_fixes(yaml_config)
            
            # Show what would be changed
            if config.fix and not config.execute:
                # Dry-run mode
                preview = []
                preview.append(f"Would migrate {len(findings)} legacy configuration(s):")
                preview.extend(details)
                preview.append("\nTo apply changes, run with --fix --execute")
                
                return CheckResult(
                    id="runtime.config_migration",
                    title="Runtime Configuration Migration (Dry-Run)",
                    category=CheckCategory.RUNTIME,
                    status=CheckStatus.INFO,
                    message=f"Preview of changes for {config_path.name}",
                    details="\n".join(preview),
                    severity=CheckSeverity.INFO
                )
            
            # Execute the migration
            if config.fix and config.execute:
                backup_info = _save_config(config_path, migrated_config)
                
                return CheckResult(
                    id="runtime.config_migration",
                    title="Runtime Configuration Migration",
                    category=CheckCategory.RUNTIME,
                    status=CheckStatus.PASS,
                    message=f"Successfully migrated {len(findings)} legacy configuration(s)",
                    details=f"Updated: {config_path.name}{backup_info}",
                    severity=CheckSeverity.INFO
                )
            
        except Exception as e:
            return CheckResult(
                id="runtime.config_migration",
                title="Runtime Configuration Migration",
                category=CheckCategory.RUNTIME,
                status=CheckStatus.ERROR,
                message=f"Failed to apply migration: {e}",
                severity=CheckSeverity.HIGH
            )
    
    except Exception as e:
        return CheckResult(
            id="runtime.config_migration",
            title="Runtime Configuration Migration",
            category=CheckCategory.RUNTIME,
            status=CheckStatus.ERROR,
            message=f"Runtime migration check failed: {e}",
            severity=CheckSeverity.HIGH
        )