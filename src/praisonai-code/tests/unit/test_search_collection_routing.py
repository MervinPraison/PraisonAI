"""Regression tests for issue #2776.

The top-level ``praisonai search`` command is intercepted by the legacy
argparse router (``CapabilitiesHandler.handle_search``) which historically only
accepted ``--max-results`` and performed an OpenAI-style web search. That made
the documented knowledge-base retrieval flags (``--collection``, ``--top-k``,
``--hybrid``) fail with ``unrecognized arguments``.

These tests verify that ``handle_search`` now delegates to the Typer retrieval
CLI (``retrieval.search_command``) when a retrieval flag is present, while
preserving the web-search default for plain queries.
"""

import sys
import types

from praisonai_code.cli.features.capabilities import CapabilitiesHandler


def _install_fake_retrieval(monkeypatch, recorder):
    """Install a fake ``..commands.retrieval`` module and a fake ``typer``."""

    fake_typer = types.ModuleType("typer")

    class _FakeExit(Exception):
        def __init__(self, exit_code=0):
            self.exit_code = exit_code

    class _FakeTyperApp:
        def __call__(self, args, standalone_mode=True):
            recorder["invoked_args"] = list(args)

    fake_typer.Typer = lambda *a, **k: _FakeTyperApp()
    fake_typer.Exit = _FakeExit
    monkeypatch.setitem(sys.modules, "typer", fake_typer)

    fake_retrieval = types.ModuleType(
        "praisonai_code.cli.commands.retrieval"
    )

    def register_commands(app):
        recorder["registered"] = True

    fake_retrieval.register_commands = register_commands
    monkeypatch.setitem(
        sys.modules,
        "praisonai_code.cli.commands.retrieval",
        fake_retrieval,
    )


def test_search_collection_flag_delegates_to_retrieval(monkeypatch):
    recorder = {}
    _install_fake_retrieval(monkeypatch, recorder)

    rc = CapabilitiesHandler.handle_search(
        args=None,
        unknown_args=["test", "--collection", "default"],
    )

    assert rc == 0
    assert recorder.get("registered") is True
    assert recorder["invoked_args"] == ["search", "test", "--collection", "default"]


def test_search_top_k_and_hybrid_flags_delegate(monkeypatch):
    for flag in (["--top-k", "10"], ["-c", "research"], ["--hybrid"]):
        recorder = {}
        _install_fake_retrieval(monkeypatch, recorder)

        rc = CapabilitiesHandler.handle_search(
            args=None,
            unknown_args=["q", *flag],
        )

        assert rc == 0
        assert recorder["invoked_args"] == ["search", "q", *flag]


def test_plain_query_does_not_delegate(monkeypatch):
    """Without retrieval flags, delegation must NOT happen (web-search path)."""
    recorder = {}
    _install_fake_retrieval(monkeypatch, recorder)

    called = {"web": False}

    def fake_cap(*_a, **_k):
        called["web"] = True

        def _search(query, max_results):
            return types.SimpleNamespace(results=[])

        return _search

    monkeypatch.setattr(
        "praisonai_code.cli.features.capabilities._cap",
        fake_cap,
    )

    rc = CapabilitiesHandler.handle_search(
        args=None,
        unknown_args=["just a web search"],
    )

    assert rc == 0
    assert called["web"] is True
    assert "invoked_args" not in recorder
