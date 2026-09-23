"""Regression tests for CLI auto session titles (Issue #5141).

The SDK already ships `generate_title_async`, but the `DefaultSessionStore`
path the CLI uses never called it, so `session list` showed opaque ids. The
`maybe_auto_title_session` wrapper hook must generate a title from the first
user<->assistant exchange, persist it to `metadata["title"]`, skip when a
title/`--title` already exists, and degrade silently on failure.
"""

import pytest


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Isolated project dir + sessions home under the test sandbox."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praison_home"))
    import praisonaiagents.paths as _paths

    sessions_dir = tmp_path / "sessions"

    def _fake_get_sessions_dir():
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    monkeypatch.setattr(_paths, "get_sessions_dir", _fake_get_sessions_dir)
    monkeypatch.setattr(
        "praisonaiagents.session.store.get_sessions_dir", _fake_get_sessions_dir
    )
    return tmp_path


def _store(session_id, contents):
    from praisonai_code.cli.state.project_sessions import get_project_session_store

    store = get_project_session_store()
    for i, content in enumerate(contents):
        role = "user" if i % 2 == 0 else "assistant"
        store.add_message(session_id, role, content)
    return store


def test_auto_title_sets_generated_title(project, monkeypatch):
    """A fresh unnamed session gets a non-id title after the first exchange."""
    import praisonaiagents.session.title as title_mod

    async def _fake(user_msg, assistant_msg, *a, **k):
        return "Debug Python Import Error"

    monkeypatch.setattr(title_mod, "generate_title_async", _fake)

    from praisonai_code.cli.state.project_sessions import (
        get_project_session_store,
        maybe_auto_title_session,
    )

    _store("sess-title", ["fix my import error", "sure, here's how"])

    result = maybe_auto_title_session("sess-title")
    assert result == "Debug Python Import Error"

    store = get_project_session_store()
    data = store.get_session("sess-title")
    assert data.metadata.get("title") == "Debug Python Import Error"


def test_auto_title_skips_when_explicit_title(project, monkeypatch):
    """`--title` (explicit_title=True) must not be overwritten."""
    import praisonaiagents.session.title as title_mod

    async def _fake(user_msg, assistant_msg, *a, **k):  # pragma: no cover
        raise AssertionError("should not be called with explicit title")

    monkeypatch.setattr(title_mod, "generate_title_async", _fake)

    from praisonai_code.cli.state.project_sessions import maybe_auto_title_session

    _store("sess-explicit", ["hi", "hello"])
    assert maybe_auto_title_session("sess-explicit", explicit_title=True) is None


def test_auto_title_skips_when_title_exists(project, monkeypatch):
    """An already-titled session is left untouched."""
    import praisonaiagents.session.title as title_mod

    async def _fake(user_msg, assistant_msg, *a, **k):  # pragma: no cover
        raise AssertionError("should not be called when a title exists")

    monkeypatch.setattr(title_mod, "generate_title_async", _fake)

    from praisonai_code.cli.state.project_sessions import (
        get_project_session_store,
        maybe_auto_title_session,
    )

    store = _store("sess-named", ["hi", "hello"])
    store.rename_session("sess-named", "My Manual Title")

    assert maybe_auto_title_session("sess-named") is None
    data = store.get_session("sess-named")
    assert data.metadata.get("title") == "My Manual Title"


def test_auto_title_no_exchange_yet(project, monkeypatch):
    """Before an assistant reply lands there is nothing to title."""
    import praisonaiagents.session.title as title_mod

    async def _fake(user_msg, assistant_msg, *a, **k):  # pragma: no cover
        raise AssertionError("should not be called before the first pair")

    monkeypatch.setattr(title_mod, "generate_title_async", _fake)

    from praisonai_code.cli.state.project_sessions import maybe_auto_title_session

    _store("sess-partial", ["just a user message"])
    assert maybe_auto_title_session("sess-partial") is None


def test_auto_title_failure_degrades_silently(project, monkeypatch):
    """Generation failure leaves the existing fallback untouched, no error."""
    import praisonaiagents.session.title as title_mod

    async def _boom(user_msg, assistant_msg, *a, **k):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(title_mod, "generate_title_async", _boom)

    from praisonai_code.cli.state.project_sessions import (
        get_project_session_store,
        maybe_auto_title_session,
    )

    _store("sess-fail", ["do something", "done"])
    assert maybe_auto_title_session("sess-fail") is None

    store = get_project_session_store()
    data = store.get_session("sess-fail")
    assert data.metadata.get("title") is None


def test_run_command_invokes_auto_title(project, monkeypatch):
    """`run`'s post-run boundary must invoke the auto-title hook.

    Guards the command wiring itself: if `_record_session_usage` stops calling
    `maybe_auto_title_session` (or passes the wrong id), this fails even though
    the helper-level tests still pass.
    """
    from praisonai_code.cli.commands import run as run_cmd
    from praisonai_code.cli.state import project_sessions

    called = {}

    monkeypatch.setattr(
        project_sessions, "accumulate_session_usage",
        lambda session_id, model=None: {"total_tokens": 0},
    )
    monkeypatch.setattr(
        project_sessions, "maybe_auto_title_session",
        lambda session_id, *a, **k: called.setdefault("session_id", session_id),
    )

    run_cmd._record_session_usage("sess-run", model="gpt-4o-mini", output=None)
    assert called.get("session_id") == "sess-run"


def test_code_command_wires_auto_title(project):
    """`code`'s headless post-run boundary references the auto-title hook.

    `_run_print_code` is heavy to drive end-to-end, so assert statically that
    the post-run block imports and calls `maybe_auto_title_session` on the
    resolved session. This fails if the wiring is removed from `code.py`.
    """
    import inspect
    from praisonai_code.cli.commands import code as code_cmd

    src = inspect.getsource(code_cmd._run_print_code)
    assert "maybe_auto_title_session" in src
    assert "maybe_auto_title_session(resolved_session)" in src
