"""Tests for praison run project-scoped session continuity."""

from praisonai.cli.state.project_sessions import (
    apply_cli_session_continuity,
    build_cli_memory_config,
    get_project_session_store,
)
from praisonaiagents import Agent


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
