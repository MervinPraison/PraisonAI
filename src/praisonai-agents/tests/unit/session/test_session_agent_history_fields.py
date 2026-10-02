"""Closing and reopening a Session must preserve complete agent messages."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from praisonaiagents.session.api import AGENT_HISTORY_KEY, Session
from praisonaiagents.session.store import DefaultSessionStore


@pytest.mark.parametrize("history", [
    [{"role": "user", "content": "hello"}],
    [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {
                "name": "lookup", "arguments": '{"query":"hello"}'}}
        ]},
        {"role": "tool", "content": "found", "tool_call_id": "call_1",
         "name": "lookup"},
        {"role": "assistant", "content": "answer"},
    ],
    [{"role": "assistant", "content": "answer", "reasoning_content": "why",
      "metadata": {"citations": [{"source": "local"}]}, "custom": False}],
    [{"role": "user", "content": [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
    ], "name": "reader"}],
], ids=["plain-control", "tool-turn", "reasoning-and-metadata", "multimodal"])
def test_close_reopen_preserves_message_fields(tmp_path, monkeypatch, history):
    import praisonaiagents.agent as agent_module
    import praisonaiagents.session.store as store_module

    class LocalAgent:
        def __init__(self, **kwargs):
            self.chat_history = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agent_module, "Agent", LocalAgent)
    session_dir = str(tmp_path / "sessions")
    store = DefaultSessionStore(session_dir=session_dir)
    monkeypatch.setattr(store_module, "_default_store", store)
    session = Session(session_id="parent")
    session._memory = SimpleNamespace(search_short_term=lambda **kwargs: [])
    agent = session.Agent(name="helper", memory=False)
    agent.chat_history = deepcopy(history)
    session.close()

    fresh = DefaultSessionStore(session_dir=session_dir)
    monkeypatch.setattr(store_module, "_default_store", fresh)
    assert fresh.get_session("parent").metadata[AGENT_HISTORY_KEY][
        "helper:Assistant"
    ] == history
    resumed = Session(session_id="parent").Agent(name="helper", memory=False)
    assert resumed.chat_history == history


@pytest.mark.parametrize("builder", ["openai", "litellm"])
def test_restored_extensions_do_not_reach_responses_input(tmp_path, monkeypatch, builder):
    import praisonaiagents.session.store as store_module
    from praisonaiagents.llm.openai_client import OpenAIClient
    from praisonaiagents.llm.llm import LLM

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    monkeypatch.setattr(store_module, "_default_store", store)
    history = [
        {"role": "user", "content": "question", "name": "reader",
         "metadata": {"origin": "disk"}},
        {"role": "assistant", "content": "answer", "reasoning_content": "why",
         "metadata": {"citation": "local"}, "extension": False},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "lookup", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "call_1", "content": "found"},
    ]
    session = Session(session_id="parent")
    session._agents["helper:Assistant"] = {"agent": None, "chat_history": history}
    session.close()
    resumed = Session(session_id="parent")._restore_agent_chat_history("helper:Assistant")
    if builder == "openai":
        client = object.__new__(OpenAIClient)
        params = client._build_responses_input(resumed, model="gpt-4o")
    else:
        llm = object.__new__(LLM)
        llm.max_tokens = None
        llm.top_p = None
        llm.base_url = None
        llm.api_key = None
        llm.timeout = None
        llm._resolve_subscription_creds = lambda: None
        llm._resolve_openai_compatible_model = lambda: "gpt-4o"
        params = llm._build_responses_params(resumed)
    assert params["input"] == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
        {"type": "function_call", "call_id": "call_1", "name": "lookup",
         "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "found"},
    ]
    assert store.get_session("parent").metadata[AGENT_HISTORY_KEY][
        "helper:Assistant"
    ] == history


def test_legacy_defaults_and_non_message_filter(tmp_path, monkeypatch):
    import praisonaiagents.session.store as store_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    monkeypatch.setattr(store_module, "_default_store", store)
    session = Session(session_id="parent")
    session._agents["helper:Assistant"] = {
        "agent": None, "chat_history": [None, {"name": "helper"}],
    }
    session.close()
    assert store.get_session("parent").metadata[AGENT_HISTORY_KEY][
        "helper:Assistant"
    ] == [{"role": "user", "content": "", "name": "helper"}]
