"""
Permissions checks for the Doctor CLI module.

Validates filesystem permissions for PraisonAI directories.
"""

import os
import tempfile
from pathlib import Path

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


def _check_dir_writable(path: Path) -> tuple:
    """Check if a directory is writable."""
    try:
        if not path.exists():
            return False, "does not exist"
        
        if not path.is_dir():
            return False, "not a directory"
        
        # Try to create a temp file
        test_file = path / ".praison_write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            return True, "writable"
        except PermissionError:
            return False, "permission denied"
        except Exception as e:
            return False, str(e)
    except Exception as e:
        return False, str(e)


@register_check(
    id="permissions_home_praison",
    title="~/.praison Directory",
    description="Check ~/.praison directory permissions",
    category=CheckCategory.PERMISSIONS,
    severity=CheckSeverity.MEDIUM,
)
def check_permissions_home_praison(config: DoctorConfig) -> CheckResult:
    """Check ~/.praison directory permissions."""
    praison_dir = Path.home() / ".praison"
    
    if not praison_dir.exists():
        # Try to create it
        try:
            praison_dir.mkdir(parents=True, exist_ok=True)
            return CheckResult(
                id="permissions_home_praison",
                title="~/.praison Directory",
                category=CheckCategory.PERMISSIONS,
                status=CheckStatus.PASS,
                message="~/.praison created successfully",
                metadata={"path": str(praison_dir)},
            )
        except PermissionError:
            return CheckResult(
                id="permissions_home_praison",
                title="~/.praison Directory",
                category=CheckCategory.PERMISSIONS,
                status=CheckStatus.FAIL,
                message="Cannot create ~/.praison directory",
                remediation="Check home directory permissions",
                severity=CheckSeverity.HIGH,
            )
    
    writable, reason = _check_dir_writable(praison_dir)
    
    if writable:
        return CheckResult(
            id="permissions_home_praison",
            title="~/.praison Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.PASS,
            message=f"~/.praison is writable",
            metadata={"path": str(praison_dir)},
        )
    else:
        return CheckResult(
            id="permissions_home_praison",
            title="~/.praison Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.FAIL,
            message=f"~/.praison is not writable: {reason}",
            remediation="Fix permissions: chmod 755 ~/.praison",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="permissions_project_praison",
    title=".praison Directory (Project)",
    description="Check project .praison directory permissions",
    category=CheckCategory.PERMISSIONS,
    severity=CheckSeverity.LOW,
)
def check_permissions_project_praison(config: DoctorConfig) -> CheckResult:
    """Check project .praison directory permissions."""
    praison_dir = Path.cwd() / ".praison"
    
    if not praison_dir.exists():
        return CheckResult(
            id="permissions_project_praison",
            title=".praison Directory (Project)",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.SKIP,
            message="No .praison directory in current project",
        )
    
    writable, reason = _check_dir_writable(praison_dir)
    
    if writable:
        return CheckResult(
            id="permissions_project_praison",
            title=".praison Directory (Project)",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.PASS,
            message=".praison is writable",
            metadata={"path": str(praison_dir)},
        )
    else:
        return CheckResult(
            id="permissions_project_praison",
            title=".praison Directory (Project)",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.WARN,
            message=f".praison is not writable: {reason}",
            remediation="Fix permissions or use ~/.praison instead",
        )


@register_check(
    id="permissions_temp_dir",
    title="Temp Directory",
    description="Check temp directory permissions",
    category=CheckCategory.PERMISSIONS,
    severity=CheckSeverity.MEDIUM,
)
def check_permissions_temp_dir(config: DoctorConfig) -> CheckResult:
    """Check temp directory permissions."""
    temp_dir = Path(tempfile.gettempdir())
    
    try:
        # Try to create a temp file
        with tempfile.NamedTemporaryFile(delete=True) as f:
            f.write(b"test")
        
        return CheckResult(
            id="permissions_temp_dir",
            title="Temp Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.PASS,
            message=f"Temp directory writable: {temp_dir}",
            metadata={"path": str(temp_dir)},
        )
    except Exception as e:
        return CheckResult(
            id="permissions_temp_dir",
            title="Temp Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.FAIL,
            message=f"Temp directory not writable: {e}",
            remediation="Check TMPDIR environment variable and permissions",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="permissions_cwd",
    title="Current Working Directory",
    description="Check current directory permissions",
    category=CheckCategory.PERMISSIONS,
    severity=CheckSeverity.INFO,
)
def check_permissions_cwd(config: DoctorConfig) -> CheckResult:
    """Check current directory permissions."""
    cwd = Path.cwd()
    
    writable, reason = _check_dir_writable(cwd)
    
    if writable:
        return CheckResult(
            id="permissions_cwd",
            title="Current Working Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.PASS,
            message=f"Current directory writable: {cwd}",
        )
    else:
        return CheckResult(
            id="permissions_cwd",
            title="Current Working Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.WARN,
            message=f"Current directory not writable: {reason}",
            details="Some features may not work without write access",
        )


@register_check(
    id="permissions_config_dir",
    title="Config Directory",
    description="Check ~/.config/praison directory",
    category=CheckCategory.PERMISSIONS,
    severity=CheckSeverity.LOW,
)
def check_permissions_config_dir(config: DoctorConfig) -> CheckResult:
    """Check ~/.config/praison directory."""
    config_dir = Path.home() / ".config" / "praison"
    
    if not config_dir.exists():
        # Check if we can create it
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            return CheckResult(
                id="permissions_config_dir",
                title="Config Directory",
                category=CheckCategory.PERMISSIONS,
                status=CheckStatus.PASS,
                message="~/.config/praison created successfully",
            )
        except Exception:
            return CheckResult(
                id="permissions_config_dir",
                title="Config Directory",
                category=CheckCategory.PERMISSIONS,
                status=CheckStatus.SKIP,
                message="~/.config/praison does not exist (will use ~/.praison)",
            )
    
    writable, reason = _check_dir_writable(config_dir)
    
    if writable:
        return CheckResult(
            id="permissions_config_dir",
            title="Config Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.PASS,
            message="~/.config/praison is writable",
        )
    else:
        return CheckResult(
            id="permissions_config_dir",
            title="Config Directory",
            category=CheckCategory.PERMISSIONS,
            status=CheckStatus.WARN,
            message=f"~/.config/praison not writable: {reason}",
        )
