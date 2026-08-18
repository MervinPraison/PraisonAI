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
import os

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


def test_code_print_uses_supported_agent_kwargs_and_workspace_tools(monkeypatch, tmp_path):
    """The real constructor contract and coding-tool wiring must stay aligned."""
    import inspect
    import praisonaiagents
    from praisonaiagents.agent.agent import Agent as RealAgent

    captured = {}

    class _SpyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self, *_args, **_kwargs):
            return "ok"

    def fake_tools(*, groups, workspace):
        captured["tool_groups"] = groups
        captured["workspace"] = workspace
        return [lambda: None]

    monkeypatch.setattr(praisonaiagents, "Agent", _SpyAgent, raising=False)
    monkeypatch.setattr(code_module, "_get_headless_code_tools", fake_tools)

    result = CliRunner().invoke(
        app,
        ["-p", "--workspace", str(tmp_path), "inspect the workspace"],
    )

    assert result.exit_code == 0, result.output
    real_params = set(inspect.signature(RealAgent.__init__).parameters)
    agent_keys = set(captured) - {"tool_groups", "workspace"}
    assert agent_keys <= real_params
    assert "verbose" not in captured
    assert captured["output"] == "minimal"
    assert captured["tools"]
    assert captured["workspace"] == str(tmp_path)
    assert captured["tool_groups"] == ["acp", "edit", "search", "lsp"]


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS", "").lower() not in {"1", "true", "yes"}
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Real OpenAI test disabled",
)
def test_code_print_real_agent_writes_workspace(tmp_path):
    """Run the real headless coding agent and exercise a workspace write."""
    target = tmp_path / "headless_probe.txt"

    result = CliRunner().invoke(
        app,
        [
            "-p",
            "--output",
            "json",
            "--model",
            "gpt-4o-mini",
            "--workspace",
            str(tmp_path),
            "--dangerously-skip-approval",
            f"Create {target.name} containing exactly HEADLESS_OK.",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip())
    assert payload["status"] == "ok"
    assert target.read_text(encoding="utf-8").strip() == "HEADLESS_OK"


def test_headless_search_tools_are_workspace_bound(tmp_path):
    """Search tools must contain reads to --workspace, not the process cwd.

    The core ``grep``/``glob`` default containment to ``os.getcwd()`` and
    ``ast_grep_search`` performs none, so the headless loader must bind them to
    the configured workspace. A model-supplied path that escapes the workspace
    (absolute or ``..``) must be rejected without touching the filesystem.
    """
    from praisonai_code.cli.features.interactive_tools import (
        ToolConfig,
        _load_search_tools,
    )

    (tmp_path / "inside.txt").write_text("needle here", encoding="utf-8")

    config = ToolConfig(workspace=str(tmp_path))
    tools = _load_search_tools(config)
    by_name = {t.__name__: t for t in tools.values()}

    # grep is always available (pure-Python fallback), so assert on it.
    grep = by_name["grep"]
    assert "escapes the workspace" in grep("needle", path="/etc")
    assert "escapes the workspace" in grep("needle", path="../../..")
    # An in-workspace search still works and finds the seeded match.
    assert "inside.txt" in grep("needle", path=".")

    if "glob" in by_name:
        assert "escapes the workspace" in by_name["glob"]("*", path="/etc")
    if "ast_grep_search" in by_name:
        assert "escapes the workspace" in by_name["ast_grep_search"](
            "x", lang="python", path="/etc"
        )


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
        ["--no-acp"],
        ["--no-lsp"],
    ],
)
def test_print_rejects_unsupported_options(opt):
    """`-p` still fails closed on options the headless path cannot honor.

    ``--no-acp``/``--no-lsp`` toggle the resident split-pane TUI's runtime tool
    servers, which the one-shot headless agent does not spin up, so they are
    rejected rather than silently ignored. ``--tools``/``--agent``/``--plan``
    are now wired into the headless branch (see their dedicated tests below).
    """
    runner = CliRunner()
    result = runner.invoke(app, ["-p", *opt, "do a thing"])

    assert result.exit_code == 1
    assert "does not support" in result.output


def test_print_tools_merged_onto_headless_defaults(monkeypatch, tmp_path):
    """`code -p --tools <name>` resolves the tool and merges it with defaults."""
    import praisonaiagents

    captured = {}

    class _SpyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self, *_args, **_kwargs):
            return "ok"

    def _default_tools(*, groups, workspace):
        return [lambda: "default"]

    def _custom_tool():
        return "custom"

    def _fake_resolve_tools_arg(value, verbose=False):
        assert value == "my_tool"
        return [_custom_tool]

    monkeypatch.setattr(praisonaiagents, "Agent", _SpyAgent, raising=False)
    monkeypatch.setattr(code_module, "_get_headless_code_tools", _default_tools)
    from praisonai_code.cli.commands import run as run_module

    monkeypatch.setattr(run_module, "_resolve_tools_arg", _fake_resolve_tools_arg)

    result = CliRunner().invoke(
        app,
        ["-p", "--workspace", str(tmp_path), "--tools", "my_tool", "do a thing"],
    )

    assert result.exit_code == 0, result.output
    assert _custom_tool in captured["tools"]
    # The default coding toolset is preserved alongside the custom tool.
    assert len(captured["tools"]) >= 2


def test_print_tools_resolution_failure_uses_envelope(monkeypatch, tmp_path):
    """A failing `--tools` resolution is reported via the envelope, not a traceback.

    Resolving ``--tools`` may import a user ``tools.py`` that fails at import
    time. That failure must be captured by ``_run_print_code``'s error envelope
    (``status=error`` + non-zero exit + machine-readable ``error``) so scripted
    callers get the documented contract, never a raw CLI traceback.
    """
    import praisonaiagents

    class _SpyAgent:
        def __init__(self, **kwargs):
            pass

        def start(self, *_args, **_kwargs):  # pragma: no cover - never reached
            return "should not run"

    monkeypatch.setattr(praisonaiagents, "Agent", _SpyAgent, raising=False)
    monkeypatch.setattr(
        code_module,
        "_get_headless_code_tools",
        lambda *, groups, workspace: [lambda: None],
    )

    def _boom(value, verbose=False):
        raise RuntimeError("bad tools.py: import failed")

    from praisonai_code.cli.commands import run as run_module

    monkeypatch.setattr(run_module, "_resolve_tools_arg", _boom)

    result = CliRunner().invoke(
        app,
        ["-p", "--output", "json", "--workspace", str(tmp_path), "--tools", "bad.py", "go"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout.strip())
    assert payload["status"] == "error"
    assert "bad tools.py" in payload.get("error", "")


def test_print_plan_sets_readonly_approval(monkeypatch, tmp_path):
    """`code -p --plan` wires a non-interactive read-only approval backend."""
    import praisonaiagents

    captured = {}

    class _SpyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self, *_args, **_kwargs):
            return "plan result"

    monkeypatch.setattr(praisonaiagents, "Agent", _SpyAgent, raising=False)
    monkeypatch.setattr(
        code_module,
        "_get_headless_code_tools",
        lambda *, groups, workspace: [lambda: None],
    )

    result = CliRunner().invoke(
        app,
        ["-p", "--workspace", str(tmp_path), "--plan", "explore the repo"],
    )

    assert result.exit_code == 0, result.output
    # An approval backend was threaded in for the read-only plan scope.
    approval = captured.get("approval")
    assert approval is not None
    backend = getattr(approval, "backend", approval)
    from praisonaiagents.permissions import PermissionMode

    assert getattr(backend, "permission_mode", None) == PermissionMode.PLAN
    assert getattr(backend, "non_interactive", False) is True


def test_print_agent_profile_applies_instructions_and_scope(monkeypatch, tmp_path):
    """`code -p --agent <name>` applies the profile's instructions + scope."""
    import praisonaiagents

    captured = {}

    class _SpyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self, *_args, **_kwargs):
            return "ok"

    monkeypatch.setattr(praisonaiagents, "Agent", _SpyAgent, raising=False)
    monkeypatch.setattr(
        code_module,
        "_get_headless_code_tools",
        lambda *, groups, workspace: [lambda: None],
    )

    def _fake_load_agent(name):
        assert name == "reviewer"
        return {
            "name": "reviewer",
            "instructions": "Review carefully.",
            "permissions": {"edit:*": "deny", "write:*": "deny"},
        }

    from praisonai_code.cli.features import custom_definitions as cd

    monkeypatch.setattr(cd, "load_agent_from_name", _fake_load_agent)

    result = CliRunner().invoke(
        app,
        ["-p", "--workspace", str(tmp_path), "--agent", "reviewer", "review"],
    )

    assert result.exit_code == 0, result.output
    assert captured["instructions"] == "Review carefully."
    # The profile's permission scope is enforced via a non-interactive backend.
    approval = captured.get("approval")
    assert approval is not None


def test_profiled_code_agent_kwargs_match_constructor(monkeypatch):
    """The `--profile` path must not pass the dropped `verbose=` kwarg either.

    The profiled code path builds its own ``Agent`` directly (bypassing
    ``_run_print_code``). It suffered the same constructor drift: passing a
    legacy top-level ``verbose=`` that ``Agent.__init__`` now rejects. Guard the
    kwargs against the real signature so the crash cannot reappear.
    """
    import inspect
    import praisonaiagents
    from praisonaiagents.agent.agent import Agent as RealAgent
    from praisonai_code.cli.commands.code import _run_profiled_code

    captured = {}

    class _SpyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self, *_args, **_kwargs):
            return "ok"

    monkeypatch.setattr(praisonaiagents, "Agent", _SpyAgent, raising=False)

    _run_profiled_code(prompt="do a thing", verbose=True)

    real_params = set(inspect.signature(RealAgent.__init__).parameters)
    assert set(captured) <= real_params
    assert "verbose" not in captured
    assert captured["output"] == "verbose"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
