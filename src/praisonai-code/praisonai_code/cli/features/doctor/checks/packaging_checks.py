"""
Packaging checks for the Doctor CLI module.

Validates PraisonAI packaging and entry point configurations to diagnose 
Windows daemon invocation issues (python -m praisonai vs praisonai console script).
"""

import os
import subprocess
import sys
import platform
import shutil

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


@register_check(
    id="praisonai_package_structure",
    title="PraisonAI Package Structure",
    description="Check if praisonai package has correct structure for both -m and script execution",
    category=CheckCategory.PACKAGING,
    severity=CheckSeverity.HIGH,
)
def check_praisonai_package_structure(config: DoctorConfig) -> CheckResult:
    """Check PraisonAI package structure and entry points."""
    issues = []
    metadata = {}
    
    try:
        from praisonai_code._wrapper_bridge import import_wrapper_module, wrapper_available

        if not wrapper_available():
            issues.append("praisonai wrapper not installed")
            metadata["import_error"] = "wrapper not available"
        else:
            praisonai = import_wrapper_module("praisonai")
            package_path = praisonai.__file__
            if package_path:
                package_dir = os.path.dirname(package_path)
                metadata["package_path"] = package_path
                metadata["package_dir"] = package_dir

                # Check for __main__.py
                main_py_path = os.path.join(package_dir, "__main__.py")
                if os.path.exists(main_py_path):
                    metadata["has_main_py"] = True
                    metadata["main_py_path"] = main_py_path
                else:
                    issues.append("Missing __main__.py - python -m praisonai will not work")
                    metadata["has_main_py"] = False
            else:
                issues.append("praisonai.__file__ is None - namespace package detected")

    except ImportError as e:
        issues.append(f"Cannot import praisonai: {e}")
        metadata["import_error"] = str(e)
    
    # Check console script availability
    praisonai_script = shutil.which("praisonai")
    if praisonai_script:
        metadata["console_script_path"] = praisonai_script
        metadata["has_console_script"] = True
    else:
        issues.append("praisonai console script not found in PATH")
        metadata["has_console_script"] = False
    
    if not issues:
        return CheckResult(
            id="praisonai_package_structure",
            title="PraisonAI Package Structure",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.PASS,
            message="Package structure is correct for both -m and script execution",
            metadata=metadata,
        )
    else:
        return CheckResult(
            id="praisonai_package_structure",
            title="PraisonAI Package Structure",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.FAIL,
            message=f"Package structure issues: {'; '.join(issues)}",
            metadata=metadata,
        )


@register_check(
    id="python_module_execution",
    title="Python Module Execution",
    description="Test if python -m praisonai works correctly",
    category=CheckCategory.PACKAGING,
    severity=CheckSeverity.HIGH,
)
def check_python_module_execution(config: DoctorConfig) -> CheckResult:
    """Test python -m praisonai execution."""
    metadata = {"test_command": f"{sys.executable} -m praisonai --version"}
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "--version"],
            capture_output=True,
            text=True,
            timeout=config.timeout,
        )
        
        metadata["return_code"] = result.returncode
        metadata["stdout"] = result.stdout.strip()
        metadata["stderr"] = result.stderr.strip()
        
        if result.returncode == 0:
            return CheckResult(
                id="python_module_execution",
                title="Python Module Execution",
                category=CheckCategory.PACKAGING,
                status=CheckStatus.PASS,
                message=f"python -m praisonai works: {result.stdout.strip() or result.stderr.strip()}",
                metadata=metadata,
            )
        else:
            return CheckResult(
                id="python_module_execution",
                title="Python Module Execution",
                category=CheckCategory.PACKAGING,
                status=CheckStatus.FAIL,
                message=f"python -m praisonai failed with exit code {result.returncode}",
                metadata=metadata,
            )
            
    except subprocess.TimeoutExpired:
        return CheckResult(
            id="python_module_execution",
            title="Python Module Execution",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.FAIL,
            message=f"python -m praisonai timed out (>{config.timeout}s)",
            metadata=metadata,
        )
    except Exception as e:
        metadata["exception"] = str(e)
        return CheckResult(
            id="python_module_execution",
            title="Python Module Execution",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.FAIL,
            message=f"python -m praisonai execution failed: {e}",
            metadata=metadata,
        )


@register_check(
    id="console_script_execution",
    title="Console Script Execution",
    description="Test if praisonai console script works correctly",
    category=CheckCategory.PACKAGING,
    severity=CheckSeverity.HIGH,
)
def check_console_script_execution(config: DoctorConfig) -> CheckResult:
    """Test praisonai console script execution."""
    praisonai_script = shutil.which("praisonai")
    
    if not praisonai_script:
        return CheckResult(
            id="console_script_execution",
            title="Console Script Execution",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.FAIL,
            message="praisonai console script not found in PATH",
            metadata={"script_path": None},
        )
    
    metadata = {
        "script_path": praisonai_script,
        "test_command": f"{praisonai_script} --version"
    }
    
    try:
        result = subprocess.run(
            [praisonai_script, "--version"],
            capture_output=True,
            text=True,
            timeout=config.timeout,
        )
        
        metadata["return_code"] = result.returncode
        metadata["stdout"] = result.stdout.strip()
        metadata["stderr"] = result.stderr.strip()
        
        if result.returncode == 0:
            return CheckResult(
                id="console_script_execution",
                title="Console Script Execution",
                category=CheckCategory.PACKAGING,
                status=CheckStatus.PASS,
                message=f"praisonai console script works: {result.stdout.strip() or result.stderr.strip()}",
                metadata=metadata,
            )
        else:
            return CheckResult(
                id="console_script_execution",
                title="Console Script Execution",
                category=CheckCategory.PACKAGING,
                status=CheckStatus.FAIL,
                message=f"praisonai console script failed with exit code {result.returncode}",
                metadata=metadata,
            )
            
    except subprocess.TimeoutExpired:
        return CheckResult(
            id="console_script_execution",
            title="Console Script Execution",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.FAIL,
            message=f"praisonai console script timed out (>{config.timeout}s)",
            metadata=metadata,
        )
    except Exception as e:
        metadata["exception"] = str(e)
        return CheckResult(
            id="console_script_execution",
            title="Console Script Execution",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.FAIL,
            message=f"praisonai console script execution failed: {e}",
            metadata=metadata,
        )


@register_check(
    id="windows_daemon_context",
    title="Windows Daemon Context",
    description="Check Windows-specific daemon execution context",
    category=CheckCategory.PACKAGING,
    severity=CheckSeverity.MEDIUM,
)
def check_windows_daemon_context(config: DoctorConfig) -> CheckResult:
    """Check Windows daemon execution context and provide recommendations."""
    metadata = {
        "platform": platform.system(),
        "is_windows": platform.system().lower() == "windows"
    }
    
    if not metadata["is_windows"]:
        return CheckResult(
            id="windows_daemon_context",
            title="Windows Daemon Context",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.SKIP,
            message="Not Windows - check skipped",
            metadata=metadata,
        )
    
    recommendations = []
    warnings = []
    
    # Check if in virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    metadata["in_venv"] = in_venv
    metadata["sys_prefix"] = sys.prefix
    metadata["sys_executable"] = sys.executable
    
    if in_venv:
        venv_scripts_dir = os.path.join(sys.prefix, "Scripts")
        metadata["venv_scripts_dir"] = venv_scripts_dir
        
        # Check if Scripts dir exists and has praisonai.exe
        if os.path.exists(venv_scripts_dir):
            praisonai_exe = os.path.join(venv_scripts_dir, "praisonai.exe")
            metadata["venv_praisonai_exe_exists"] = os.path.exists(praisonai_exe)
            
            if os.path.exists(praisonai_exe):
                recommendations.append(f"For daemons, use absolute path: {praisonai_exe}")
            else:
                warnings.append("praisonai.exe not found in venv Scripts directory")
        else:
            warnings.append("Virtual environment Scripts directory not found")
    else:
        warnings.append("Not in virtual environment - daemon may use global Python")
    
    # Check Python executable type
    if "WindowsApps" in sys.executable:
        warnings.append("Using Microsoft Store Python - may cause daemon issues")
        recommendations.append("Consider using python.org Python or conda for daemons")
    
    # Check encoding environment
    pythonioencoding = os.environ.get("PYTHONIOENCODING")
    metadata["pythonioencoding"] = pythonioencoding
    
    if not pythonioencoding:
        recommendations.append("Set PYTHONIOENCODING=utf-8 for daemon encoding safety")
    
    # Generate canonical daemon command
    praisonai_script = shutil.which("praisonai")
    if praisonai_script:
        canonical_command = f'"{praisonai_script}"'
    else:
        canonical_command = f'"{sys.executable}" -m praisonai'
    
    metadata["canonical_daemon_command"] = canonical_command
    recommendations.append(f"Recommended daemon command: {canonical_command}")
    
    if warnings:
        status = CheckStatus.WARN
        message = f"Windows daemon context has warnings: {'; '.join(warnings[:2])}"
    else:
        status = CheckStatus.PASS
        message = "Windows daemon context is good"
    
    if recommendations:
        metadata["recommendations"] = recommendations
    
    return CheckResult(
        id="windows_daemon_context",
        title="Windows Daemon Context",
        category=CheckCategory.PACKAGING,
        status=status,
        message=message,
        metadata=metadata,
    )


@register_check(
    id="packaging_metadata",
    title="Packaging Metadata",
    description="Check PraisonAI package installation metadata",
    category=CheckCategory.PACKAGING,
    severity=CheckSeverity.LOW,
)
def check_packaging_metadata(config: DoctorConfig) -> CheckResult:
    """Check PraisonAI package installation metadata."""
    metadata = {}
    issues = []
    
    try:
        from praisonai_code._wrapper_bridge import import_wrapper_module, wrapper_available

        if not wrapper_available():
            issues.append("praisonai wrapper not installed")
            metadata["import_error"] = "wrapper not available"
        else:
            praisonai = import_wrapper_module("praisonai")
            metadata["praisonai_file"] = getattr(praisonai, "__file__", None)
            metadata["praisonai_version"] = getattr(praisonai, "__version__", "unknown")

            # Check if installed via pip (using modern importlib.metadata)
            try:
                try:
                    from importlib.metadata import distribution, PackageNotFoundError
                except ImportError:
                    # Python < 3.8 fallback
                    from importlib_metadata import distribution, PackageNotFoundError

                try:
                    dist = distribution("praisonai")
                    metadata["pip_version"] = dist.version
                    metadata["pip_location"] = str(dist.locate_file(""))
                    metadata["pip_installed"] = True
                except PackageNotFoundError:
                    metadata["pip_installed"] = False
                    issues.append("Package not found in pip registry (editable install?)")
            except ImportError:
                metadata["importlib_metadata_available"] = False

            # Check for editable install markers
            if praisonai.__file__:
                package_dir = os.path.dirname(praisonai.__file__)
                # Look for .egg-link or similar editable install markers
                site_packages = []
                try:
                    import site
                    site_packages.extend(site.getsitepackages())
                    if hasattr(site, 'getusersitepackages'):
                        site_packages.append(site.getusersitepackages())
                except Exception as e:
                    metadata["site_packages_probe_error"] = str(e)

                is_editable = False
                for sp in site_packages:
                    if sp and os.path.exists(sp):
                        # Check for both case variations of egg-link files
                        for egg_link_name in ("praisonai.egg-link", "PraisonAI.egg-link"):
                            egg_link = os.path.join(sp, egg_link_name)
                            if os.path.exists(egg_link):
                                is_editable = True
                                metadata["editable_install"] = True
                                metadata["egg_link_path"] = egg_link
                                break
                        if is_editable:
                            break

                        # Check for modern editable install markers (PEP 660)
                        try:
                            for file in os.listdir(sp):
                                if file.startswith("__editable__") and "praisonai" in file.lower() and file.endswith(".pth"):
                                    is_editable = True
                                    metadata["editable_install"] = True
                                    metadata["editable_pth_path"] = os.path.join(sp, file)
                                    break
                        except OSError:
                            pass
                        if is_editable:
                            break

                if not is_editable:
                    metadata["editable_install"] = False

    except ImportError as e:
        issues.append(f"Cannot import praisonai: {e}")
        metadata["import_error"] = str(e)
    
    if not issues:
        return CheckResult(
            id="packaging_metadata",
            title="Packaging Metadata",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.PASS,
            message="Package metadata is accessible",
            metadata=metadata,
        )
    else:
        return CheckResult(
            id="packaging_metadata",
            title="Packaging Metadata",
            category=CheckCategory.PACKAGING,
            status=CheckStatus.WARN,
            message=f"Package metadata issues: {'; '.join(issues)}",
            metadata=metadata,
        )