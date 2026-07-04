"""Tests for praison run project-scoped session continuity."""

from praisonai.cli.state.project_sessions import (
    apply_cli_session_continuity,
    build_cli_memory_config,
    find_last_session,
    get_project_session_store,
    list_project_sessions,
)
from praisonaiagents import Agent
from praisonaiagents.session.store import get_default_session_store


def test_build_cli_memory_config_enables_history():
    cfg = build_cli_memory_config(session_id="sess-1", auto_save="sess-1")
    assert cfg is not None
    assert cfg.session_id == "sess-1"
    assert cfg.auto_save == "sess-1"
    assert cfg.history is True


def test_apply_cli_session_continuity_restores_project_history():
    store = get_project_session_store()
    session_id = "continuity-unit-test"
    store.clear_session(session_id)
    store.add_user_message(session_id, "remember this")
    store.add_assistant_message(session_id, "acknowledged")

    agent = Agent(name="RunAgent", memory=build_cli_memory_config(session_id, session_id))
    apply_cli_session_continuity(agent, session_id)

    assert agent._session_store.session_dir == store.session_dir
    assert agent._session_id == session_id
    assert len(agent.chat_history) == 2
    assert agent.chat_history[0]["content"] == "remember this"

    agent.chat_history.append({"role": "user", "content": "follow-up"})
    agent.chat_history.append({"role": "assistant", "content": "reply"})
    agent._auto_save_session()

    saved = store.get_chat_history(session_id)
    assert len(saved) == 4
    assert saved[-1]["content"] == "reply"

    store.clear_session(session_id)


def test_injected_session_store_not_overwritten():
    store = get_project_session_store()
    session_id = "store-injection-test"
    store.clear_session(session_id)

    agent = Agent(name="RunAgent", memory=build_cli_memory_config(session_id, session_id))
    apply_cli_session_continuity(agent, session_id)
    injected_dir = agent._session_store.session_dir

    agent._init_session_store()
    assert agent._session_store.session_dir == injected_dir

    store.clear_session(session_id)


def test_find_last_session_sees_global_agent_session():
    """A session created via the core global store (e.g. Agent(session_id=...))
    must be visible to `--continue`/find_last_session and to the merged
    listing, not only project-scoped run sessions (Issue #2655)."""
    global_store = get_default_session_store()
    session_id = "issue-2655-global-session"
    global_store.delete_session(session_id)
    global_store.add_user_message(session_id, "created by core Agent")

    try:
        assert find_last_session() == session_id

        listed = {s.get("session_id") for s in list_project_sessions()}
        assert session_id in listed
    finally:
        global_store.delete_session(session_id)


def test_find_last_session_skips_sub_agent_child():
    """`--continue` resolves to the last root session, never a sub-agent child
    marked with a parent_id in metadata (Issue #2655)."""
    store = get_project_session_store()
    root_id = "issue-2655-root"
    child_id = "issue-2655-child"
    store.delete_session(root_id)
    store.delete_session(child_id)

    store.add_user_message(root_id, "root conversation")
    store.add_user_message(child_id, "sub-agent work")
    store.update_session_metadata(child_id, parent_id=root_id)

    try:
        assert find_last_session() == root_id
    finally:
        store.delete_session(root_id)
        store.delete_session(child_id)