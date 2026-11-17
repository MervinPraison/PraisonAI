"""tools_cache_key is computed every turn; plain functions must not be re-inspected (R-07)."""

import inspect

from praisonaiagents.tools import schema


def _make(n):
    tools = []
    for i in range(n):
        def tool(query: str, limit: int = 5) -> str:
            return query

        tool.__name__ = tool.__qualname__ = f"tool_{i}"
        tool.__doc__ = f"Tool {i}."
        tools.append(tool)
    return tools


def test_repeated_keys_do_not_reinspect_plain_functions(monkeypatch):
    tools = _make(20)
    first = schema.tools_cache_key(tools)
    calls = []
    real = inspect.signature
    monkeypatch.setattr(schema.inspect, "signature", lambda f, *a, **k: calls.append(f) or real(f, *a, **k))
    for _ in range(5):
        assert schema.tools_cache_key(tools) == first
    assert calls == []


def test_key_still_changes_when_a_function_is_edited_in_place():
    (tool,) = _make(1)
    before = schema.tools_cache_key([tool])
    tool.__doc__ = "A different description."
    after_doc = schema.tools_cache_key([tool])
    assert after_doc != before
    tool.__defaults__ = (9,)
    assert schema.tools_cache_key([tool]) != after_doc

    def other(query: str, extra: int) -> str:
        return query

    tool.__code__ = other.__code__
    assert schema.tools_cache_key([tool]) != before
