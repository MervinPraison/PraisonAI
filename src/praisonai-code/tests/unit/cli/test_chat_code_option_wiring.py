"""Options `chat` and `code` accept must reach the runtime, or be declared unwired.

`praisonai chat --file README.md` and `praisonai code "fix it" --file main.py`
are the commands' *own* docstring examples, and both parsed the attachment and
threw it away. `praisonai chat --continue` started a brand-new session with a
fresh uuid. `praisonai code --no-autonomy` was the only way to turn
auto-delegation off, and it did nothing.

These tests drive the real command bodies with the TUI stubbed, and assert on
the config and prompt that actually reach it.
"""

import ast
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import praisonai_code.cli.commands.chat as chat_module
import praisonai_code.cli.commands.code as code_module


class _CapturingTUI:
    """Records the config and prompt the command dispatched with."""

    last_config = None
    last_prompt = None
    execution_failed = False

    def __init__(self, config=None, *args, **kwargs):
        type(self).last_config = config

    def run_single(self, prompt):
        type(self).last_prompt = prompt
        return ""

    def run(self):
        type(self).last_prompt = None
        return None


@pytest.fixture
def tui(monkeypatch):
    _CapturingTUI.last_config = None
    _CapturingTUI.last_prompt = None
    monkeypatch.setattr(
        "praisonai_code.llm.credentials.ensure_configured_or_onboard",
        lambda model=None, interactive=True: model,
    )
    monkeypatch.setattr(
        "praisonai_code.cli.interactive.async_tui.AsyncTUI", _CapturingTUI
    )
    # `code` only takes the resident-TUI path when the wrapper is absent.
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )
    return _CapturingTUI


def _invoke(fn, args):
    app = typer.Typer()
    app.command()(fn)
    return CliRunner().invoke(app, args)


# --------------------------------------------------------------------------
# --file / -f
# --------------------------------------------------------------------------

def test_chat_file_attachment_reaches_the_prompt(tmp_path, tui):
    doc = tmp_path / "notes.md"
    doc.write_text("the launch code is hunter2")

    result = _invoke(chat_module.chat_main, ["Summarise this", "--file", str(doc)])

    assert result.exit_code == 0, result.output
    assert tui.last_prompt is not None, "chat never dispatched a prompt"
    assert "the launch code is hunter2" in tui.last_prompt
    assert "Summarise this" in tui.last_prompt


def test_code_file_attachment_reaches_the_prompt(tmp_path, tui):
    doc = tmp_path / "main.py"
    doc.write_text("def broken():\n    return 1 / 0\n")

    result = _invoke(code_module.code_main, ["Fix the bug", "--file", str(doc)])

    assert result.exit_code == 0, result.output
    assert tui.last_prompt is not None
    assert "return 1 / 0" in tui.last_prompt


def test_attachment_without_a_prompt_still_reaches_the_model(tmp_path, tui):
    doc = tmp_path / "notes.md"
    doc.write_text("read me")
    _invoke(chat_module.chat_main, ["--file", str(doc)])
    # No prompt means the interactive path, which never calls run_single --
    # the point here is only that the command accepts it and does not crash.
    assert tui.last_config is not None


def test_a_missing_attachment_does_not_abort_the_run(tmp_path, tui):
    result = _invoke(
        chat_module.chat_main, ["hi", "--file", str(tmp_path / "nope.md")]
    )
    assert result.exit_code == 0, result.output
    assert tui.last_prompt == "hi"


def test_profiled_chat_still_receives_the_attachment(tmp_path, tui, monkeypatch):
    """`--profile` returns before the TUI path, so it must get --file too.

    The profiling branch dispatched to `_run_profiled_chat` before attachments
    were resolved, so `praisonai chat "..." --file notes.md --profile` silently
    sent only the bare prompt to the model.
    """
    captured = {}

    def _fake_profiled(prompt, model=None, verbose=False, profile_deep=False):
        captured["prompt"] = prompt

    monkeypatch.setattr(chat_module, "_run_profiled_chat", _fake_profiled)

    doc = tmp_path / "notes.md"
    doc.write_text("the launch code is hunter2")

    result = _invoke(
        chat_module.chat_main, ["Summarise this", "--file", str(doc), "--profile"]
    )

    assert result.exit_code == 0, result.output
    assert "the launch code is hunter2" in captured.get("prompt", ""), (
        "profiling dropped the --file attachment"
    )


# --------------------------------------------------------------------------
# --continue
# --------------------------------------------------------------------------

def test_chat_continue_resumes_the_last_session(tmp_path, tui, monkeypatch):
    from praisonai_code.cli.session import UnifiedSessionStore
    import praisonai_code.cli.session as session_pkg

    store = UnifiedSessionStore(session_dir=tmp_path / "sessions")
    store.get_or_create("earlier-one")
    monkeypatch.setattr(session_pkg, "get_session_store", lambda: store)

    _invoke(chat_module.chat_main, ["hi", "--continue"])

    assert tui.last_config.session_id == "earlier-one", (
        "--continue started a brand-new session instead of resuming"
    )


def test_an_explicit_session_beats_continue(tmp_path, tui, monkeypatch):
    from praisonai_code.cli.session import UnifiedSessionStore
    import praisonai_code.cli.session as session_pkg

    store = UnifiedSessionStore(session_dir=tmp_path / "sessions")
    store.get_or_create("earlier-one")
    monkeypatch.setattr(session_pkg, "get_session_store", lambda: store)

    _invoke(chat_module.chat_main, ["hi", "--continue", "--session", "chosen"])

    assert tui.last_config.session_id == "chosen"


def test_continue_with_no_history_says_so_and_carries_on(tmp_path, tui, monkeypatch):
    from praisonai_code.cli.session import UnifiedSessionStore
    import praisonai_code.cli.session as session_pkg

    store = UnifiedSessionStore(session_dir=tmp_path / "sessions")
    monkeypatch.setattr(session_pkg, "get_session_store", lambda: store)

    result = _invoke(chat_module.chat_main, ["hi", "--continue"])

    assert result.exit_code == 0
    assert "No previous session" in result.output


# --------------------------------------------------------------------------
# --no-acp / --no-lsp / --no-autonomy
# --------------------------------------------------------------------------

def test_chat_no_acp_and_no_lsp_reach_the_tui(tui):
    _invoke(chat_module.chat_main, ["hi", "--no-acp", "--no-lsp"])
    assert tui.last_config.enable_acp is False
    assert tui.last_config.enable_lsp is False


def test_chat_acp_and_lsp_default_to_on(tui):
    _invoke(chat_module.chat_main, ["hi"])
    assert tui.last_config.enable_acp is True
    assert tui.last_config.enable_lsp is True


def test_code_no_autonomy_reaches_the_tui(tui):
    _invoke(code_module.code_main, ["hi", "--no-autonomy"])
    assert tui.last_config.autonomy_mode is False, (
        "--no-autonomy was accepted and dropped; auto-delegation stayed on"
    )


def test_code_autonomy_defaults_to_on(tui):
    _invoke(code_module.code_main, ["hi"])
    assert tui.last_config.autonomy_mode is True


# --------------------------------------------------------------------------
# The pin
# --------------------------------------------------------------------------

def _unread_params(module, func_name, exempt=frozenset({"ctx", "pure"})):
    """Parameters the function declares and never loads in its body.

    ``pure``/``--no-plugins`` is consumed by the @scopes_no_plugins decorator,
    so it is wired despite not appearing in the body.
    """
    tree = ast.parse(Path(module.__file__).read_text())
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == func_name
    )
    a = fn.args
    params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    read = {
        n.id for stmt in fn.body for n in ast.walk(stmt)
        if isinstance(n, ast.Name)
    }
    return [p for p in params if p not in read and p not in exempt]


def test_code_declares_no_option_it_ignores():
    """`code` has no unwired-option warning, so it must have none to warn about."""
    assert _unread_params(code_module, "code_main") == []
