"""
Regression tests for the memory adapter (issue #3528, Defect C).

The old adapter called ``get_session``/``get_all``/``clear_session``/
``clear_all``/``list_sessions``/``add`` — none of which exist on core, so every
call fell into ``except`` and returned an ``"Error: …"`` string. These tests
bind against the real core API and assert no ``Error:`` fallback.
"""

import sys
import types
import ast

import pytest


@pytest.fixture
def fake_memory(monkeypatch):
    """Install a fake ``praisonaiagents.memory`` exposing the real core API."""
    calls = {"stored": [], "searched": [], "reset": 0}

    class Memory:
        def __init__(self, *a, **k):
            pass

        def get_all_memories(self):
            return [{"id": "1", "text": "hello", "metadata": {"user_id": "u1"}}]

        def store_short_term(self, text, metadata=None, **k):
            calls["stored"].append((text, metadata))

        def search(self, query, user_id=None, limit=10, **k):
            calls["searched"].append((query, user_id, limit))
            return [{"text": "hit"}]

        def reset_all(self):
            calls["reset"] += 1

    pkg = types.ModuleType("praisonaiagents")
    mem_mod = types.ModuleType("praisonaiagents.memory")
    mem_mod.Memory = Memory
    pkg.memory = mem_mod
    monkeypatch.setitem(sys.modules, "praisonaiagents", pkg)
    monkeypatch.setitem(sys.modules, "praisonaiagents.memory", mem_mod)
    return calls


@pytest.fixture
def memory_tools():
    from praisonai_mcp.mcp_server.registry import MCPToolRegistry
    import praisonai_mcp.mcp_server.registry as reg

    registry = MCPToolRegistry()
    saved = reg._tool_registry
    reg._tool_registry = registry
    try:
        from praisonai_mcp.mcp_server.adapters.memory import register_memory_tools
        register_memory_tools()
        yield registry
    finally:
        reg._tool_registry = saved


def _call(registry, name, **kwargs):
    tool = registry.get(name)
    assert tool is not None
    return tool.handler(**kwargs)


def test_memory_show_calls_real_api(fake_memory, memory_tools):
    out = _call(memory_tools, "praisonai.memory.show")
    assert not out.startswith("Error:")
    assert "hello" in out


@pytest.mark.parametrize("user_id,expected", [
    ("", ["empty"]),
    ("None", ["literal-none"]),
    ("u1", ["named"]),
    (None, ["missing", "null", "empty", "literal-none", "named"]),
])
def test_memory_show_distinguishes_missing_and_explicit_user_ids(fake_memory, memory_tools, monkeypatch, user_id, expected):
    import praisonaiagents.memory as module

    records = [
        {"id": "missing", "metadata": {}},
        {"id": "null", "metadata": {"user_id": None}},
        {"id": "empty", "metadata": {"user_id": ""}},
        {"id": "literal-none", "metadata": {"user_id": "None"}},
        {"id": "named", "metadata": {"user_id": "u1"}},
    ]
    monkeypatch.setattr(module.Memory, "get_all_memories", lambda self: records)
    actual = ast.literal_eval(_call(memory_tools, "praisonai.memory.show", user_id=user_id))
    assert [record["id"] for record in actual] == expected


def test_memory_add_calls_store_short_term(fake_memory, memory_tools):
    out = _call(memory_tools, "praisonai.memory.add", content="note")
    assert not out.startswith("Error:")
    assert fake_memory["stored"] == [("note", {})]


def test_memory_search_calls_real_api(fake_memory, memory_tools):
    out = _call(memory_tools, "praisonai.memory.search", query="q")
    assert not out.startswith("Error:")
    assert fake_memory["searched"][0][0] == "q"


def test_memory_clear_calls_reset_all(fake_memory, memory_tools):
    out = _call(memory_tools, "praisonai.memory.clear")
    assert not out.startswith("Error:")
    assert fake_memory["reset"] == 1


@pytest.mark.parametrize("user_id,expected", [(None, 2000), ("even", 1000), ("old-user", 2), ("absent", 0)])
def test_sqlite_show_bounds_fetches_without_capping_full_enumeration(tmp_path, monkeypatch, memory_tools, user_id, expected):
    import praisonaiagents.memory as module

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    memory = module.Memory(config={"provider": "sqlite"})
    adapter = memory.memory_adapter
    queries = []
    try:
        for tier in ("short", "long"):
            for index in range(1001):
                getattr(memory, f"store_{tier}_term")(
                    f"{tier} entry {index}", metadata={"user_id": "old-user" if index == 0 else "even" if index % 2 == 0 else "odd"},
                )
        # Distinct valid timestamps make the displayed latest-1000 window
        # deterministic; SQLite's second-resolution default can tie here.
        for tier, conn in (("short", adapter._get_stm_conn()), ("long", adapter._get_ltm_conn())):
            conn.execute(f"UPDATE {tier}_term_memory SET timestamp = datetime(1700000000 + id, 'unixepoch')")
            conn.commit()
        adapter._get_stm_conn().set_trace_callback(queries.append)
        adapter._get_ltm_conn().set_trace_callback(queries.append)
        monkeypatch.setattr(module, "Memory", lambda: memory)
        records = ast.literal_eval(_call(memory_tools, "praisonai.memory.show", user_id=user_id))
        assert len(records) == expected
        selects = [query for query in queries if query.startswith("SELECT id, content")]
        assert len(selects) == 2
        assert all("LIMIT 1000" in query for query in selects)
        if user_id:
            assert all(record["metadata"]["user_id"] == user_id for record in records)
        assert {record["type"] for record in records} == ({"short_term", "long_term"} if expected else set())
        assert len(memory.get_all_memories()) == 2002
    finally:
        adapter.close_connections()
        memory.close_connections()
