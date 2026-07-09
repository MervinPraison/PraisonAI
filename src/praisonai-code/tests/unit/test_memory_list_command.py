"""Tests for the `memory list` subcommand (issue #2840).

`praisonai-code memory list` must be resolvable by Typer for parity with
`tools list`, `session list`, and `config list`. Previously the memory command
group only exposed `show`/`add`/`search`/`clear`, so `memory list` exited with
code 2 ("No such command 'list'"). `list` is now registered as an alias that
delegates to the same handler as `show`.
"""

import sys
import types
from unittest.mock import patch

from typer.testing import CliRunner

from praisonai_code.cli.commands.memory import app

runner = CliRunner()


def test_memory_list_is_a_known_command():
    """`memory list` must not fail with Typer's exit code 2 (unknown command)."""
    with patch("praisonai_code.cli.commands.memory.memory_show"):
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0


def test_memory_list_delegates_to_show():
    """`memory list` shares the `show` implementation, forwarding options."""
    with patch(
        "praisonai_code.cli.commands.memory.memory_show"
    ) as mock_show:
        result = runner.invoke(app, ["list", "--user-id", "alice", "--limit", "5"])
    assert result.exit_code == 0
    mock_show.assert_called_once_with(user_id="alice", limit=5)


def test_memory_show_forwards_limit_to_argv():
    """`--limit` must be forwarded in the argv passed to PraisonAI (issue #2840)."""
    captured = {}

    class _FakePraisonAI:
        def main(self):
            captured["argv"] = list(sys.argv)

    fake_main = types.ModuleType("praisonai_code.cli.main")
    fake_main.PraisonAI = _FakePraisonAI
    with patch.dict(sys.modules, {"praisonai_code.cli.main": fake_main}):
        result = runner.invoke(app, ["list", "--user-id", "alice", "--limit", "5"])
    assert result.exit_code == 0
    assert "--limit" in captured["argv"]
    assert "5" in captured["argv"]


def test_memory_list_appears_in_help():
    """`memory --help` documents the new `list` subcommand."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "list" in result.stdout


def test_memory_show_still_registered():
    """No regression: `show` remains available alongside `list`."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("show", "add", "search", "clear"):
        assert cmd in result.stdout
