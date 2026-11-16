"""A supplied memory adapter must not require the default implementation."""
import copy
import sys
import types

import pytest

pytest.importorskip("litellm", reason="optional LLM provider dependency")

from praisonaiagents.llm import LLM


class ProvidedMemory:
    """Side-effect-free implementation of the supplied memory adapter surface."""

    def get_tool_definition(self):
        """Return the request tool definition without constructing a backend."""
        return {"type": "memory_20250818", "name": "memory"}

    def get_beta_header(self):
        """Return a synthetic beta marker for local parameter checks."""
        return "synthetic-memory-fixture-beta"

    def execute(self, **kwargs):
        """Provide the adapter execution surface without I/O."""
        return "fixture memory result"


def make_llm(memory, **kwargs):
    """Construct the real params producer with an explicit synthetic key."""
    return LLM(
        model="anthropic/claude-sonnet-4-20250514",
        api_key="synthetic-offline-fixture",
        base_url="http://127.0.0.1:1",
        claude_memory=memory,
        **kwargs,
    )


def test_supplied_memory_is_used_without_default_module(monkeypatch):
    """A supplied instance is reused even if the default cannot be imported."""
    monkeypatch.setitem(sys.modules, "praisonaiagents.tools.claude_memory_tool", None)
    supplied = ProvidedMemory()
    llm = make_llm(supplied)
    assert llm._get_claude_memory_tool() is supplied
    assert llm._get_claude_memory_tool() is supplied


@pytest.mark.parametrize("tools, headers", [
    (None, None),
    ([], {}),
    ([{"type": "function", "function": {"name": "fixture", "parameters": {"type": "object", "properties": {}}}}], {"x-fixture": "retained"}),
])
def test_real_params_builder_accepts_supplied_memory_without_default_module(monkeypatch, tools, headers):
    """Supplied memory is included without ordering assumptions or input mutation."""
    monkeypatch.setitem(sys.modules, "praisonaiagents.tools.claude_memory_tool", None)
    supplied = ProvidedMemory()
    llm = make_llm(supplied, web_fetch=True)
    original_tools, original_headers = copy.deepcopy(tools), copy.deepcopy(headers)
    first = llm._build_completion_params(tools=tools, extra_headers=headers)
    second = llm._build_completion_params(tools=tools, extra_headers=headers)
    assert supplied.get_tool_definition() in first["tools"]
    assert first["tools"] == second["tools"]
    assert supplied.get_beta_header() in first["extra_headers"]["anthropic-beta"]
    assert tools == original_tools
    assert headers == original_headers


@pytest.mark.parametrize("memory", [None, False])
def test_disabled_memory_still_needs_no_implementation(monkeypatch, memory):
    """Disabled memory never imports an implementation."""
    monkeypatch.setitem(sys.modules, "praisonaiagents.tools.claude_memory_tool", None)
    assert make_llm(memory)._get_claude_memory_tool() is None


def test_boolean_opt_in_still_constructs_and_caches_default(monkeypatch):
    """Boolean opt-in retains default factory construction and caching."""
    calls = []

    class DefaultMemory(ProvidedMemory):
        """Optional implementation stand-in that records construction."""

        def __init__(self):
            """Record one default factory invocation."""
            calls.append(self)

    module = types.ModuleType("praisonaiagents.tools.claude_memory_tool")
    module.ClaudeMemoryTool = DefaultMemory
    monkeypatch.setitem(sys.modules, module.__name__, module)
    llm = make_llm(True)
    tool = llm._get_claude_memory_tool()
    assert isinstance(tool, DefaultMemory)
    assert llm._get_claude_memory_tool() is tool
    assert calls == [tool]
