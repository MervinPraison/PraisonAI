"""Unit tests for ShellTools.execute_command input-normalisation improvements.

Covers:
1. Stripping wrapping quotes added by LLMs around the whole command string.
2. Empty-command guard – consistent return-value shape.
3. Empty/None cwd normalisation.
"""

import os
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_shell():
    """Return a ShellTools instance with auto-approval so tests can call it."""
    from praisonaiagents.tools.shell_tools import ShellTools
    return ShellTools()


def _run(shell, command, **kwargs):
    """Call execute_command with PRAISONAI_AUTO_APPROVE set."""
    with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "true"}):
        return shell.execute_command(command, **kwargs)


# ---------------------------------------------------------------------------
# Expected result-shape helper
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"stdout", "stderr", "exit_code", "success", "execution_time"}


def _assert_shape(result: dict) -> None:
    """Assert the result dict has all required keys."""
    missing = _REQUIRED_KEYS - result.keys()
    assert not missing, f"Result is missing keys: {missing}; got {result}"


# ---------------------------------------------------------------------------
# Tests: empty command
# ---------------------------------------------------------------------------

class TestEmptyCommandGuard:
    """execute_command should return a consistent dict for empty commands."""

    def test_empty_string_returns_required_keys(self):
        shell = _make_shell()
        result = _run(shell, "")
        _assert_shape(result)

    def test_empty_string_success_is_false(self):
        shell = _make_shell()
        result = _run(shell, "")
        assert result["success"] is False

    def test_empty_string_exit_code_nonzero(self):
        shell = _make_shell()
        result = _run(shell, "")
        assert result["exit_code"] != 0

    def test_empty_string_execution_time_present(self):
        shell = _make_shell()
        result = _run(shell, "")
        assert isinstance(result["execution_time"], (int, float))

    def test_whitespace_only_returns_required_keys(self):
        shell = _make_shell()
        result = _run(shell, "   ")
        _assert_shape(result)

    def test_whitespace_only_success_is_false(self):
        shell = _make_shell()
        result = _run(shell, "   ")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: quote stripping
# ---------------------------------------------------------------------------

class TestQuoteNormalisation:
    """execute_command should strip wrapping quotes added by LLMs."""

    def test_single_quoted_command_executes(self):
        shell = _make_shell()
        result = _run(shell, "'echo hello'")
        _assert_shape(result)
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_double_quoted_command_executes(self):
        shell = _make_shell()
        result = _run(shell, '"echo world"')
        _assert_shape(result)
        assert result["success"] is True
        assert "world" in result["stdout"]

    def test_unquoted_command_executes_normally(self):
        shell = _make_shell()
        result = _run(shell, "echo normal")
        _assert_shape(result)
        assert result["success"] is True
        assert "normal" in result["stdout"]

    def test_mismatched_quotes_not_stripped(self):
        """Mismatched quotes (e.g. 'cmd") are not stripped; shlex raises ValueError which is caught."""
        shell = _make_shell()
        # The outer try/except in execute_command catches ValueError from shlex.split
        result = _run(shell, "'echo bad\"")
        _assert_shape(result)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: cwd normalisation
# ---------------------------------------------------------------------------

class TestCwdNormalisation:
    """Empty/None cwd should be treated as None (use current directory)."""

    def test_empty_string_cwd_is_treated_as_none(self):
        shell = _make_shell()
        result = _run(shell, "echo cwd_test", cwd="")
        _assert_shape(result)
        assert result["success"] is True

    def test_none_cwd_works(self):
        shell = _make_shell()
        result = _run(shell, "echo no_cwd", cwd=None)
        _assert_shape(result)
        assert result["success"] is True
