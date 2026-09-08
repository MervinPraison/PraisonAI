"""The SDK shell executor must not report success for work it never did.

`execute_command` runs shell=False, so shell syntax is passed to the program
as a literal argument rather than interpreted. Before this gate,
`echo written > redir.txt` returned exit_code 0, success True, stdout
"written > redir.txt" -- and created no file. A model reading that result was
told its redirect had succeeded, so it had no signal to correct on.
"""
import os
import tempfile

import pytest

from praisonaiagents.tools.shell_tools import ShellTools, _find_shell_syntax


@pytest.fixture(autouse=True)
def _auto_approve(monkeypatch):
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")


@pytest.mark.parametrize(
    "command,token",
    [
        ("echo written > redir.txt", ">"),
        ("echo a >> log.txt", ">>"),
        ("cd .. && pwd", "&&"),
        ("false || echo fallback", "||"),
        ("ls | head", "|"),
        ("echo a; echo b", ";"),
        ("echo $(whoami)", "$("),
    ],
)
def test_shell_syntax_is_refused_not_silently_mangled(command, token, tmp_path):
    """Each must FAIL loudly. Before the fix every one returned success=True."""
    os.chdir(tmp_path)
    result = ShellTools().execute_command(command)

    assert result.get("success") is False, f"{command!r} reported success"
    assert result.get("exit_code") == 1
    assert token in str(result.get("error", "")), "the error must name the syntax"


def test_the_redirect_really_does_not_happen(tmp_path):
    """Control: proves the refusal is about a real absence, not just a message."""
    os.chdir(tmp_path)
    ShellTools().execute_command("echo written > proof.txt")
    assert not (tmp_path / "proof.txt").exists()


def test_a_plain_command_still_runs(tmp_path):
    """Control: the guard must not reject commands it can honour."""
    os.chdir(tmp_path)
    result = ShellTools().execute_command("echo hello")
    assert result.get("success") is True
    assert "hello" in result.get("stdout", "")


def test_quoted_metacharacters_are_not_refused():
    """`git commit -m "fix: a > b"` is legitimate -- its ">" is inside quotes.

    A naive substring scan would reject it, which is its own false failure.
    """
    assert _find_shell_syntax('git commit -m "fix: a > b"') is None
    assert _find_shell_syntax("echo 'a | b'") is None
    assert _find_shell_syntax("echo plain") is None
    # Control: the same characters unquoted ARE found.
    assert _find_shell_syntax("echo a > b") == ">"
    assert _find_shell_syntax("echo a | b") == "|"
