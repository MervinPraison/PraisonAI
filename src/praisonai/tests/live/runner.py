"""Live smoke test runner for AI code editor verification.

This runner is CLI-FIRST: all scenarios execute via `praisonai code` or `praisonai chat`
CLI commands, NOT direct Python Agent API calls. This ensures we're testing the actual
CLI interface that users interact with.

Environment variables for automation:
- PRAISON_APPROVAL_MODE=auto  - Auto-approve all tool executions (required for non-interactive)
- PRAISONAI_LIVE_SMOKE=1      - Enable live smoke tests
- PRAISONAI_LIVE_MODEL        - Override default model (default: gpt-4o-mini)
- OPENAI_API_KEY              - Required for live tests
"""

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "ai_code_editor_fixture"
PRAISONAI_PATH = Path(__file__).parent.parent.parent.parent / "praisonai"
AGENTS_PATH = Path(__file__).parent.parent.parent.parent / "praisonai-agents"

DEFAULT_MODEL = os.environ.get("PRAISONAI_LIVE_MODEL", "gpt-4o-mini")


@dataclass
class ScenarioResult:
    """Result of a scenario execution."""
    name: str
    success: bool
    output: str
    error: str = ""
    file_diffs: dict = field(default_factory=dict)
    commands_run: List[str] = field(default_factory=list)
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    cli_command: str = ""


@dataclass
class Scenario:
    """A test scenario for AI code editor verification."""
    name: str
    description: str
    prompt: str
    acceptance_checks: List[Callable[[Path], tuple]]
    check_names: List[str]
    timeout: int = 120
    model: str = ""  # Empty means use DEFAULT_MODEL
    use_code_command: bool = True  # Use `praisonai code` vs `praisonai chat`


def is_live_smoke_enabled() -> bool:
    """Check if live smoke tests are enabled."""
    return os.environ.get("PRAISONAI_LIVE_SMOKE", "0") == "1"


def has_api_key() -> bool:
    """Check if OpenAI API key is available."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def mask_secrets(text: str) -> str:
    """Mask API keys and other secrets in output."""
    patterns = [
        (r'sk-[a-zA-Z0-9]{20,}', '[MASKED_API_KEY]'),
        (r'api[_-]?key["\s:=]+["\']?[a-zA-Z0-9-_]{20,}', 'api_key=[MASKED]'),
    ]
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def create_working_dir() -> Path:
    """Create a temporary working directory with fixture project."""
    work_dir = Path(tempfile.mkdtemp(prefix="praisonai_code_editor_"))
    if FIXTURE_PATH.exists():
        shutil.copytree(FIXTURE_PATH, work_dir / "project", dirs_exist_ok=True)
    return work_dir


def cleanup_working_dir(work_dir: Path) -> None:
    """Clean up temporary working directory."""
    if work_dir.exists() and str(work_dir).startswith(tempfile.gettempdir()):
        shutil.rmtree(work_dir, ignore_errors=True)


def get_file_snapshot(project_dir: Path) -> dict:
    """Get a snapshot of all Python files in the project."""
    snapshot = {}
    for py_file in project_dir.rglob("*.py"):
        rel_path = py_file.relative_to(project_dir)
        snapshot[str(rel_path)] = py_file.read_text()
    return snapshot


def compute_file_diffs(before: dict, after: dict) -> dict:
    """Compute diffs between two file snapshots."""
    diffs = {}
    all_files = set(before.keys()) | set(after.keys())
    for f in all_files:
        old = before.get(f, "")
        new = after.get(f, "")
        if old != new:
            diffs[f] = {"before": old, "after": new}
    return diffs


def build_cli_env(extra_env: Optional[dict] = None) -> dict:
    """Build environment for CLI subprocess with proper PYTHONPATH and approval mode."""
    run_env = os.environ.copy()
    
    # Set PYTHONPATH to include praisonai and praisonai-agents
    paths = []
    if PRAISONAI_PATH.exists():
        paths.append(str(PRAISONAI_PATH.parent))  # Parent of praisonai package
    if AGENTS_PATH.exists():
        paths.append(str(AGENTS_PATH))
    existing = run_env.get("PYTHONPATH", "")
    if existing:
        paths.append(existing)
    run_env["PYTHONPATH"] = ":".join(paths)
    
    # CRITICAL: Enable auto-approval for non-interactive execution
    run_env["PRAISON_APPROVAL_MODE"] = "auto"
    
    if extra_env:
        run_env.update(extra_env)
    
    return run_env


def run_command(
    cmd: List[str],
    cwd: Path,
    timeout: int = 60,
    env: Optional[dict] = None,
) -> tuple:
    """Run a command and return (exit_code, stdout, stderr)."""
    run_env = build_cli_env(env)
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
        )
        return result.returncode, mask_secrets(result.stdout), mask_secrets(result.stderr)
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def run_praisonai_cli(
    prompt: str,
    workspace: Path,
    model: str = "",
    use_code: bool = True,
    timeout: int = 120,
    extra_env: Optional[dict] = None,
) -> tuple:
    """
    Run praisonai CLI command and return (exit_code, stdout, stderr, cli_command).
    
    This is the CLI-FIRST approach: we invoke `python -m praisonai code` or 
    `python -m praisonai chat` as a subprocess, exactly as a user would.
    
    We use `python -m praisonai` instead of the `praisonai` entry point to ensure
    we're using the correct Python environment and package path.
    
    Args:
        prompt: The prompt to send to the AI
        workspace: Working directory for the command
        model: LLM model to use (empty = default)
        use_code: Use `praisonai code` (True) or `praisonai chat` (False)
        timeout: Command timeout in seconds
        extra_env: Additional environment variables
    
    Returns:
        (exit_code, stdout, stderr, cli_command_string)
    """
    import sys
    
    # Build CLI command using python -m for proper environment handling
    cmd = [sys.executable, "-m", "praisonai", "code" if use_code else "chat"]
    
    # Add model flag
    effective_model = model or DEFAULT_MODEL
    cmd.extend(["-m", effective_model])
    
    # Add workspace flag
    cmd.extend(["-w", str(workspace)])
    
    # Add the prompt as the final argument
    cmd.append(prompt)
    
    # Human-readable command for logging (using praisonai directly)
    cli_command = f"praisonai {'code' if use_code else 'chat'} -m {effective_model} -w {workspace} \"{prompt[:50]}...\""
    
    # Build environment
    run_env = build_cli_env(extra_env)
    
    try:
        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
        )
        return (
            result.returncode,
            mask_secrets(result.stdout),
            mask_secrets(result.stderr),
            cli_command,
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"CLI command timed out after {timeout}s", cli_command
    except Exception as e:
        return -1, "", str(e), cli_command


def run_pytest(project_dir: Path, test_filter: Optional[str] = None) -> tuple:
    """Run pytest and return (passed, output)."""
    cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
    if test_filter:
        cmd.extend(["-k", test_filter])
    exit_code, stdout, stderr = run_command(cmd, project_dir, timeout=60)
    output = stdout + stderr
    passed = exit_code == 0
    return passed, output


def run_ruff(project_dir: Path, fix: bool = False) -> tuple:
    """Run ruff linter and return (clean, output)."""
    cmd = ["python", "-m", "ruff", "check", "."]
    if fix:
        cmd.append("--fix")
    exit_code, stdout, stderr = run_command(cmd, project_dir, timeout=30)
    output = stdout + stderr
    clean = exit_code == 0
    return clean, output


def run_scenario(scenario: Scenario, work_dir: Path) -> ScenarioResult:
    """
    Run a single scenario using the CLI-FIRST approach.
    
    This executes `praisonai code` or `praisonai chat` as a subprocess,
    NOT direct Python Agent API calls. This ensures we're testing the
    actual CLI interface that users interact with.
    """
    project_dir = work_dir / "project"
    start_time = time.time()
    
    # Take snapshot before
    before_snapshot = get_file_snapshot(project_dir)
    
    # Run the CLI command
    exit_code, stdout, stderr, cli_command = run_praisonai_cli(
        prompt=scenario.prompt,
        workspace=project_dir,
        model=scenario.model,
        use_code=scenario.use_code_command,
        timeout=scenario.timeout,
    )
    
    output = stdout + stderr
    error = stderr if exit_code != 0 else ""
    
    # Take snapshot after
    after_snapshot = get_file_snapshot(project_dir)
    file_diffs = compute_file_diffs(before_snapshot, after_snapshot)
    
    # Run acceptance checks
    checks_passed = []
    checks_failed = []
    
    for check_fn, check_name in zip(scenario.acceptance_checks, scenario.check_names):
        try:
            passed, msg = check_fn(project_dir)
            if passed:
                checks_passed.append(check_name)
            else:
                checks_failed.append(f"{check_name}: {msg}")
        except Exception as e:
            checks_failed.append(f"{check_name}: {e}")
    
    duration = time.time() - start_time
    success = len(checks_failed) == 0
    
    return ScenarioResult(
        name=scenario.name,
        success=success,
        output=output,
        error=error,
        file_diffs=file_diffs,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        duration_seconds=duration,
        cli_command=cli_command,
    )
