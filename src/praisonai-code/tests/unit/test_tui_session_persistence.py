"""The interactive TUI must actually save sessions.

Issue #4910 gave the TUI a working resume path: ``/continue`` records
``_resume_session_id``, and ``_build_agent`` rehydrates the agent from the
session store so a follow-up prompt is answered *with* the restored
conversation rather than only redisplaying it.

But nothing in the TUI ever *wrote* a session. A fresh ``praisonai chat``, a
bare ``praisonai``, or a standalone ``praisonai code`` produced zero saved
sessions, so ``/sessions`` answered "No saved sessions found.", ``/continue``
had nothing to continue, and every conversation on the default interactive path
was lost on exit. The resume machinery worked; there was never anything for it
to find.

Two stores are involved and both must be populated:

* the flat ``UnifiedSessionStore`` -- what ``/sessions`` lists and
  ``/continue`` loads;
* the project session store -- what ``apply_cli_session_continuity`` reads to
  rehydrate the agent.
"""

import ast
from pathlib import Path

import pytest

from praisonai_code.cli.interactive import async_tui as tui_mod
from praisonai_code.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig
from praisonai_code.cli.session import UnifiedSessionStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the TUI's session store at a temp dir, not the user's ~/.praisonai."""
    session_store = UnifiedSessionStore(session_dir=tmp_path / "sessions")
    import praisonai_code.cli.session as session_pkg

    monkeypatch.setattr(session_pkg, "get_session_store", lambda: session_store)
    return session_store


@pytest.fixture
def project_store(tmp_path, monkeypatch):
    """Isolate the project session store the agent rehydrates from.

    ``apply_cli_session_continuity`` reads this store, not the flat unified one,
    so ``/import`` must write here for the model to actually see the transcript.
    """
    from praisonaiagents.session.store import DefaultSessionStore

    proj_store = DefaultSessionStore(session_dir=str(tmp_path / "project_sessions"))
    import praisonai_code.cli.state.project_sessions as proj_mod

    monkeypatch.setattr(
        proj_mod, "get_project_session_store", lambda *a, **k: proj_store
    )
    return proj_store


def _make_tui(tmp_path, session_id):
    # workspace=tmp_path keeps __init__'s file scan off the real repo tree.
    return AsyncTUI(AsyncTUIConfig(
        session_id=session_id,
        workspace=str(tmp_path),
        show_logo=False,
    ))


def test_a_completed_turn_is_written_to_disk(tmp_path, store):
    tui = _make_tui(tmp_path, "sess-one")

    tui._persist_turn("what is 2+2", "4")

    saved = store.load("sess-one")
    assert saved is not None, "the turn was never persisted"
    roles = [(m["role"], m["content"]) for m in saved.get_chat_history()]
    assert ("user", "what is 2+2") in roles
    assert ("assistant", "4") in roles


def test_the_session_is_then_listed_by_sessions(tmp_path, store):
    tui = _make_tui(tmp_path, "sess-listed")
    tui._persist_turn("hello", "hi")

    listed = {s.get("session_id") for s in store.list_sessions()}
    assert "sess-listed" in listed, (
        "/sessions would still report 'No saved sessions found.'"
    )


def test_a_persisted_session_can_actually_be_continued(tmp_path, store):
    """End to end: what one TUI saves, the next one's /continue restores."""
    writer = _make_tui(tmp_path, "sess-two")
    writer._persist_turn("my name is Ada", "Nice to meet you, Ada.")

    reader = _make_tui(tmp_path, "sess-three")
    assert reader._handle_command("/continue") is True

    assert reader.session_id == "sess-two"
    contents = [m.get("content") for m in reader._conversation_history]
    assert "my name is Ada" in contents
    # Issue #4910's contract: the resumed id is recorded so the agent built
    # next is rehydrated from it rather than starting empty.
    assert reader._resume_session_id == "sess-two"


def test_a_turn_survives_a_storage_failure(tmp_path, store, monkeypatch):
    """Persistence is best-effort: it must never break the completed turn."""
    def _boom(session):
        raise OSError("disk full")

    monkeypatch.setattr(store, "save", _boom)
    tui = _make_tui(tmp_path, "sess-four")

    tui._persist_turn("hello", "hi")  # must not raise


def test_import_reaches_the_model_not_only_the_screen(tmp_path, store, project_store):
    """/import reported "Imported N messages" and answered as if none existed.

    The rebuilt agent restores from the *project* store, so the imported turns
    must land there -- not only in the flat unified store /sessions lists.
    """
    transcript = tmp_path / "conv.json"
    transcript.write_text(
        '{"session_id": "imported", "messages": ['
        '{"role": "user", "content": "the passphrase is oakleaf"},'
        '{"role": "assistant", "content": "Understood."}]}'
    )

    tui = _make_tui(tmp_path, "sess-five")
    assert tui._handle_command(f"/import {transcript}") is True

    assert tui._resume_session_id == "imported", (
        "imported turns never reached the agent-rehydration path"
    )
    # The store the model actually rehydrates from must hold the transcript.
    project_history = project_store.get_chat_history("imported")
    assert "the passphrase is oakleaf" in [
        m["content"] for m in project_history
    ], "the model would receive none of the imported conversation"
    # And the flat store keeps it discoverable to /sessions and /continue.
    saved = store.load("imported")
    assert saved is not None
    assert "the passphrase is oakleaf" in [
        m["content"] for m in saved.get_chat_history()
    ]


def test_import_preserves_a_trailing_unpaired_message(tmp_path, store, project_store):
    """The old pair-stepping loop dropped a trailing/non-alternating message."""
    transcript = tmp_path / "odd.json"
    transcript.write_text(
        '{"session_id": "odd", "messages": ['
        '{"role": "user", "content": "first"},'
        '{"role": "assistant", "content": "reply"},'
        '{"role": "user", "content": "trailing question"}]}'
    )

    tui = _make_tui(tmp_path, "sess-odd")
    assert tui._handle_command(f"/import {transcript}") is True

    contents = [m["content"] for m in project_store.get_chat_history("odd")]
    assert "trailing question" in contents, (
        "the final unpaired turn was dropped before the model saw it"
    )


@pytest.mark.parametrize("command", ["/clear", "/new"])
def test_clear_and_new_also_drop_the_models_context(tmp_path, store, command):
    tui = _make_tui(tmp_path, "sess-six")
    tui._conversation_history = [{"role": "user", "content": "stale turn"}]
    tui._resume_session_id = "sess-six"
    tui._agent = object()

    tui._handle_command(command)

    assert tui._conversation_history == []
    assert tui._agent is None, (
        f"{command} cleared the screen but kept the agent holding the "
        f"conversation it just cleared"
    )
    assert tui._resume_session_id is None
    # Rotating the session id is what severs the model context: the rebuilt
    # agent wires continuity from the current id and re-reads its stored turns,
    # so keeping the id would reload the exact conversation just cleared.
    assert tui.session_id != "sess-six", (
        f"{command} kept the session id, so the next prompt would reload the "
        f"cleared conversation from the project store"
    )


def test_clear_does_not_rehydrate_the_cleared_conversation(
    tmp_path, store, project_store, monkeypatch
):
    """After /clear, a rebuilt agent must not restore the cleared turns.

    The project store still holds the pre-clear turns under the *old* id; the
    fix rotates ``session_id`` so ``apply_cli_session_continuity`` reads an
    empty history for the new id instead.
    """
    project_store.set_chat_history(
        "sess-clear",
        [
            {"role": "user", "content": "secret is orchid"},
            {"role": "assistant", "content": "noted"},
        ],
    )

    tui = _make_tui(tmp_path, "sess-clear")
    tui._conversation_history = [{"role": "user", "content": "secret is orchid"}]

    tui._handle_command("/clear")

    # The continuity read for the rotated id must be empty.
    assert project_store.get_chat_history(tui.session_id) == [], (
        "the cleared conversation is still reachable under the new session id"
    )


def _source_of(func_name: str):
    """Parse the module and return the named function's AST node.

    Parses the file rather than using ``inspect.getsource``: some methods embed
    triple-quoted help text at column 0, which defeats dedent.
    """
    module = ast.parse(Path(tui_mod.__file__).read_text())
    return next(
        n for n in ast.walk(module)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == func_name
    )


def _calls_in(func_name: str) -> set:
    """Names of ``self.<method>()`` calls made inside ``func_name``."""
    return {
        node.func.attr
        for node in ast.walk(_source_of(func_name))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    }


def test_both_turn_loops_are_wired_to_the_store():
    """Pin the call sites, so persistence cannot be quietly unhooked again."""
    assert "_persist_turn" in _calls_in("_execute_in_background")
    assert "_persist_turn" in _calls_in("_run_simple"), (
        "the no-prompt_toolkit fallback loop still records nothing"
    )


def test_a_fresh_session_is_wired_for_auto_save():
    """The agent must persist a brand-new session, not only a resumed one.

    Before this, continuity was wired only when ``_resume_session_id`` was set,
    so a first-ever session wrote nothing -- and therefore could never become a
    session to resume.
    """
    src = _source_of("_build_agent")
    call = next(
        n for n in ast.walk(src)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "apply_cli_session_continuity"
    )
    kwargs = {k.arg for k in call.keywords}
    assert "auto_save" in kwargs, "the agent will restore history but never save it"
