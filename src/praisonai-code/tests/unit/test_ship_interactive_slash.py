"""Unit tests for interactive `/ship` and `/steward` slash commands."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

from praisonai_code.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig
from praisonai_code.cli.interactive.repl import DEFAULT_COMMANDS, InteractiveREPL


class TestRunShipSlash:
    def test_ship_forwards_exact_args(self):
        from praisonai_code.cli.interactive._ship_slash import run_ship_slash

        seen = []

        def fake_run(argv, **kw):
            seen.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0, stdout="dry-run ok\n", stderr="")

        out = run_ship_slash("ship", "--dry-run --title 'fix: bug'", cwd="/repo", run=fake_run)
        assert out == "dry-run ok"
        assert len(seen) == 1
        argv, kw = seen[0]
        assert argv == [
            sys.executable, "-m", "praisonai_code", "ship", "--dry-run", "--title", "fix: bug",
        ]
        assert kw == {"cwd": "/repo", "capture_output": True, "text": True}

    def test_steward_appends_once_and_note_on_success(self):
        from praisonai_code.cli.interactive._ship_slash import run_ship_slash

        seen = []

        def fake_run(argv, **kw):
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="PR #42 green\n", stderr="")

        out = run_ship_slash("steward", "42", run=fake_run)
        assert seen == [[sys.executable, "-m", "praisonai_code", "steward", "42", "--once"]]
        assert "PR #42 green" in out
        assert "praisonai steward" in out

    def test_steward_nonzero_omits_once_note(self):
        from praisonai_code.cli.interactive._ship_slash import run_ship_slash

        def fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="disabled\n")

        out = run_ship_slash("steward", "42", run=fake_run)
        assert out == "disabled"
        assert "praisonai steward" not in out

    def test_steward_help_and_explicit_once_do_not_duplicate_once(self):
        from praisonai_code.cli.interactive._ship_slash import run_ship_slash

        seen = []

        def fake_run(argv, **kw):
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="usage\n", stderr="")

        out_help = run_ship_slash("steward", "--help", run=fake_run)
        out_h = run_ship_slash("steward", "-h", run=fake_run)
        out_once = run_ship_slash("steward", "42 --once", run=fake_run)

        assert seen == [
            [sys.executable, "-m", "praisonai_code", "steward", "--help"],
            [sys.executable, "-m", "praisonai_code", "steward", "-h"],
            [sys.executable, "-m", "praisonai_code", "steward", "42", "--once"],
        ]
        assert out_help == "usage"
        assert out_h == "usage"
        assert out_once == "usage"

    def test_bad_quoting_and_unsupported_cmd_return_error_without_raising(self):
        from praisonai_code.cli.interactive._ship_slash import run_ship_slash

        called = []

        def fake_run(argv, **kw):
            called.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        err_quote = run_ship_slash("ship", '"unclosed', run=fake_run)
        err_cmd = run_ship_slash("merge", "", run=fake_run)

        assert "Invalid arguments" in err_quote
        assert "Unsupported command" in err_cmd
        assert called == []

    def test_subprocess_exception_returns_error_without_raising(self):
        from praisonai_code.cli.interactive._ship_slash import run_ship_slash

        def boom(argv, **kw):
            raise OSError("spawn failed")

        out = run_ship_slash("ship", "--dry-run", run=boom)
        assert "spawn failed" in out

    def test_approvals_forwards_exact_args_without_injecting_once(self):
        from praisonai_code.cli.interactive._ship_slash import run_ship_slash

        seen = []

        def fake_run(argv, **kw):
            seen.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0, stdout='{"passed": true}\n', stderr="")

        out = run_ship_slash("approvals", "42 --json", cwd="/repo", run=fake_run)
        assert out == '{"passed": true}'
        assert seen == [
            ([sys.executable, "-m", "praisonai_code", "approvals", "42", "--json"],
             {"cwd": "/repo", "capture_output": True, "text": True})
        ]
        assert "--once" not in seen[0][0]


class TestInteractiveRegistrationAndDispatch:
    def test_async_tui_registers_and_dispatches_ship_and_steward(self):
        assert "ship" in AsyncTUI._BUILTIN_COMMANDS
        assert "steward" in AsyncTUI._BUILTIN_COMMANDS
        assert "approvals" in AsyncTUI._BUILTIN_COMMANDS

        tui = AsyncTUI(config=AsyncTUIConfig(workspace="/tmp/ws"))
        calls = []

        def fake_slash(cmd, args="", *, cwd=None, **kw):
            calls.append((cmd, args, cwd))
            return f"ran {cmd} {args}".strip()

        with patch(
            "praisonai_code.cli.interactive._ship_slash.run_ship_slash",
            side_effect=fake_slash,
        ):
            assert tui._handle_command("/ship --dry-run") is True
            assert tui._handle_command("/steward 42") is True
            assert tui._handle_command("/approvals 42 --json") is True

        assert calls == [
            ("ship", "--dry-run", "/tmp/ws"),
            ("steward", "42", "/tmp/ws"),
            ("approvals", "42 --json", "/tmp/ws"),
        ]
        assert [(m.role, m.content) for m in tui.messages[-3:]] == [
            ("system", "ran ship --dry-run"),
            ("system", "ran steward 42"),
            ("system", "ran approvals 42 --json"),
        ]

    def test_repl_registers_and_dispatches_ship_and_steward(self):
        assert "ship" in DEFAULT_COMMANDS
        assert "steward" in DEFAULT_COMMANDS
        assert "approvals" in DEFAULT_COMMANDS

        repl = InteractiveREPL()
        repl.io = MagicMock()
        calls = []

        def fake_slash(cmd, args="", **kw):
            calls.append((cmd, args))
            return f"ran {cmd} {args}".strip()

        with patch(
            "praisonai_code.cli.interactive._ship_slash.run_ship_slash",
            side_effect=fake_slash,
        ):
            assert repl._handle_command("/ship --dry-run") is True
            assert repl._handle_command("/steward 42") is True
            assert repl._handle_command("/approvals 42 --json") is True

        assert calls == [("ship", "--dry-run"), ("steward", "42"), ("approvals", "42 --json")]
        info_args = [call.args[0] for call in repl.io.info.call_args_list]
        assert info_args == ["ran ship --dry-run", "ran steward 42", "ran approvals 42 --json"]
