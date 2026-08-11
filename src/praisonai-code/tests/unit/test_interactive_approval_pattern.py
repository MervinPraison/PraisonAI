"""Tests for interactive-approval pattern scoping (#3178).

Choosing "Always allow" in the interactive Rich/Textual frontends must default
to the *narrowest reasonable* command-scoped pattern, never a blanket
``action_type:*`` grant. The blanket grant must only be produced by the
explicit ``scope="tool"`` choice, matching the console backend's ``[A]``/``[T]``
split.
"""

import pytest

from praisonai_code.cli.interactive.events import (
    ApprovalRequest,
    derive_permission_pattern,
)

_core_helper_available = True
try:  # pragma: no cover - environment dependent
    from praisonaiagents.permissions import derive_pattern  # noqa: F401
except Exception:  # pragma: no cover
    _core_helper_available = False


def _req(action_type, tool_name, **params):
    return ApprovalRequest(
        action_type=action_type,
        description="test",
        tool_name=tool_name,
        parameters=params,
    )


def test_shell_command_narrow_not_blanket():
    req = _req("shell_command", "bash", command="git status")
    pattern = derive_permission_pattern(req, scope="command")
    # Never a blanket grant, and always scoped to the concrete command.
    assert pattern != "shell_command:*"
    assert pattern.startswith("shell_command:git status")


@pytest.mark.skipif(
    not _core_helper_available,
    reason="praisonaiagents core derive_pattern not installed",
)
def test_shell_command_generalises_prefix_when_core_available():
    req = _req("shell_command", "bash", command="git status")
    assert derive_permission_pattern(req, scope="command") == "shell_command:git status *"


def test_shell_command_blanket_is_explicit_only():
    req = _req("shell_command", "bash", command="git status")
    assert derive_permission_pattern(req, scope="tool") == "shell_command:*"


def test_compound_shell_command_stays_literal():
    req = _req("shell_command", "bash", command="cd /tmp && rm -rf x")
    pattern = derive_permission_pattern(req, scope="command")
    assert pattern == "shell_command:cd /tmp && rm -rf x"
    assert "*" not in pattern


def test_file_write_scopes_to_path():
    req = _req("file_write", "write", path="src/app.py")
    assert derive_permission_pattern(req, scope="command") == "file_write:src/app.py"
    assert derive_permission_pattern(req, scope="tool") == "file_write:*"


def test_no_params_never_wildcards():
    req = _req("file_read", "read")
    assert derive_permission_pattern(req, scope="command") == "file_read:"


def test_command_scope_never_returns_blanket():
    for action, tool, params in [
        ("shell_command", "bash", {"command": "npm run build"}),
        ("file_write", "write", {"path": "a.py"}),
        ("file_read", "read", {}),
    ]:
        req = _req(action, tool, **params)
        assert derive_permission_pattern(req, scope="command") != f"{action}:*"
