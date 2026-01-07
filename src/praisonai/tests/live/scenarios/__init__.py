"""AI code editor scenario definitions.

Each scenario tests a specific AI code editor capability via CLI commands.
Scenarios use `praisonai code` by default (use_code_command=True).

Mandatory coverage (10+ scenarios):
1. Implement new module from spec + run pytest
2. Refactor messy function + run pytest + run ruff
3. Fix failing test by editing production code + rerun pytest
4. Add new CLI command + run it + assert output
5. Add type hints + run mypy (if configured)
6. Generate/update docs + run docs check
7. Use grep/glob to locate code and apply targeted change
8. Use multiedit to change multiple files
9. Use file attachment feature (or file path reference)
10. Use session continuation across multiple prompts
"""

from pathlib import Path
from typing import List, Optional
import subprocess

from ..runner import Scenario, build_cli_env


def check_pytest_passes(test_filter: Optional[str] = None):
    """Check that pytest passes for given filter."""
    def check(project_dir: Path) -> tuple:
        cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
        if test_filter:
            cmd.extend(["-k", test_filter])
        env = build_cli_env()
        result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, timeout=60, env=env)
        if result.returncode == 0:
            return True, "Tests passed"
        # Include more context in failure message
        output = result.stdout + result.stderr
        # Find the summary line
        info = ""
        for line in output.split("\n"):
            if "FAILED" in line or "passed" in line or "failed" in line:
                info += line + "\n"
        return False, f"Tests failed: info {info[-500:]}"
    return check


def check_file_contains(filepath: str, text: str):
    """Check that a file contains specific text."""
    def check(project_dir: Path) -> tuple:
        path = project_dir / filepath
        if not path.exists():
            return False, f"File {filepath} does not exist"
        content = path.read_text()
        if text in content:
            return True, f"Found '{text}' in {filepath}"
        return False, f"'{text}' not found in {filepath}"
    return check


def check_file_not_contains(filepath: str, text: str):
    """Check that a file does NOT contain specific text."""
    def check(project_dir: Path) -> tuple:
        path = project_dir / filepath
        if not path.exists():
            return False, f"File {filepath} does not exist"
        content = path.read_text()
        if text not in content:
            return True, f"'{text}' correctly removed from {filepath}"
        return False, f"'{text}' still present in {filepath}"
    return check


def check_function_exists(filepath: str, func_name: str):
    """Check that a function exists in a file."""
    def check(project_dir: Path) -> tuple:
        path = project_dir / filepath
        if not path.exists():
            return False, f"File {filepath} does not exist"
        content = path.read_text()
        if f"def {func_name}" in content:
            return True, f"Function {func_name} exists in {filepath}"
        return False, f"Function {func_name} not found in {filepath}"
    return check


def check_cli_command_works(cmd_args: List[str], expected_output: Optional[str] = None):
    """Check that a CLI command works."""
    def check(project_dir: Path) -> tuple:
        cmd = ["python", "-m", "mathlib.cli"] + cmd_args
        env = build_cli_env()
        result = subprocess.run(cmd, cwd=project_dir / "src", capture_output=True, text=True, timeout=30, env=env)
        if result.returncode != 0:
            return False, f"CLI command failed: {result.stderr}"
        if expected_output and expected_output not in result.stdout:
            return False, f"Expected '{expected_output}' in output, got: {result.stdout}"
        return True, "CLI command works"
    return check


def check_ruff_clean():
    """Check that ruff reports no errors."""
    def check(project_dir: Path) -> tuple:
        env = build_cli_env()
        result = subprocess.run(
            ["python", "-m", "ruff", "check", "."],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode == 0:
            return True, "Ruff clean"
        return False, f"Ruff errors: {result.stdout[:500]}"
    return check


def check_file_modified(filepath: str):
    """Check that a file was modified (exists and is non-empty)."""
    def check(project_dir: Path) -> tuple:
        path = project_dir / filepath
        if not path.exists():
            return False, f"File {filepath} does not exist"
        content = path.read_text()
        if len(content) > 0:
            return True, f"File {filepath} exists and has content"
        return False, f"File {filepath} is empty"
    return check


def check_grep_pattern(filepath: str, pattern: str):
    """Check that a file matches a grep pattern."""
    def check(project_dir: Path) -> tuple:
        import re
        path = project_dir / filepath
        if not path.exists():
            return False, f"File {filepath} does not exist"
        content = path.read_text()
        if re.search(pattern, content):
            return True, f"Pattern '{pattern}' found in {filepath}"
        return False, f"Pattern '{pattern}' not found in {filepath}"
    return check


SCENARIO_1_IMPLEMENT_CONVERTER = Scenario(
    name="implement_celsius_to_fahrenheit",
    description="Implement celsius_to_fahrenheit function and run tests until they pass",
    prompt="Implement the celsius_to_fahrenheit function in src/mathlib/converter.py. Formula: F = C * 9/5 + 32. Run pytest tests/test_converter.py -k celsius to verify. Fix until tests pass.",
    acceptance_checks=[
        check_function_exists("src/mathlib/converter.py", "celsius_to_fahrenheit"),
        check_grep_pattern("src/mathlib/converter.py", r"9.*5.*32|1\.8.*32"),  # Accept 9/5, 9.0/5.0, or 1.8
        check_pytest_passes("celsius"),
    ],
    check_names=["function_exists", "has_formula", "tests_pass"],
)

SCENARIO_2_FIX_DIVIDE_BUG = Scenario(
    name="fix_divide_by_zero",
    description="Fix the divide by zero bug in Calculator",
    prompt="Fix the divide method in src/mathlib/calculator.py to raise ValueError('Cannot divide by zero') when b is 0. Run pytest tests/test_calculator.py -k divide to verify.",
    acceptance_checks=[
        check_file_contains("src/mathlib/calculator.py", "Cannot divide by zero"),
        check_pytest_passes("divide"),
    ],
    check_names=["has_error_message", "tests_pass"],
)

SCENARIO_3_IMPLEMENT_MODE = Scenario(
    name="implement_mode_function",
    description="Implement the mode function in stats.py",
    prompt="Implement the mode function in src/mathlib/stats.py. Mode returns the most frequent value. Run pytest tests/test_stats.py -k mode to verify.",
    acceptance_checks=[
        check_pytest_passes("mode"),
    ],
    check_names=["tests_pass"],
)

SCENARIO_4_FIX_MEAN_EMPTY = Scenario(
    name="fix_mean_empty_list",
    description="Fix mean function to handle empty lists",
    prompt="Fix mean in src/mathlib/stats.py to raise ValueError('Cannot calculate mean of empty list') for empty input. Run pytest tests/test_stats.py -k mean to verify.",
    acceptance_checks=[
        check_file_contains("src/mathlib/stats.py", "Cannot calculate mean of empty list"),
        check_pytest_passes("mean"),
    ],
    check_names=["has_error_message", "tests_pass"],
)

SCENARIO_5_ADD_CLI_VERSION = Scenario(
    name="add_cli_version_command",
    description="Add a version command to the CLI",
    prompt="Add a 'version' command to src/mathlib/cli.py that prints __version__ from __init__.py. Test with: python -m mathlib.cli version",
    acceptance_checks=[
        check_file_contains("src/mathlib/cli.py", "version"),
        check_cli_command_works(["version"], "0.1.0"),
    ],
    check_names=["has_version_command", "version_works"],
)

SCENARIO_6_REFACTOR_WITH_LINT = Scenario(
    name="fix_lint_errors",
    description="Fix all ruff lint errors in the project",
    prompt="Run ruff check . to find lint errors. Fix all errors (unused imports, whitespace). Run ruff check . again to verify.",
    acceptance_checks=[
        check_ruff_clean(),
    ],
    check_names=["ruff_clean"],
)

SCENARIO_7_IMPLEMENT_FAHRENHEIT = Scenario(
    name="implement_fahrenheit_to_celsius",
    description="Implement fahrenheit_to_celsius function",
    prompt="Implement fahrenheit_to_celsius in src/mathlib/converter.py. Formula: C = (F - 32) * 5/9. Run pytest tests/test_converter.py -k fahrenheit to verify.",
    acceptance_checks=[
        check_function_exists("src/mathlib/converter.py", "fahrenheit_to_celsius"),
        check_pytest_passes("fahrenheit"),
    ],
    check_names=["function_exists", "tests_pass"],
)

SCENARIO_8_FIX_MEDIAN_EMPTY = Scenario(
    name="fix_median_empty_list",
    description="Fix median function to handle empty lists",
    prompt="Fix median in src/mathlib/stats.py to raise ValueError('Cannot calculate median of empty list') for empty input. Run pytest tests/test_stats.py -k median to verify.",
    acceptance_checks=[
        check_file_contains("src/mathlib/stats.py", "Cannot calculate median of empty list"),
        check_pytest_passes("median"),
    ],
    check_names=["has_error_message", "tests_pass"],
)

SCENARIO_9_ADD_TYPE_HINTS = Scenario(
    name="add_type_hints_calculator",
    description="Add type hints to Calculator class",
    prompt="Add type hints to all methods in src/mathlib/calculator.py. Example: def add(self, a: float, b: float) -> float:",
    acceptance_checks=[
        check_file_contains("src/mathlib/calculator.py", "-> float"),
        check_file_contains("src/mathlib/calculator.py", ": float"),
    ],
    check_names=["has_return_type", "has_param_types"],
)

SCENARIO_10_FULL_TEST_SUITE = Scenario(
    name="make_all_tests_pass",
    description="Fix all remaining issues until full test suite passes",
    prompt="Run pytest to see failing tests. Fix each one by implementing missing functions and fixing bugs. Keep going until ALL tests pass.",
    acceptance_checks=[
        check_pytest_passes(),
    ],
    check_names=["all_tests_pass"],
    timeout=180,
)

ALL_SCENARIOS: List[Scenario] = [
    SCENARIO_1_IMPLEMENT_CONVERTER,
    SCENARIO_2_FIX_DIVIDE_BUG,
    SCENARIO_3_IMPLEMENT_MODE,
    SCENARIO_4_FIX_MEAN_EMPTY,
    SCENARIO_5_ADD_CLI_VERSION,
    SCENARIO_6_REFACTOR_WITH_LINT,
    SCENARIO_7_IMPLEMENT_FAHRENHEIT,
    SCENARIO_8_FIX_MEDIAN_EMPTY,
    SCENARIO_9_ADD_TYPE_HINTS,
    SCENARIO_10_FULL_TEST_SUITE,
]
