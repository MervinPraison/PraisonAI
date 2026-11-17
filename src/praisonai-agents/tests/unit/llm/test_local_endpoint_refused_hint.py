"""X-07: a local model with no server running fails fast and says what to do.

``Agent(model="ollama/llama3.2")`` with no Ollama server took about 19 s of
"overloaded error hit, waiting..." retries on the litellm route, then printed
a ``Connection refused`` panel with no hint and returned ``None``. A refused
connection is now not retried on this route either, and one warning names the
endpoint and how to start it.
"""

import asyncio
import logging
import socket

import pytest

from praisonaiagents import Agent


def _closed_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


@pytest.mark.parametrize("model,start", [("ollama/llama3.2", "ollama serve"),
                                         ("openai/local-model", "start the server")],
                         ids=["ollama", "openai_compatible"])
@pytest.mark.parametrize("mode", ["chat", "achat"])
def test_refused_local_endpoint_is_not_retried_and_hints(monkeypatch, tmp_path, caplog, mode, model, start):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    url = _closed_url()
    agent = Agent(name="local", instructions="hi", llm=model, base_url=url, output="silent")
    with caplog.at_level(logging.WARNING):
        result = agent.chat("hi") if mode == "chat" else asyncio.run(agent.achat("hi"))
    assert result is None
    messages = [r.getMessage() for r in caplog.records]
    assert not [m for m in messages if "error hit" in m], "a refused connection was retried"
    hints = [m for m in messages if "connection refused" in m and url in m]
    assert hints and start in hints[0]


def _refused():
    try:
        raise RuntimeError("APIConnectionError") from ConnectionRefusedError(111, "Connection refused")
    except RuntimeError as e:
        return e


def test_refused_with_auth_profiles_rotates_instead_of_surfacing():
    from praisonaiagents.llm.llm import LLM
    llm = LLM(model="ollama/llama3.2")
    llm._failover_manager = object()  # another profile may point at a live server
    decision = llm.resolve_failover_decision(_refused(), {"attempt": 1, "max_retries": 3})
    assert decision.action == "rotate_profile"
    llm._failover_manager = None
    assert llm.resolve_failover_decision(_refused(), {"attempt": 1, "max_retries": 3}).action == "surface_error"


def test_refused_hint_never_logs_url_credentials(caplog):
    from praisonaiagents.llm.llm import LLM
    llm = LLM(model="openai/local", base_url="http://user:s3cret@127.0.0.1:9/v1")
    with caplog.at_level(logging.WARNING):
        llm._warn_connection_refused()
    text = caplog.text
    assert "s3cret" not in text and "user:" not in text and "http://127.0.0.1:9/v1" in text
