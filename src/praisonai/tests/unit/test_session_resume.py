"""Unit tests for the deterministic CLI session resume helper."""

import importlib

import pytest


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    """Point the global default session store at a temp directory."""
    store_mod = importlib.import_module("praisonaiagents.session.store")
    store = store_mod.DefaultSessionStore(session_dir=str(tmp_path))
    monkeypatch.setattr(store_mod, "_default_store", store, raising=False)
    return store


def test_rehydrate_restores_history_model_agent(temp_store):
    from praisonai.cli.session.resume import rehydrate_session

    temp_store.add_user_message("s1", "codename is Falcon")
    temp_store.add_assistant_message("s1", "Understood.")
    temp_store.update_session_metadata("s1", model="gpt-4o-mini", agent_name="RunAgent")

    restored = rehydrate_session("s1")

    assert restored.found is True
    assert restored.model == "gpt-4o-mini"
    assert restored.agent_name == "RunAgent"
    assert restored.chat_history == [
        {"role": "user", "content": "codename is Falcon"},
        {"role": "assistant", "content": "Understood."},
    ]


def test_rehydrate_missing_session_returns_not_found(temp_store):
    from praisonai.cli.session.resume import rehydrate_session

    restored = rehydrate_session("nope")

    assert restored.found is False
    assert restored.chat_history == []
    assert restored.session_id == "nope"


def test_rehydrate_falls_back_to_llm_metadata_key(temp_store):
    from praisonai.cli.session.resume import rehydrate_session

    temp_store.add_user_message("s2", "hello")
    temp_store.update_session_metadata("s2", llm="claude-3-5-sonnet")

    restored = rehydrate_session("s2")

    assert restored.found is True
    assert restored.model == "claude-3-5-sonnet"


@pytest.fixture
def temp_project_store(tmp_path, monkeypatch):
    """Point the project-scoped session store at a temp directory."""
    store_mod = importlib.import_module("praisonaiagents.session.store")
    store = store_mod.DefaultSessionStore(session_dir=str(tmp_path / "project"))

    proj_mod = importlib.import_module("praisonai.cli.state.project_sessions")
    monkeypatch.setattr(
        proj_mod, "get_project_session_store", lambda *a, **k: store
    )
    return store


def test_rehydrate_uses_project_store_first(temp_project_store):
    from praisonai.cli.session.resume import rehydrate_session

    temp_project_store.add_user_message("p1", "from project store")
    temp_project_store.update_session_metadata("p1", model="gpt-4o", agent_name="ProjAgent")

    restored = rehydrate_session("p1")

    assert restored.found is True
    assert restored.model == "gpt-4o"
    assert restored.agent_name == "ProjAgent"
    assert restored.chat_history == [
        {"role": "user", "content": "from project store"},
    ]


def test_rehydrate_falls_back_from_project_to_global(temp_project_store, temp_store):
    from praisonai.cli.session.resume import rehydrate_session

    # Session only exists in the global store, not the project store.
    temp_store.add_user_message("g1", "only in global")
    temp_store.update_session_metadata("g1", model="gpt-4o-mini")

    restored = rehydrate_session("g1")

    assert restored.found is True
    assert restored.model == "gpt-4o-mini"
    assert restored.chat_history == [
        {"role": "user", "content": "only in global"},
    ]


def test_session_exists_anywhere_checks_both_stores(temp_project_store, temp_store):
    from praisonai.cli.state.project_sessions import session_exists_anywhere

    temp_project_store.add_user_message("inproj", "x")
    temp_store.add_user_message("inglobal", "y")

    assert session_exists_anywhere("inproj") is True
    assert session_exists_anywhere("inglobal") is True
    assert session_exists_anywhere("missing") is False
