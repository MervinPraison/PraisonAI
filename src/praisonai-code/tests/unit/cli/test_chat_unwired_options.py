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
    """Stand-in for AsyncTUI: constructs cleanly and never runs a real chat.

    Captures the config it was constructed with so parity tests can assert the
    high-value capability options were threaded through to the runtime.
    """

    execution_failed = False
    last_config = None

    def __init__(self, config=None, *args, **kwargs):
        type(self).last_config = config

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
        out = _run(monkeypatch, "--theme", "dark").output
        assert "does not implement" in out
        assert "--theme" in out

    def test_only_the_supplied_ones_are_named(self, monkeypatch):
        out = _run(monkeypatch, "--theme", "dark").output
        assert "--theme" in out
        assert "--ui-backend" not in out, "named an option the user never passed"

    def test_several_are_listed_together(self, monkeypatch):
        out = _run(monkeypatch, "--theme", "dark", "--no-color",
                   "--ui-backend", "plain").output
        for flag in ("--theme", "--no-color", "--ui-backend"):
            assert flag in out, flag

    def test_nothing_is_said_when_none_are_supplied(self, monkeypatch):
        assert "does not implement" not in _run(monkeypatch).output

    def test_a_wired_option_never_triggers_the_warning(self, monkeypatch):
        """--model and --continue are honoured, so they must stay silent."""
        out = _run(monkeypatch, "--model", "gpt-4o-mini", "--continue").output
        assert "does not implement" not in out

    def test_a_wired_capability_option_never_triggers_the_warning(self, monkeypatch):
        """The now-wired capability options must not warn (issue #4890)."""
        out = _run(monkeypatch, "--guardrails", "strict", "--planning", "auto").output
        assert "does not implement" not in out

    def test_the_command_still_succeeds(self, monkeypatch):
        """A warning must not become a failure."""
        assert _run(monkeypatch, "--theme", "dark").exit_code == 0

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


class TestWiredCapabilityOptions:
    """`chat` must honour the high-value capability options (issue #4890).

    These reach the same consolidated Agent params `run`/YAML/Python use. The
    stub TUI records the AsyncTUIConfig it is built with, so we can assert a
    supplied flag lands on the config, and that the config -> Agent mapping
    (_apply_capability_options) produces the expected constructor kwargs.
    """

    def test_supplied_capability_options_reach_the_tui_config(self, monkeypatch):
        _StubTUI.last_config = None
        _run(monkeypatch, "--guardrails", "strict", "--knowledge", "docs/",
             "--web", "true", "--planning", "auto")
        cfg = _StubTUI.last_config
        assert cfg is not None
        assert cfg.guardrails == "strict"
        assert cfg.knowledge == "docs/"
        assert cfg.web == "true"
        assert cfg.planning == "auto"

    def test_unset_capability_options_stay_none(self, monkeypatch):
        _StubTUI.last_config = None
        _run(monkeypatch)
        cfg = _StubTUI.last_config
        assert cfg is not None
        for name in ("guardrails", "knowledge", "web", "planning",
                     "reflection", "context", "execution", "caching"):
            assert getattr(cfg, name) is None, name

    def test_config_maps_onto_agent_constructor_kwargs(self):
        from praisonai_code.cli.interactive.async_tui import (
            AsyncTUIConfig,
            _apply_capability_options,
        )

        cfg = AsyncTUIConfig(
            guardrails="strict", knowledge="docs/,notes.md", web="true",
            planning="false",
        )
        agent_config = {}
        _apply_capability_options(agent_config, cfg)
        assert agent_config["guardrails"] == "strict"
        assert agent_config["knowledge"] == ["docs/", "notes.md"]
        assert agent_config["web"] is True
        assert agent_config["planning"] is False

    def test_unset_options_are_not_added_to_agent_kwargs(self):
        from praisonai_code.cli.interactive.async_tui import (
            AsyncTUIConfig,
            _apply_capability_options,
        )

        agent_config = {}
        _apply_capability_options(agent_config, AsyncTUIConfig())
        for name in ("guardrails", "knowledge", "web", "planning",
                     "reflection", "context", "execution", "caching"):
            assert name not in agent_config, name
