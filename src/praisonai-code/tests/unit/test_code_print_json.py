"""Tests for `praisonai code -p/--print --output json|text` headless mode (#3738).

`code` — the flagship surface — previously had no scripting-grade headless mode:
its one-shot path printed human-decorated output mixed with `Chat mode:`/`Prompt:`
diagnostics and a profiling block, and always exited 0. This makes it unusable for
scripts, CI, and benchmark harnesses. These tests assert the new `-p/--print` +
`--output` surface reaches parity with `run --output json`/`chat --json`:

* the flags exist on `code`;
* `-p --output json` emits a clean single-line JSON envelope with no `Chat mode:`
  or profiling lines;
* the exit code is non-zero on error/empty result;
* `--resume <id> -p` composes for scripted multi-turn.
"""

import json

import pytest
from typer.testing import CliRunner

from praisonai_code.cli.commands import code as code_module
from praisonai_code.cli.commands.code import app


def _param_names(app):
    """Collect the declared CLI option strings for a Typer callback app."""
    import inspect

    callback = app.registered_callback.callback
    names = set()
    for param in inspect.signature(callback).parameters.values():
        names.update(getattr(param.default, "param_decls", None) or [])
    return names


def test_code_exposes_print_and_output_flags():
    names = _param_names(app)
    assert "--print" in names
    assert "-p" in names
    assert "--output" in names
    assert "--resume" in names


def test_code_print_json_envelope_clean_stdout(monkeypatch):
    """`code -p --output json` emits only the JSON envelope on stdout.

    No `Chat mode:`/`Prompt:` diagnostics and no profiling block should leak into
    stdout — the whole point of headless mode.
    """
    import praisonaiagents

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *_args, **_kwargs):
            return "def add(a, b): return a + b"

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "json", "Write an add function"])

    assert result.exit_code == 0, result.output
    # stdout is a single clean JSON object — parseable, no decorations.
    payload = json.loads(result.stdout.strip())
    assert payload["result"] == "def add(a, b): return a + b"
    assert payload["status"] == "ok"
    assert set(payload["usage"].keys()) == {"in", "out", "cost"}
    assert "session_id" in payload

    assert "Chat mode:" not in result.stdout
    assert "Prompt:" not in result.stdout
    assert "profiling" not in result.stdout.lower()


def test_code_print_defaults_to_json(monkeypatch):
    """`-p` without `--output` defaults to the JSON envelope for parity."""
    import praisonaiagents

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *_args, **_kwargs):
            return "ok result"

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "do a thing"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip())
    assert payload["result"] == "ok result"


def test_code_print_text_mode_clean_stdout(monkeypatch):
    """`-p --output text` prints just the result text, no envelope or decorations."""
    import praisonaiagents

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *_args, **_kwargs):
            return "plain answer"

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "text", "ask"])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "plain answer"
    assert "Chat mode:" not in result.stdout
    assert "{" not in result.stdout  # not JSON


def test_exit_code_nonzero_on_error(monkeypatch):
    """A raised error inside the agent yields status=error and a non-zero exit."""
    import praisonaiagents

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *_args, **_kwargs):
            raise RuntimeError("invalid api key")

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "json", "do a thing"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout.strip())
    assert payload["status"] == "error"
    assert "invalid api key" in payload.get("error", "")


def test_exit_code_nonzero_on_empty_result(monkeypatch):
    """An empty/None result is a failure (parity with `run`): exit non-zero."""
    import praisonaiagents

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *_args, **_kwargs):
            return ""

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "do a thing"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout.strip())
    assert payload["status"] == "failed"
    assert payload["result"] is None


def test_resume_plus_print_composes(monkeypatch):
    """`--resume <id> -p` threads the session id into the envelope for multi-turn."""
    import praisonaiagents

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *_args, **_kwargs):
            return "follow-up answer"

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent, raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app, ["-p", "--output", "json", "--resume", "sess-123", "follow up please"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip())
    assert payload["session_id"] == "sess-123"
    assert payload["result"] == "follow-up answer"


def test_output_requires_print():
    """`--output` without `-p` fails closed with a clear error and non-zero exit."""
    runner = CliRunner()
    result = runner.invoke(app, ["--output", "json", "hello"])

    assert result.exit_code == 1
    assert "--output requires -p/--print" in result.output


def test_unknown_output_format_fails_closed():
    """An unknown `--output` value fails closed before any work."""
    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "yaml", "hello"])

    assert result.exit_code == 1
    assert "unknown --output" in result.output


def test_print_rejects_profile_combination():
    """`-p` + `--profile` fails closed rather than emitting a human report.

    Profiling prints a human-oriented report and always exits 0, which would
    silently break the machine-readable -p contract. The two intents are
    mutually exclusive, so the combination must be rejected up front.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--profile", "do a thing"])

    assert result.exit_code == 1
    assert "cannot be combined with --profile" in result.output
    assert "Chat mode:" not in result.output


@pytest.mark.parametrize(
    "opt",
    [
        ["--tools", "web_search"],
        ["--agent", "planner"],
        ["--plan"],
        ["--no-acp"],
        ["--no-lsp"],
    ],
)
def test_print_rejects_unsupported_options(opt):
    """`-p` fails closed on options the headless path cannot honor.

    Silently dropping tool/profile/scope configuration would run a
    tool-dependent task without the requested tools; an explicit error is
    safer and points users to interactive mode.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["-p", *opt, "do a thing"])

    assert result.exit_code == 1
    assert "does not support" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
