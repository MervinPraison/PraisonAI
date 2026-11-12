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


# --- Review follow-ups ---------------------------------------------------------

def test_function_name_alias_resolves_to_declared_name_for_gates():
    calls = []

    @tool(name="delete_file")
    def remove_file(path: str) -> str:
        """Delete a file."""
        calls.append(path)
        return "deleted"

    agent = Agent(name="h", instructions="x", tools=[remove_file], model="gpt-4o-mini",
                  approval={"permissions": {"delete_*": "deny"}})
    assert agent._canonical_tool_name("remove_file") == "delete_file"
    assert agent.execute_tool("remove_file", {"path": "/tmp/z"}).get("permission_denied")
    assert asyncio.run(agent.execute_tool_async("remove_file", {"path": "/tmp/z"})).get("permission_denied")
    assert calls == []


def test_reasoning_branch_commits_approved_text_only():
    def reasoning_response(content, reasoning):
        resp = _response(content)
        resp.choices[0].message.reasoning_content = reasoning
        return resp

    replies = iter([reasoning_response("unchecked answer", "BAD thinking"), _response("GOOD retry")])
    agent = Agent(name="i", instructions="x", model="gpt-4o-mini", guardrails=_good_only)
    with patch.object(Agent, "_chat_completion", lambda self, *a, **k: next(replies)), \
            patch.object(Agent, "_guardrail_retry_delay", lambda self, n: 0):
        result = agent.chat("hi", reasoning_steps=True)
    contents = [m["content"] for m in agent.chat_history if m["role"] == "assistant"]
    assert contents == [str(result)] and "unchecked" not in contents[0]


def test_injected_filled_when_type_hints_unresolvable():
    def lookup(query: str, state: Injected[dict]) -> "UndefinedReturnType":  # noqa: F821
        """Lookup."""
        return f"ok:{isinstance(state, dict)}"

    agent = Agent(name="j", instructions="x", tools=[lookup], model="gpt-4o-mini")
    params = agent._format_tools_for_completion()[0]["function"]["parameters"]
    assert "state" not in params["properties"]
    assert agent.execute_tool("lookup", {"query": "q"}) == "ok:True"


def test_class_tool_run_method_gets_injected_state():
    class LookupTool:
        def _run(self, query: str, state: Injected[dict]) -> str:
            """Lookup."""
            return f"cls:{isinstance(state, dict)}"

    agent = Agent(name="k", instructions="x", tools=[LookupTool], model="gpt-4o-mini")
    assert agent.execute_tool("LookupTool", {"query": "q"}) == "cls:True"


def test_function_name_alias_gated_with_tools_override():
    calls = []

    @tool(name="delete_file")
    def remove_file(path: str) -> str:
        """Delete a file."""
        calls.append(path)
        return "deleted"

    agent = Agent(name="l", instructions="x", tools=[], model="gpt-4o-mini",
                  approval={"permissions": {"delete_*": "deny"}})
    result = asyncio.run(agent.execute_tool_async("remove_file", {"path": "/tmp/o"},
                                                  tools_override=[remove_file]))
    assert result.get("permission_denied")
    assert calls == []


def test_framework_tools_registered_mid_turn_not_denied_by_turn_scope():
    def user_tool(x: str) -> str:
        """User."""
        return "u"

    import sys
    import types

    # Stub module: registration only needs ``set_artifact_store`` and the callables.
    stub = types.ModuleType("praisonaiagents.tools.artifact_tools")
    stub.set_artifact_store = lambda store: None
    for fn_name in ("artifact_head", "artifact_tail", "artifact_grep",
                    "artifact_chunk", "artifact_load", "artifact_list"):
        def _fn(artifact_id: str = "") -> str:
            return "a"
        _fn.__name__ = fn_name
        setattr(stub, fn_name, _fn)

    agent = Agent(name="m", instructions="x", tools=[user_tool], model="gpt-4o-mini")
    agent._artifact_store = object()
    import praisonaiagents.tools as tools_pkg
    with patch.dict(sys.modules, {"praisonaiagents.tools.artifact_tools": stub}), \
            patch.object(tools_pkg, "artifact_tools", stub, create=True):
        agent._register_artifact_tools()
    assert "artifact_list" in agent._available_active_tool_names()
    token = agent._enter_turn_tool_scope([user_tool])
    try:
        assert agent._turn_tool_denial("artifact_list") is None
    finally:
        agent._exit_turn_tool_scope(token)


def test_plain_injected_cache_keys_on_function_not_bound_method():
    from praisonaiagents.tools import injected as inj

    class LookupTool:
        def _run(self, query: str, state: Injected[dict]) -> str:
            return "x"

    before = len(inj._plain_injected_cache)
    for _ in range(5):
        inj.inject_into_plain_callable(LookupTool()._run, {"query": "q"})
    assert len(inj._plain_injected_cache) == before + 1
    assert LookupTool.__dict__["_run"] in inj._plain_injected_cache
