"""
Environment checks for the Doctor CLI module.

Validates Python version, packages, API keys, and environment variables.
"""

import os
import platform
import shutil
import sys
from typing import List, Optional

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


@register_check(
    id="python_version",
    title="Python Version",
    description="Check Python version is 3.9+",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.CRITICAL,
)
def check_python_version(config: DoctorConfig) -> CheckResult:
    """Check Python version is 3.9+."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    if version.major >= 3 and version.minor >= 9:
        return CheckResult(
            id="python_version",
            title="Python Version",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"Python {version_str} (>= 3.9 required)",
            metadata={"version": version_str, "executable": sys.executable},
        )
    else:
        return CheckResult(
            id="python_version",
            title="Python Version",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.FAIL,
            message=f"Python {version_str} found, but 3.9+ required",
            remediation="Upgrade Python to version 3.9 or higher",
            severity=CheckSeverity.CRITICAL,
        )


@register_check(
    id="praisonai_package",
    title="PraisonAI Package",
    description="Check praisonai package is installed",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.CRITICAL,
)
def check_praisonai_package(config: DoctorConfig) -> CheckResult:
    """Check praisonai package is installed."""
    try:
        from praisonai_code._version import get_package_version
        version = get_package_version()
        return CheckResult(
            id="praisonai_package",
            title="PraisonAI Package",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"praisonai-code {version} installed",
            metadata={"version": version},
        )
    except ImportError as e:
        return CheckResult(
            id="praisonai_package",
            title="PraisonAI Package",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.FAIL,
            message="praisonai package not found",
            details=str(e),
            remediation="Install with: pip install praisonai",
            severity=CheckSeverity.CRITICAL,
        )


@register_check(
    id="praisonaiagents_package",
    title="PraisonAI Agents Package",
    description="Check praisonaiagents package is installed",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.CRITICAL,
)
def check_praisonaiagents_package(config: DoctorConfig) -> CheckResult:
    """Check praisonaiagents package is installed."""
    try:
        import praisonaiagents
        # praisonaiagents does not expose __version__ at module level yet, so
        # prefer importlib.metadata (which reads the installed dist-info) and
        # fall back to the attribute for forward-compat.
        version = getattr(praisonaiagents, "__version__", None)
        if not version:
            try:
                from importlib.metadata import version as _pkg_version
                version = _pkg_version("praisonaiagents")
            except Exception:
                version = "unknown"
        return CheckResult(
            id="praisonaiagents_package",
            title="PraisonAI Agents Package",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"praisonaiagents {version} installed",
            metadata={"version": version},
        )
    except ImportError as e:
        return CheckResult(
            id="praisonaiagents_package",
            title="PraisonAI Agents Package",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.FAIL,
            message="praisonaiagents package not found",
            details=str(e),
            remediation="Install with: pip install praisonaiagents",
            severity=CheckSeverity.CRITICAL,
        )


@register_check(
    id="openai_api_key",
    title="OpenAI API Key",
    description="Check OPENAI_API_KEY is configured",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.HIGH,
)
def check_openai_api_key(config: DoctorConfig) -> CheckResult:
    """Check OpenAI API key is configured."""
    key = os.environ.get("OPENAI_API_KEY", "")
    
    if key:
        # Mask the key for display
        if config.show_keys and len(key) > 12:
            masked = f"{key[:4]}...{key[-4:]}"
        else:
            masked = "***configured***"
        
        # Basic validation
        if key.startswith("sk-") or key.startswith("sk-proj-"):
            return CheckResult(
                id="openai_api_key",
                title="OpenAI API Key",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message=f"OPENAI_API_KEY configured ({masked})",
                metadata={"masked_key": masked},
            )
        else:
            return CheckResult(
                id="openai_api_key",
                title="OpenAI API Key",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.WARN,
                message=f"OPENAI_API_KEY set but format unexpected ({masked})",
                remediation="Verify the API key format is correct",
            )
    else:
        # Check for alternative providers
        alternatives = []
        if os.environ.get("ANTHROPIC_API_KEY"):
            alternatives.append("ANTHROPIC_API_KEY")
        if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
            alternatives.append("GOOGLE/GEMINI_API_KEY")
        if os.environ.get("OLLAMA_HOST") or shutil.which("ollama"):
            alternatives.append("Ollama")
        
        if alternatives:
            return CheckResult(
                id="openai_api_key",
                title="OpenAI API Key",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.WARN,
                message=f"OPENAI_API_KEY not set, but alternatives found: {', '.join(alternatives)}",
                details="OpenAI is the default provider. Other providers require explicit configuration.",
            )
        else:
            return CheckResult(
                id="openai_api_key",
                title="OpenAI API Key",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.FAIL,
                message="OPENAI_API_KEY not configured and no alternative providers found",
                remediation="Run 'praisonai setup' to configure API keys, or set OPENAI_API_KEY environment variable",
                severity=CheckSeverity.HIGH,
            )


@register_check(
    id="anthropic_api_key",
    title="Anthropic API Key",
    description="Check ANTHROPIC_API_KEY is configured",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
)
def check_anthropic_api_key(config: DoctorConfig) -> CheckResult:
    """Check Anthropic API key is configured."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    
    if key:
        if config.show_keys and len(key) > 12:
            masked = f"{key[:4]}...{key[-4:]}"
        else:
            masked = "***configured***"
        
        return CheckResult(
            id="anthropic_api_key",
            title="Anthropic API Key",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"ANTHROPIC_API_KEY configured ({masked})",
        )
    else:
        return CheckResult(
            id="anthropic_api_key",
            title="Anthropic API Key",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.SKIP,
            message="ANTHROPIC_API_KEY not set (optional)",
        )


@register_check(
    id="google_api_key",
    title="Google/Gemini API Key",
    description="Check GOOGLE_API_KEY or GEMINI_API_KEY is configured",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
)
def check_google_api_key(config: DoctorConfig) -> CheckResult:
    """Check Google/Gemini API key is configured."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    
    if key:
        if config.show_keys and len(key) > 12:
            masked = f"{key[:4]}...{key[-4:]}"
        else:
            masked = "***configured***"
        
        return CheckResult(
            id="google_api_key",
            title="Google/Gemini API Key",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"Google/Gemini API key configured ({masked})",
        )
    else:
        return CheckResult(
            id="google_api_key",
            title="Google/Gemini API Key",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.SKIP,
            message="GOOGLE_API_KEY/GEMINI_API_KEY not set (optional)",
        )


@register_check(
    id="os_info",
    title="Operating System",
    description="Check operating system information",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.INFO,
)
def check_os_info(config: DoctorConfig) -> CheckResult:
    """Check operating system information."""
    os_name = platform.system()
    os_version = platform.release()
    arch = platform.machine()
    
    return CheckResult(
        id="os_info",
        title="Operating System",
        category=CheckCategory.ENVIRONMENT,
        status=CheckStatus.PASS,
        message=f"{os_name} {os_version} ({arch})",
        metadata={
            "os_name": os_name,
            "os_version": os_version,
            "architecture": arch,
        },
    )


@register_check(
    id="virtual_env",
    title="Virtual Environment",
    description="Check if running in a virtual environment",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.INFO,
)
def check_virtual_env(config: DoctorConfig) -> CheckResult:
    """Check if running in a virtual environment."""
    venv = os.environ.get("VIRTUAL_ENV")
    conda_env = os.environ.get("CONDA_DEFAULT_ENV")
    
    if venv:
        return CheckResult(
            id="virtual_env",
            title="Virtual Environment",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"Running in venv: {os.path.basename(venv)}",
            metadata={"venv_path": venv},
        )
    elif conda_env:
        return CheckResult(
            id="virtual_env",
            title="Virtual Environment",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"Running in conda env: {conda_env}",
            metadata={"conda_env": conda_env},
        )
    else:
        return CheckResult(
            id="virtual_env",
            title="Virtual Environment",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message="Not running in a virtual environment",
            remediation="Consider using a virtual environment for isolation",
        )


@register_check(
    id="git_available",
    title="Git",
    description="Check if git is available",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
)
def check_git_available(config: DoctorConfig) -> CheckResult:
    """Check if git is available."""
    git_path = shutil.which("git")
    
    if git_path:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = result.stdout.strip() if result.returncode == 0 else "unknown"
            return CheckResult(
                id="git_available",
                title="Git",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message=f"Git available: {version}",
                metadata={"path": git_path},
            )
        except Exception:
            return CheckResult(
                id="git_available",
                title="Git",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message=f"Git available at {git_path}",
            )
    else:
        return CheckResult(
            id="git_available",
            title="Git",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message="Git not found in PATH",
            remediation="Install git for version control features",
        )


@register_check(
    id="docker_available",
    title="Docker",
    description="Check if Docker is available",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
)
def check_docker_available(config: DoctorConfig) -> CheckResult:
    """Check if Docker is available."""
    docker_path = shutil.which("docker")
    
    if docker_path:
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return CheckResult(
                    id="docker_available",
                    title="Docker",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.PASS,
                    message=f"Docker available: {version}",
                    metadata={"path": docker_path},
                )
        except Exception:
            pass
        
        return CheckResult(
            id="docker_available",
            title="Docker",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message="Docker found but not responding",
            remediation="Ensure Docker daemon is running",
        )
    else:
        return CheckResult(
            id="docker_available",
            title="Docker",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.SKIP,
            message="Docker not found (optional)",
        )


@register_check(
    id="npx_available",
    title="npx (Node.js)",
    description="Check if npx is available for MCP servers",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
)
def check_npx_available(config: DoctorConfig) -> CheckResult:
    """Check if npx is available for MCP servers."""
    npx_path = shutil.which("npx")
    
    if npx_path:
        return CheckResult(
            id="npx_available",
            title="npx (Node.js)",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"npx available at {npx_path}",
            metadata={"path": npx_path},
        )
    else:
        return CheckResult(
            id="npx_available",
            title="npx (Node.js)",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message="npx not found (required for some MCP servers)",
            remediation="Install Node.js to use MCP servers that require npx",
        )


def _probe_optional_package(package: str) -> bool:
    """Attempt to import a single optional package.

    Returns True if the import succeeds. Raises ``ImportError`` if the package
    is not installed, or any other exception if the import itself fails (e.g. a
    broken C extension). Kept as a module-level helper so it can be dispatched
    to a daemon worker thread with a per-package timeout (see
    ``check_optional_deps``).
    """
    __import__(package)
    return True


@register_check(
    id="optional_deps",
    title="Optional Dependencies",
    description="Check availability of optional dependencies",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.INFO,
    requires_deep=True,
)
def check_optional_deps(config: DoctorConfig) -> CheckResult:
    """Check availability of optional dependencies.

    Imports are dispatched to daemon worker threads with an individual
    per-package timeout so that a single slow or hanging optional import (e.g.
    ``chromadb`` or ``crawl4ai``) cannot block the entire check and trip the
    engine-wide timeout. Packages that exceed the per-package budget are
    reported as ``slow`` rather than failing the whole check.

    Daemon threads (rather than a ``ThreadPoolExecutor``) are used deliberately:
    a pool's worker threads are joined by its internal ``atexit`` handler at
    interpreter shutdown even after ``shutdown(wait=False)``, so a truly
    hanging import would still stall CLI exit. Daemon threads are abandoned on
    exit, so a hanging import can never block the process from terminating.
    """
    import time
    import threading

    optional_packages = [
        ("chromadb", "Knowledge/RAG features"),
        ("mem0ai", "Memory features"),
        ("litellm", "Multi-provider LLM support"),
        ("praisonaiui", "aiui (Chat/Dashboard UI)"),
        ("gradio", "Gradio UI"),
        ("crawl4ai", "Web crawling"),
        ("tavily", "Tavily search"),
        ("duckduckgo_search", "DuckDuckGo search"),
    ]

    # Reserve a slice of the overall check budget for each package. The engine
    # gives this check ``config.timeout`` seconds total; keep the per-package
    # cap comfortably below that so the aggregate stays within budget even when
    # several imports are slow.
    per_package_timeout = max(1.0, min(3.0, config.timeout / 4))

    available = []
    missing = []
    broken = []
    slow = []

    # Probe each import on its own daemon thread. Each thread records its own
    # outcome; the main thread waits at most ``per_package_timeout`` (bounded by
    # the overall check budget) for each to finish. A thread that is still
    # running past its deadline is abandoned: because it is a daemon it will not
    # block interpreter/CLI shutdown, unlike ThreadPoolExecutor workers which
    # are joined by an atexit handler even after ``shutdown(wait=False)``.
    outcomes: dict[str, tuple[str, BaseException | None]] = {}
    threads: dict[str, threading.Thread] = {}

    def _run_probe(pkg: str) -> None:
        try:
            _probe_optional_package(pkg)
            outcomes[pkg] = ("available", None)
        except ImportError:
            outcomes[pkg] = ("missing", None)
        except Exception as exc:  # noqa: BLE001 - surface broken installs
            outcomes[pkg] = ("broken", exc)

    for package, _description in optional_packages:
        thread = threading.Thread(
            target=_run_probe,
            args=(package,),
            name=f"doctor-optdep-{package}",
            daemon=True,
        )
        threads[package] = thread
        thread.start()

    deadline = time.monotonic() + max(per_package_timeout, config.timeout * 0.8)
    for package, description in optional_packages:
        remaining = max(0.0, deadline - time.monotonic())
        wait_for = min(per_package_timeout, remaining) if remaining > 0 else 0.0
        threads[package].join(timeout=wait_for)

        if threads[package].is_alive():
            # Import is hanging or unusually slow; abandon the daemon thread
            # rather than let it block the whole deep-doctor pass.
            slow.append(f"{package} ({description})")
            continue

        status, _exc = outcomes.get(package, ("missing", None))
        if status == "available":
            available.append(package)
        elif status == "broken":
            broken.append(f"{package} ({description})")
        else:
            missing.append(f"{package} ({description})")

    details_parts = []
    if missing:
        details_parts.append(
            f"Missing: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
        )
    if broken:
        details_parts.append(f"Broken install: {', '.join(broken)}")
    if slow:
        details_parts.append(
            f"Slow (skipped after {per_package_timeout:.0f}s): {', '.join(slow)}"
        )

    message_parts = [f"{len(available)} optional packages available"]
    if missing:
        message_parts.append(f"{len(missing)} not installed")
    if broken:
        message_parts.append(f"{len(broken)} broken")
    if slow:
        message_parts.append(f"{len(slow)} slow/skipped")

    # A broken install is actionable (fix the install) so surface it as a
    # warning; missing/slow packages are informational and keep the check green.
    status = CheckStatus.WARN if broken else CheckStatus.PASS
    remediation = (
        f"Reinstall the broken optional package(s): {', '.join(broken)}"
        if broken
        else None
    )

    return CheckResult(
        id="optional_deps",
        title="Optional Dependencies",
        category=CheckCategory.ENVIRONMENT,
        status=status,
        message=", ".join(message_parts),
        details="; ".join(details_parts) or None,
        remediation=remediation,
        metadata={
            "available": available,
            "missing": missing,
            "broken": broken,
            "slow": slow,
        },
    )


@register_check(
    id="stale_packages",
    title="Stale Package Artifacts",
    description="Check for stale praisonaiagents artifacts in site-packages",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.CRITICAL,
)
def check_stale_packages(config: DoctorConfig) -> CheckResult:
    """
    Check for stale praisonaiagents artifacts in site-packages.
    
    This detects namespace package shadowing issues where a stale directory
    in site-packages (without __init__.py) shadows the real package.
    """
    import site
    
    stale_dirs = []
    
    # Check all site-packages directories
    try:
        site_packages = site.getsitepackages()
    except AttributeError:
        # Some environments don't have getsitepackages
        site_packages = []
    
    # Also check user site-packages
    user_site = site.getusersitepackages() if hasattr(site, 'getusersitepackages') else None
    if user_site:
        site_packages = list(site_packages) + [user_site]
    
    for sp in site_packages:
        praisonai_dir = os.path.join(sp, 'praisonaiagents')
        if os.path.isdir(praisonai_dir):
            init_path = os.path.join(praisonai_dir, '__init__.py')
            if not os.path.exists(init_path):
                # This is a stale namespace package directory
                stale_dirs.append(praisonai_dir)
    
    if stale_dirs:
        return CheckResult(
            id="stale_packages",
            title="Stale Package Artifacts",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.FAIL,
            message=f"Found {len(stale_dirs)} stale praisonaiagents directory(ies)",
            details=f"Stale directories: {', '.join(stale_dirs)}",
            remediation=(
                "Remove stale directories to fix import errors:\n"
                f"  rm -rf {stale_dirs[0]}\n"
                "Then reinstall: pip install praisonaiagents"
            ),
            severity=CheckSeverity.CRITICAL,
            metadata={"stale_dirs": stale_dirs},
        )
    
    # Also verify the package loads correctly (not as namespace)
    try:
        import praisonaiagents
        if praisonaiagents.__file__ is None:
            return CheckResult(
                id="stale_packages",
                title="Stale Package Artifacts",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.FAIL,
                message="praisonaiagents loaded as namespace package",
                details="__file__ is None, indicating namespace package shadowing",
                remediation=(
                    "Remove stale praisonaiagents directory from site-packages:\n"
                    "  rm -rf $(python -c \"import site; print(site.getsitepackages()[0])\")/praisonaiagents/\n"
                    "Then reinstall: pip install praisonaiagents"
                ),
                severity=CheckSeverity.CRITICAL,
            )
    except ImportError:
        pass  # Package not installed - handled by praisonaiagents_package check
    
    return CheckResult(
        id="stale_packages",
        title="Stale Package Artifacts",
        category=CheckCategory.ENVIRONMENT,
        status=CheckStatus.PASS,
        message="No stale package artifacts found",
    )


@register_check(
    id="model_env_vars",
    title="Model Configuration",
    description="Check model-related environment variables",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.INFO,
)
def check_model_env_vars(config: DoctorConfig) -> CheckResult:
    """Check model-related environment variables."""
    model_vars = {
        "MODEL_NAME": os.environ.get("MODEL_NAME"),
        "OPENAI_MODEL_NAME": os.environ.get("OPENAI_MODEL_NAME"),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL"),
        "OPENAI_API_BASE": os.environ.get("OPENAI_API_BASE"),
    }
    
    configured = {k: v for k, v in model_vars.items() if v}
    
    if configured:
        details = ", ".join(f"{k}={v}" for k, v in configured.items())
        return CheckResult(
            id="model_env_vars",
            title="Model Configuration",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"Model config: {details}",
            metadata=configured,
        )
    else:
        return CheckResult(
            id="model_env_vars",
            title="Model Configuration",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="Using default model configuration (gpt-4o-mini)",
            metadata={"default_model": "gpt-4o-mini"},
        )
