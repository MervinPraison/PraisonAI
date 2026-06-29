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


def _track(input_tokens, output_tokens, model="gpt-4o-mini"):
    """Feed a fake LLM call into the global token collector."""
    from praisonaiagents.telemetry.token_collector import (
        TokenMetrics,
        get_token_collector,
    )

    get_token_collector().track_tokens(
        model, "Agent", TokenMetrics(input_tokens=input_tokens, output_tokens=output_tokens)
    )


@pytest.fixture(autouse=False)
def reset_collector():
    from praisonaiagents.telemetry.token_collector import get_token_collector

    get_token_collector().reset()
    yield
    get_token_collector().reset()


def test_accumulate_session_usage_persists_totals(temp_project_store, reset_collector):
    from praisonai.cli.state.project_sessions import (
        accumulate_session_usage,
        read_session_usage,
    )

    temp_project_store.add_user_message("u1", "hi")

    _track(1000, 500)
    _track(240, 3480)
    usage = accumulate_session_usage("u1", model="gpt-4o-mini")

    assert usage["input_tokens"] == 1240
    assert usage["output_tokens"] == 3980
    assert usage["total_tokens"] == 5220
    assert usage["requests"] == 2
    assert usage["cost"] > 0

    # Persisted and re-readable.
    assert read_session_usage("u1")["total_tokens"] == 5220


def test_accumulate_session_usage_is_cumulative_across_runs(temp_project_store, reset_collector):
    from praisonai.cli.state.project_sessions import accumulate_session_usage

    temp_project_store.add_user_message("u2", "hi")

    _track(100, 200)
    first = accumulate_session_usage("u2", model="gpt-4o-mini")
    assert first["total_tokens"] == 300

    # A second run's usage adds to the first (collector reset internally).
    _track(50, 50)
    second = accumulate_session_usage("u2", model="gpt-4o-mini")
    assert second["total_tokens"] == 400
    assert second["requests"] == 2


def test_rehydrate_restores_usage(temp_project_store, reset_collector):
    from praisonai.cli.session.resume import rehydrate_session
    from praisonai.cli.state.project_sessions import accumulate_session_usage

    temp_project_store.add_user_message("u3", "hi")
    _track(500, 700)
    accumulate_session_usage("u3", model="gpt-4o-mini")

    restored = rehydrate_session("u3")
    assert restored.found is True
    assert restored.usage.get("total_tokens") == 1200


def test_accumulate_prices_per_model(temp_project_store, reset_collector):
    """Multi-model runs are priced per-model, not with a single CLI model."""
    from praisonai.cli.features.cost_tracker import get_pricing
    from praisonai.cli.state.project_sessions import accumulate_session_usage

    temp_project_store.add_user_message("um", "hi")

    _track(1000, 1000, model="gpt-4o-mini")
    _track(1000, 1000, model="gpt-4o")

    # Pass an unrelated CLI model to prove the cost derives from by_model, not it.
    usage = accumulate_session_usage("um", model="gpt-4o-mini")

    expected = get_pricing("gpt-4o-mini").calculate_cost(1000, 1000) + \
        get_pricing("gpt-4o").calculate_cost(1000, 1000)
    assert usage["cost"] == pytest.approx(round(expected, 6))
    assert usage["total_tokens"] == 4000


def test_accumulate_uses_global_store_after_resume(temp_project_store, temp_store, reset_collector):
    """Usage for a globally-stored session accumulates into that same store."""
    from praisonai.cli.state.project_sessions import (
        accumulate_session_usage,
        read_session_usage,
    )

    # Session only exists in the global store (e.g. created by the gateway/TUI).
    temp_store.add_user_message("gonly", "hi")

    _track(100, 200)
    usage = accumulate_session_usage("gonly", model="gpt-4o-mini")
    assert usage["total_tokens"] == 300

    # Persisted into the global store and re-readable from there.
    assert read_session_usage("gonly")["total_tokens"] == 300
    global_meta = temp_store.get_session("gonly").metadata
    assert global_meta.get("usage", {}).get("total_tokens") == 300
    # The project store must NOT have shadow-created the session.
    assert not temp_project_store.session_exists("gonly")


def test_accumulate_prefers_store_holding_usage(temp_project_store, temp_store, reset_collector):
    """A globally-stored session keeps accumulating into the global store even
    when resume shadow-creates a project record without usage (Issue #2421)."""
    from praisonai.cli.state.project_sessions import (
        accumulate_session_usage,
        read_session_usage,
    )

    # Global store holds the real cumulative usage.
    temp_store.add_user_message("gboth", "hi")
    temp_store.update_session_metadata(
        "gboth", usage={"total_tokens": 300, "input_tokens": 100, "output_tokens": 200, "cost": 0.0},
        total_tokens=300,
    )
    # Resume shadow-creates a project record (no usage yet).
    temp_project_store.add_user_message("gboth", "hi")

    _track(50, 50)
    usage = accumulate_session_usage("gboth", model="gpt-4o-mini")

    # Merged into the global record, not restarted from zero in the project one.
    assert usage["total_tokens"] == 400
    assert read_session_usage("gboth")["total_tokens"] == 400
    assert temp_store.get_session("gboth").metadata["usage"]["total_tokens"] == 400


def test_rehydrate_prefers_store_holding_usage(temp_project_store, temp_store, reset_collector):
    """Resume restores the real cumulative usage from whichever store holds it,
    even when an empty project shadow record is found first (Issue #2421)."""
    from praisonai.cli.session.resume import rehydrate_session

    # Real cumulative usage lives in the global store.
    temp_store.add_user_message("rboth", "hi")
    temp_store.update_session_metadata(
        "rboth",
        usage={"total_tokens": 500, "input_tokens": 200, "output_tokens": 300, "cost": 0.01},
        total_tokens=500,
    )
    # A project shadow record exists first but carries no usage.
    temp_project_store.add_user_message("rboth", "hi")

    restored = rehydrate_session("rboth")
    assert restored.found is True
    assert restored.usage.get("total_tokens") == 500


def test_format_usage_footer():
    from praisonai.cli.state.project_sessions import format_usage_footer

    footer = format_usage_footer(
        {"input_tokens": 1240, "output_tokens": 3980, "cost": 0.014}
    )
    assert "1,240 in" in footer
    assert "3,980 out" in footer
    assert "$0.0140" in footer
