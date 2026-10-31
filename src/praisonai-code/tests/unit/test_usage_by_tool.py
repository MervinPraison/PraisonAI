"""Tests for per-tool usage reporting: ``praisonai usage --by tool`` (Issue #6158)."""

import json
import os
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

import praisonai_code.cli.state.project_sessions as ps
from praisonaiagents.hooks import HookRegistry
from praisonaiagents.session.store import DefaultSessionStore


@pytest.fixture
def store(monkeypatch, tmp_path):
    project = DefaultSessionStore(session_dir=str(tmp_path / "project"))
    empty_global = DefaultSessionStore(session_dir=str(tmp_path / "global"))
    monkeypatch.setattr(ps, "get_project_session_store", lambda *a, **k: project)
    monkeypatch.setattr(ps, "_get_default_store", lambda: empty_global)
    monkeypatch.setattr(ps, "_resolve_usage_store", lambda *a, **k: project)
    ps.reset_tool_stats()
    yield project
    ps.reset_tool_stats()


class _Evt:
    def __init__(self, name, ms, error=None):
        self.tool_name, self.execution_time_ms, self.tool_error = name, ms, error


def _usage_json(by="tool"):
    from praisonai_code.cli.commands.usage import app

    result = CliRunner().invoke(app, ["--by", by, "--json", "--days", "0"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output[result.output.index("{"):])


def test_tally_persists_and_merges_across_runs(store):
    store.add_message("s1", "user", "hi")
    ps._on_after_tool(_Evt("read_file", 10))
    ps._on_after_tool(_Evt("read_file", 30, error="boom"))
    ps._flush_tool_stats("s1")
    # Tally is drained after a flush, so a second flush does not double count.
    ps._flush_tool_stats("s1")
    ps._on_after_tool(_Evt("read_file", 20))
    ps._flush_tool_stats("s1")

    stats = store.get_session("s1").metadata["tool_stats"]["read_file"]
    assert stats["calls"] == 3
    assert stats["errors"] == 1
    assert stats["total_ms"] == 60
    assert stats["last_ms"] == 20
    assert stats["last_error"] == "boom"



def test_failed_save_keeps_tally_for_retry(store, monkeypatch):
    store.add_message("s1", "user", "hi")
    ps._on_after_tool(_Evt("read_file", 10))
    monkeypatch.setattr(store, "_modify_session_locked", lambda *a, **k: False)
    ps._flush_tool_stats("s1")
    assert "tool_stats" not in store.get_session("s1").metadata
    monkeypatch.undo()
    monkeypatch.setattr(ps, "_resolve_usage_store", lambda *a, **k: store)
    ps._on_after_tool(_Evt("read_file", 20))
    ps._flush_tool_stats("s1")
    stats = store.get_session("s1").metadata["tool_stats"]["read_file"]
    assert stats["calls"] == 2 and stats["total_ms"] == 30


def test_latest_values_follow_tool_time_not_session_time(store):
    store.add_message("a", "user", "hi")
    store.add_message("b", "user", "hi")
    store.update_session_metadata("a", tool_stats={"search": {
        "calls": 1, "errors": 1, "total_ms": 5, "last_ms": 5,
        "last_error": "old", "last_at": 100.0, "last_error_at": 100.0}})
    store.update_session_metadata("b", tool_stats={"search": {
        "calls": 1, "errors": 1, "total_ms": 9, "last_ms": 9,
        "last_error": "new", "last_at": 200.0, "last_error_at": 200.0}})
    store.add_message("a", "user", "text-only turn")  # bumps a's updated_at
    row = _usage_json()["rows"][0]
    assert row["last_ms"] == 9.0 and row["last_error"] == "new"

def test_usage_by_tool_json_shape(store):
    store.add_message("s1", "user", "hi")
    store.add_message("s2", "user", "hi")
    ps._on_after_tool(_Evt("search", 100))
    ps._on_after_tool(_Evt("search", 300, error="timeout"))
    ps._flush_tool_stats("s1")
    ps._on_after_tool(_Evt("search", 200))
    ps._on_after_tool(_Evt("write_file", 5))
    ps._flush_tool_stats("s2")

    data = _usage_json()
    assert data["by"] == "tool"
    rows = {r["tool"]: r for r in data["rows"]}
    assert rows["search"]["calls"] == 3
    assert rows["search"]["successes"] == 2
    assert rows["search"]["errors"] == 1
    assert rows["search"]["success_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert rows["search"]["avg_ms"] == 200.0
    assert rows["search"]["last_error"] == "timeout"
    assert rows["write_file"]["calls"] == 1
    assert data["rows"][0]["tool"] == "search"  # most-called first


def test_usage_by_tool_empty(store):
    assert _usage_json()["rows"] == []


def test_existing_groupings_unaffected(store):
    store.add_message("s1", "user", "hi")
    store.update_session_metadata("s1", total_tokens=10, cost=0.5)
    data = _usage_json(by="model")
    assert data["total_tokens"] == 10


def test_real_agent_tool_call_is_reported(store):
    """A real Agent tool execution flows through AFTER_TOOL into the report."""
    from praisonaiagents import Agent

    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    registry = HookRegistry()
    ps.install_tool_stats_hook(registry)
    agent = Agent(name="calc", tools=[add], hooks=registry)
    assert agent.execute_tool("add", {"a": 2, "b": 3}) == 5

    store.add_message("s1", "user", "hi")
    ps._flush_tool_stats("s1")
    rows = {r["tool"]: r for r in _usage_json()["rows"]}
    assert rows["add"]["calls"] == 1
    assert rows["add"]["errors"] == 0


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY")
def test_real_agentic_llm_tool_run_is_reported(store):
    from praisonaiagents import Agent

    def get_weather(city: str) -> str:
        """Get the weather for a city."""
        return f"Sunny in {city}"

    ps.install_tool_stats_hook()
    agent = Agent(name="weather", tools=[get_weather], llm="gpt-4o-mini")
    print(agent.start("Use the get_weather tool for Paris and report it."))

    store.add_message("s1", "user", "hi")
    ps._flush_tool_stats("s1")
    rows = {r["tool"]: r for r in _usage_json()["rows"]}
    assert rows["get_weather"]["calls"] >= 1
