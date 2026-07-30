"""
Regression tests for the memory adapter (issue #3528, Defect C).

The old adapter called ``get_session``/``get_all``/``clear_session``/
``clear_all``/``list_sessions``/``add`` — none of which exist on core, so every
call fell into ``except`` and returned an ``"Error: …"`` string. These tests
bind against the real core API and assert no ``Error:`` fallback.
"""

import sys
import types

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
