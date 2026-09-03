"""`praisonai chat` must not accept options it silently ignores.

chat_main declares many parameters and dispatches to the async TUI. Twelve of
those options reach neither the TUI config nor any other runtime path -- there
is no locals(), ctx.params or **kwargs pass-through in the command body.

So `praisonai chat --planning auto --guardrails strict` looked like it had
configured something and had not: accepted, validated by typer, and dropped.

Wiring the twelve up is twelve separate features. Saying so is one line, and
it stops the CLI making a promise it does not keep. These tests pin that the
warning names exactly what was supplied, and stays quiet otherwise.

The tests stub the *actual* runtime chat_main dispatches to -- the credential
gate and the async TUI -- so a supplied option exercises the warning without
depending on external state (an API key, a local endpoint, or a real TTY).
"""
import typer
from typer.testing import CliRunner

import praisonai_code.cli.commands.chat as chat_module


class _StubTUI:
    """Stand-in for AsyncTUI: constructs cleanly and never runs a real chat."""

    execution_failed = False

    def __init__(self, *args, **kwargs):
        pass

    def run_single(self, prompt):
        return ""

    def run(self):
        return None


def _app(monkeypatch):
    """chat_main, with the credential gate and async TUI stubbed out.

    chat_main resolves a model, runs the credential gate, then dispatches to
    AsyncTUI -- none of which should touch the network or exit non-zero in a
    unit test. Both are imported locally inside chat_main, so they are patched
    at their source modules.
    """
    monkeypatch.setattr(
        "praisonai_code.llm.credentials.ensure_configured_or_onboard",
        lambda model=None, interactive=True: model,
    )
    monkeypatch.setattr(
        "praisonai_code.cli.interactive.async_tui.AsyncTUI", _StubTUI
    )
    app = typer.Typer()
    app.command()(chat_module.chat_main)
    return app


def _run(monkeypatch, *args):
    return CliRunner().invoke(_app(monkeypatch), ["hi", *args])


class TestUnwiredChatOptions:

    def test_a_supplied_unwired_option_is_reported(self, monkeypatch):
        out = _run(monkeypatch, "--planning", "auto").output
        assert "does not implement" in out
        assert "--planning" in out

    def test_only_the_supplied_ones_are_named(self, monkeypatch):
        out = _run(monkeypatch, "--planning", "auto").output
        assert "--planning" in out
        assert "--guardrails" not in out, "named an option the user never passed"

    def test_several_are_listed_together(self, monkeypatch):
        out = _run(monkeypatch, "--planning", "auto", "--guardrails", "strict",
                   "--theme", "dark").output
        for flag in ("--planning", "--guardrails", "--theme"):
            assert flag in out, flag

    def test_nothing_is_said_when_none_are_supplied(self, monkeypatch):
        assert "does not implement" not in _run(monkeypatch).output

    def test_a_wired_option_never_triggers_the_warning(self, monkeypatch):
        """--model and --continue are honoured, so they must stay silent."""
        out = _run(monkeypatch, "--model", "gpt-4o-mini", "--continue").output
        assert "does not implement" not in out

    def test_the_command_still_succeeds(self, monkeypatch):
        """A warning must not become a failure."""
        assert _run(monkeypatch, "--planning", "auto").exit_code == 0

    def test_every_listed_option_really_is_unread(self, monkeypatch):
        """Guards the list itself against drifting as options get wired up.

        If someone implements one of these, this test fails and tells them to
        drop it from the table rather than leaving a false warning behind.
        """
        import inspect
        import re

        src = inspect.getsource(chat_module.chat_main)
        body = src[src.index("):"):]
        for name in chat_module._UNWIRED_CHAT_OPTIONS:
            uses = [
                line for line in body.splitlines()
                if re.search(rf"\b{re.escape(name)}\b", line)
                and "_UNWIRED_CHAT_OPTIONS" not in line
                and "_warn_about_unwired_options" not in line
            ]
            assert not uses, (
                f"{name} is now read by chat_main; remove it from "
                f"_UNWIRED_CHAT_OPTIONS so the warning stops lying"
            )
