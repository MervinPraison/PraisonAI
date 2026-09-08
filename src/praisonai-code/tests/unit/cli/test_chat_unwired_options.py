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
import ast
from pathlib import Path

import typer
from typer.testing import CliRunner

import praisonai_code.cli.commands.chat as chat_module


# ``--pure``/``--no-plugins`` is consumed by the @scopes_no_plugins decorator
# rather than by the body, so it is wired despite never being named inside.
_WIRED_BY_DECORATOR = {"ctx", "pure"}


def _chat_main_ast():
    module = ast.parse(Path(chat_module.__file__).read_text())
    return next(
        n for n in ast.walk(module)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "chat_main"
    )


def _chat_main_params():
    a = _chat_main_ast().args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]


def _names_read_by_chat_main():
    """Names actually loaded somewhere in chat_main's body.

    Only the body -- a parameter's default is a ``typer.Option(...)`` call that
    mentions the flag string, not a read of the value.
    """
    return {
        node.id
        for stmt in _chat_main_ast().body
        for node in ast.walk(stmt)
        if isinstance(node, ast.Name)
    }


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

    def test_every_listed_option_really_is_unread(self):
        """Guards the list against drifting as options get wired up.

        Uses the AST, not a regex over source lines: the line-matching version
        failed the moment the word "output" appeared in one of chat_main's own
        comments, which is the same class of bug it exists to catch.
        """
        wired = set(chat_module._UNWIRED_CHAT_OPTIONS) & _names_read_by_chat_main()
        assert not wired, (
            f"now read by chat_main; drop from _UNWIRED_CHAT_OPTIONS so the "
            f"warning stops lying: {sorted(wired)}"
        )

    def test_every_dropped_option_is_named_in_the_table(self):
        """The table must cover the WHOLE gap, not a subset of it.

        It listed four options while nine were silently dropped, so
        `chat --tools web_search` was accepted, ignored, and never mentioned.
        Any declared option chat_main never reads must either be wired or be
        listed here.
        """
        import ast
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(chat_module.chat_main))
        fn = next(
            n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "chat_main"
        )
        defaults = fn.args.defaults
        params = fn.args.args[len(fn.args.args) - len(defaults):]
        declared = [
            a.arg for a, d in zip(params, defaults)
            if "typer.Option" in ast.unparse(d) or "typer.Argument" in ast.unparse(d)
        ]
        read = {
            n.id for n in ast.walk(fn)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }
        # `pure` is consumed by the @scopes_no_plugins decorator, which reads it
        # out of **kwargs rather than from the body.
        unread = [
            p for p in declared
            if p not in read and p != "pure"
        ]
        missing = [p for p in unread if p not in chat_module._UNWIRED_CHAT_OPTIONS]
        assert not missing, (
            f"chat declares and silently drops {missing}; wire them or add them "
            f"to _UNWIRED_CHAT_OPTIONS so the user is told"
        )


class TestNewlyWiredOptions:
    """--continue, --no-acp and --no-lsp were dropped; now they reach the TUI."""

    def test_no_acp_disables_acp_on_the_config(self, monkeypatch):
        _StubTUI.last_config = None
        _run(monkeypatch, "--no-acp")
        assert _StubTUI.last_config.enable_acp is False

    def test_no_lsp_disables_lsp_on_the_config(self, monkeypatch):
        _StubTUI.last_config = None
        _run(monkeypatch, "--no-lsp")
        assert _StubTUI.last_config.enable_lsp is False

    def test_acp_and_lsp_stay_enabled_by_default(self, monkeypatch):
        _StubTUI.last_config = None
        _run(monkeypatch)
        assert _StubTUI.last_config.enable_acp is True
        assert _StubTUI.last_config.enable_lsp is True

    def test_continue_resolves_the_last_session_onto_the_config(self, monkeypatch):
        monkeypatch.setattr(
            "praisonai_code.cli.state.project_sessions.find_last_session",
            lambda *a, **k: "sess-123",
        )
        _StubTUI.last_config = None
        _run(monkeypatch, "--continue")
        assert _StubTUI.last_config.session_id == "sess-123"
        assert _StubTUI.last_config.resume is True

    def test_without_continue_no_session_is_resumed(self, monkeypatch):
        monkeypatch.setattr(
            "praisonai_code.cli.state.project_sessions.find_last_session",
            lambda *a, **k: "sess-123",
        )
        _StubTUI.last_config = None
        _run(monkeypatch)
        assert _StubTUI.last_config.session_id is None
        assert _StubTUI.last_config.resume is False

    def test_none_of_them_trigger_the_unwired_warning(self, monkeypatch):
        monkeypatch.setattr(
            "praisonai_code.cli.state.project_sessions.find_last_session",
            lambda *a, **k: "sess-123",
        )
        out = _run(monkeypatch, "--no-acp", "--no-lsp", "--continue").output
        assert "does not implement" not in out


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

    def test_comma_in_single_value_capability_is_not_split(self):
        """A comma-containing guardrail prompt is one string, not a list.

        `Agent(guardrails=...)` takes a single validator prompt, so a valid
        `--guardrails="Be accurate, cite sources"` must survive intact -- only
        `--knowledge` (a source list) may split on commas. Splitting it would
        pass a list where Agent expects a str and break session startup.
        """
        from praisonai_code.cli.interactive.async_tui import (
            AsyncTUIConfig,
            _apply_capability_options,
        )

        cfg = AsyncTUIConfig(guardrails="Be accurate, cite sources")
        agent_config = {}
        _apply_capability_options(agent_config, cfg)
        assert agent_config["guardrails"] == "Be accurate, cite sources"

    def test_only_knowledge_splits_on_commas(self):
        """Comma-splitting is scoped to source-list capabilities (knowledge)."""
        from praisonai_code.cli.interactive.async_tui import (
            AsyncTUIConfig,
            _apply_capability_options,
        )

        cfg = AsyncTUIConfig(
            knowledge="docs/,notes.md",
            web="a,b",
            execution="fast,slow",
        )
        agent_config = {}
        _apply_capability_options(agent_config, cfg)
        assert agent_config["knowledge"] == ["docs/", "notes.md"]
        assert agent_config["web"] == "a,b"
        assert agent_config["execution"] == "fast,slow"
