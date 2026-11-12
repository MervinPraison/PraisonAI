"""Regression tests for issue #6334.

1. Tool gates run on the canonical tool name and honour per-turn ``tools=``.
2. ``Injected[...]`` params are hidden from the LLM schema and cannot be
   overridden by a model-supplied value.
3. A guardrail-rejected reply never reaches chat history / the DB, and the
   retry keeps ``response_format``.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from praisonaiagents import Agent
from praisonaiagents.tools import Injected, tool


def _make_delete_tool(calls):
    def delete_file(path: str) -> str:
        """Delete a file."""
        calls.append(path)
        return f"deleted {path}"

    return delete_file


def _response(text):
    message = SimpleNamespace(content=text, tool_calls=None, reasoning_content=None, parsed=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None)


# --- Gap 1a: name variants cannot bypass deny rules -------------------------

@pytest.mark.parametrize("alias", ["DeleteFile", "Delete_File", "delete-file", "DELETE_FILE"])
def test_name_variant_blocked_by_default_deny(alias):
    calls = []
    agent = Agent(name="a", instructions="x", tools=[_make_delete_tool(calls)],
                  model="gpt-4o-mini", approval=False)
    result = agent.execute_tool(alias, {"path": "/tmp/x"})
    assert isinstance(result, dict) and result.get("permission_denied")
    assert calls == []


def test_name_variant_blocked_by_permission_pattern_sync_and_async():
    calls = []
    agent = Agent(name="b", instructions="x", tools=[_make_delete_tool(calls)],
                  model="gpt-4o-mini", approval={"permissions": {"delete_*": "deny"}})
    assert agent.execute_tool("deleteFile", {"path": "/tmp/y"}).get("permission_denied")
    result = asyncio.run(agent.execute_tool_async("DeleteFile", {"path": "/tmp/y"}))
    assert result.get("permission_denied")
    assert calls == []


def test_name_variant_still_self_repairs_for_allowed_tool():
    def web_search(query: str) -> str:
        """Search."""
        return f"results for {query}"

    agent = Agent(name="c", instructions="x", tools=[web_search], model="gpt-4o-mini")
    assert agent.execute_tool("WebSearch", {"query": "q"}) == "results for q"


# --- Gap 1b: per-turn tools= is enforced at dispatch -------------------------

def test_per_turn_tool_subset_enforced_at_dispatch():
    calls = []

    def secret_tool(x: str) -> str:
        """Secret."""
        calls.append(x)
        return "ran"

    agent = Agent(name="d", instructions="x", tools=[secret_tool], model="gpt-4o-mini")
    seen = {}

    def fake_completion(self, messages, *args, **kwargs):
        # Simulates the model calling a tool it was not offered this turn.
        seen["sync"] = self.execute_tool("secret_tool", {"x": "prod"})
        seen["async"] = asyncio.run(self.execute_tool_async("secret_tool", {"x": "prod"}))
        return _response("done")

    with patch.object(Agent, "_chat_completion", fake_completion):
        assert agent.chat("hi", tools=[]) == "done"

    assert seen["sync"].get("permission_denied")
    assert seen["async"].get("permission_denied")
    assert calls == []
    # Outside the restricted turn the agent's own tool still runs.
    assert agent.execute_tool("secret_tool", {"x": "ok"}) == "ran"


# --- Gap 2: Injected[...] state ----------------------------------------------

def test_injected_params_hidden_and_not_spoofable():
    def plain(query: str, state: Injected[dict]) -> str:
        """Plain fn."""
        return f"plain:{state.get('session_id')}"

    @tool
    def deco(query: str, state: Injected[dict]) -> str:
        """Decorated."""
        return f"deco:{state.get('session_id')}"

    agent = Agent(name="e", instructions="x", tools=[plain, deco], model="gpt-4o-mini")
    for schema in agent._format_tools_for_completion():
        params = schema["function"]["parameters"]
        assert "state" not in params["properties"]
        assert "state" not in params["required"]

    spoof = {"query": "q", "state": {"session_id": "victim-session"}}
    assert "victim-session" not in agent.execute_tool("plain", dict(spoof))
    assert "victim-session" not in agent.execute_tool("deco", dict(spoof))
    # Plain functions get state injected when the model omits it.
    assert agent.execute_tool("plain", {"query": "q"}).startswith("plain:")
    assert "victim-session" not in asyncio.run(agent.execute_tool_async("plain", dict(spoof)))


# --- Gap 3: guardrail-rejected replies never persist -------------------------

def _good_only(output):
    text = getattr(output, "raw", output)
    ok = "GOOD" in str(text)
    return (ok, str(text) if ok else "must say GOOD")


def test_rejected_reply_not_in_history():
    agent = Agent(name="f", instructions="x", model="gpt-4o-mini", guardrails=_good_only)
    replies = iter([_response("BAD answer"), _response("GOOD answer")])
    with patch.object(Agent, "_chat_completion", lambda self, *a, **k: next(replies)), \
            patch.object(Agent, "_guardrail_retry_delay", lambda self, n: 0):
        assert agent.chat("hi") == "GOOD answer"
    contents = [m["content"] for m in agent.chat_history if m["role"] == "assistant"]
    assert contents == ["GOOD answer"]


def test_guardrail_retry_keeps_response_format():
    from pydantic import BaseModel

    class City(BaseModel):
        name: str
        population: int

    formats = []

    def fake_completion(self, messages, *args, **kwargs):
        formats.append(kwargs.get("response_format"))
        if len(formats) == 1:
            return _response('{"name": "BAD", "population": 1}')
        return _response('{"name": "Paris", "population": 2100000}')

    def guard(output):
        text = getattr(output, "raw", output)
        ok = "Paris" in str(text)
        return (ok, str(text) if ok else "must be Paris")

    agent = Agent(name="g", instructions="x", model="gpt-4o-mini", guardrails=guard)
    with patch.object(Agent, "_chat_completion", fake_completion), \
            patch.object(Agent, "_guardrail_retry_delay", lambda self, n: 0):
        result = agent.chat("capital of France?", output_pydantic=City)

    assert len(formats) == 2 and formats[1] is not None and formats[1] == formats[0]
    assert isinstance(result, City) and result.name == "Paris"
    contents = [m["content"] for m in agent.chat_history if m["role"] == "assistant"]
    assert len(contents) == 1 and "BAD" not in contents[0]
