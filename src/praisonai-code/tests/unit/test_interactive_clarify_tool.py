"""Tests for wiring the human-in-the-loop ``clarify`` tool into the default
interactive toolset (#4762).

The terminal coding agent must be able to pause and ask one focused clarifying
question when genuinely blocked, instead of silently guessing. The core already
owns ``ClarifyTool`` + ``create_cli_clarify_handler``; these tests verify the
CLI wrapper offers the ``clarify`` tool when an interactive channel exists and
withholds it (preserving the best-judgment fallback) in headless/non-TTY/JSON
runs so scripted runs never block.
"""

import asyncio

import pytest

from praisonai_code.cli.features import interactive_tools as it
from praisonai_code.cli.features.interactive_tools import (
    TOOL_GROUPS,
    ToolConfig,
    get_interactive_tools,
    resolve_tool_groups,
)

_clarify_available = True
try:  # pragma: no cover - environment dependent
    import praisonaiagents.tools.clarify  # noqa: F401
except ImportError:  # pragma: no cover
    _clarify_available = False

requires_clarify = pytest.mark.skipif(
    not _clarify_available,
    reason="praisonaiagents clarify tool not installed",
)


def test_clarify_group_defined():
    assert TOOL_GROUPS["clarify"] == ["clarify"]


def test_clarify_in_default_interactive_group():
    assert "clarify" in TOOL_GROUPS["interactive"]


def test_resolve_includes_clarify_by_default():
    assert "clarify" in resolve_tool_groups()


def test_resolve_clarify_group_only():
    assert resolve_tool_groups(groups=["clarify"]) == {"clarify"}


def test_disable_clarify_via_config():
    cfg = ToolConfig()
    cfg.enable_clarify = False
    assert "clarify" not in resolve_tool_groups(config=cfg)


def test_disable_clarify_via_env(monkeypatch):
    monkeypatch.setenv("PRAISON_TOOLS_DISABLE", "clarify")
    cfg = ToolConfig.from_env()
    assert cfg.enable_clarify is False


def test_channel_unavailable_when_not_tty(monkeypatch):
    monkeypatch.delenv("PRAISON_NO_CLARIFY", raising=False)
    monkeypatch.delenv("PRAISON_OUTPUT_MODE", raising=False)

    class _NotTTY:
        def isatty(self):
            return False

    monkeypatch.setattr(it.sys, "stdin", _NotTTY(), raising=False)
    monkeypatch.setattr(it.sys, "stdout", _NotTTY(), raising=False)
    assert it._interactive_channel_available() is False


def test_channel_available_when_tty(monkeypatch):
    monkeypatch.delenv("PRAISON_NO_CLARIFY", raising=False)
    monkeypatch.delenv("PRAISON_OUTPUT_MODE", raising=False)
    monkeypatch.delenv("CI", raising=False)

    class _TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(it.sys, "stdin", _TTY(), raising=False)
    monkeypatch.setattr(it.sys, "stdout", _TTY(), raising=False)
    assert it._interactive_channel_available() is True


def test_channel_unavailable_with_no_clarify_env(monkeypatch):
    monkeypatch.delenv("CI", raising=False)

    class _TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(it.sys, "stdin", _TTY(), raising=False)
    monkeypatch.setattr(it.sys, "stdout", _TTY(), raising=False)
    monkeypatch.setenv("PRAISON_NO_CLARIFY", "1")
    assert it._interactive_channel_available() is False


def test_channel_unavailable_in_ci_even_with_tty(monkeypatch):
    """CI runners can allocate pseudo-terminals; never prompt when CI is set."""
    monkeypatch.delenv("PRAISON_NO_CLARIFY", raising=False)
    monkeypatch.delenv("PRAISON_OUTPUT_MODE", raising=False)

    class _TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(it.sys, "stdin", _TTY(), raising=False)
    monkeypatch.setattr(it.sys, "stdout", _TTY(), raising=False)
    monkeypatch.setenv("CI", "true")
    assert it._interactive_channel_available() is False


def test_channel_unavailable_with_json_output(monkeypatch):
    class _TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(it.sys, "stdin", _TTY(), raising=False)
    monkeypatch.setattr(it.sys, "stdout", _TTY(), raising=False)
    monkeypatch.delenv("PRAISON_NO_CLARIFY", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("PRAISON_OUTPUT_MODE", "json")
    assert it._interactive_channel_available() is False


@requires_clarify
def test_clarify_withheld_when_headless(monkeypatch):
    monkeypatch.setattr(it, "_interactive_channel_available", lambda: False)
    tools = it._load_clarify_tools(ToolConfig())
    assert tools == {}


@requires_clarify
def test_clarify_loaded_and_invokable_when_interactive(monkeypatch):
    monkeypatch.setattr(it, "_interactive_channel_available", lambda: True)

    captured = {}

    def fake_handler():
        from praisonaiagents.tools.clarify import ClarifyHandler

        def ask(question, choices=None):
            captured["question"] = question
            captured["choices"] = choices
            return "user answer"

        return ClarifyHandler(ask_callback=ask)

    monkeypatch.setattr(
        "praisonaiagents.tools.clarify.create_cli_clarify_handler",
        fake_handler,
    )

    tools = it._load_clarify_tools(ToolConfig())
    assert "clarify" in tools

    clarify = tools["clarify"]
    answer = asyncio.run(clarify("Which file?", choices=["a.py", "b.py"]))
    assert answer == "user answer"
    assert captured["question"] == "Which file?"
    assert captured["choices"] == ["a.py", "b.py"]


@requires_clarify
def test_get_interactive_tools_includes_clarify_when_interactive(monkeypatch):
    monkeypatch.setattr(it, "_interactive_channel_available", lambda: True)
    tools = get_interactive_tools(config=ToolConfig())
    names = {getattr(t, "__name__", "") for t in tools}
    assert "clarify" in names


@requires_clarify
def test_get_interactive_tools_omits_clarify_when_headless(monkeypatch):
    monkeypatch.setattr(it, "_interactive_channel_available", lambda: False)
    tools = get_interactive_tools(config=ToolConfig())
    names = {getattr(t, "__name__", "") for t in tools}
    assert "clarify" not in names
