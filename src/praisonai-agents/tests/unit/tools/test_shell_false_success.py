"""The SDK shell executor must not report success for work it never did.

`execute_command` runs shell=False, so shell syntax is passed to the program
as a literal argument rather than interpreted. Before this gate,
`echo written > redir.txt` returned exit_code 0, success True, stdout
"written > redir.txt" -- and created no file. A model reading that result was
told its redirect had succeeded, so it had no signal to correct on.
"""
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
        # A newline separates commands just like ";" -- shell=False would run
        # only the first line and silently drop the rest.
        ("echo first\ntouch proof.txt", "\n"),
        # A substitution keeps its power inside DOUBLE quotes.
        ('echo "$(whoami)"', "$("),
        ('echo "`whoami`"', "`"),
    ],
)
def test_shell_syntax_is_refused_not_silently_mangled(command, token, tmp_path, monkeypatch):
    """Each must FAIL loudly. Before the fix every one returned success=True."""
    monkeypatch.chdir(tmp_path)
    result = ShellTools().execute_command(command)

    assert result.get("success") is False, f"{command!r} reported success"
    assert result.get("exit_code") == 1
    # The message names the token via repr(), so a control character like a
    # newline appears escaped (``'\n'``) rather than as a literal break.
    error = str(result.get("error", ""))
    assert repr(token)[1:-1] in error, "the error must name the syntax"


def test_the_redirect_really_does_not_happen(tmp_path, monkeypatch):
    """Control: proves the refusal is about a real absence, not just a message."""
    monkeypatch.chdir(tmp_path)
    ShellTools().execute_command("echo written > proof.txt")
    assert not (tmp_path / "proof.txt").exists()


def test_the_newline_second_command_really_does_not_run(tmp_path, monkeypatch):
    """Control: the dropped second line must leave no filesystem effect."""
    monkeypatch.chdir(tmp_path)
    ShellTools().execute_command("echo first\ntouch proof.txt")
    assert not (tmp_path / "proof.txt").exists()


def test_a_plain_command_still_runs(tmp_path, monkeypatch):
    """Control: the guard must not reject commands it can honour."""
    monkeypatch.chdir(tmp_path)
    result = ShellTools().execute_command("echo hello")
    assert result.get("success") is True
    assert "hello" in result.get("stdout", "")


def test_quoted_metacharacters_are_not_refused():
    """`git commit -m "fix: a > b"` is legitimate -- its ">" is inside quotes.

    A naive substring scan would reject it, which is its own false failure.
    Redirect/pipe/chain characters are inert inside quotes; only command
    substitutions keep their power inside double quotes (tested separately).
    """
    assert _find_shell_syntax('git commit -m "fix: a > b"') is None
    assert _find_shell_syntax("echo 'a | b'") is None
    assert _find_shell_syntax("echo plain") is None
    # Single quotes make even a substitution literal -- must NOT be refused.
    assert _find_shell_syntax("echo '$(whoami)'") is None
    assert _find_shell_syntax("echo '`whoami`'") is None
    # Control: the same characters unquoted ARE found.
    assert _find_shell_syntax("echo a > b") == ">"
    assert _find_shell_syntax("echo a | b") == "|"


def test_double_quoted_substitutions_are_refused():
    """POSIX shells evaluate `$(...)` and backticks inside double quotes."""
    assert _find_shell_syntax('echo "$(whoami)"') == "$("
    assert _find_shell_syntax('echo "`whoami`"') == "`"


def test_newline_command_separator_is_found():
    """A newline (or CR) separates commands and must be refused."""
    assert _find_shell_syntax("echo first\ntouch proof.txt") == "\n"
    assert _find_shell_syntax("echo first\rtouch proof.txt") == "\r"
