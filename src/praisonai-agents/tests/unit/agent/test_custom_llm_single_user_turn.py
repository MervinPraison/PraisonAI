"""The custom-LLM (``provider/model``) path sends each user turn once.

``chat()`` stores the user turn in ``chat_history`` before the model call, and
``LLM._build_messages`` appends ``prompt`` after ``chat_history`` itself, so
the stored copy must not be forwarded as history too. It was, on every
litellm route (``ollama/``, ``anthropic/``, ``openai/``, ``base_url=``), which
billed the prompt twice. ``litellm.completion`` is stubbed; nothing leaves the
machine.
"""
import asyncio

import pytest

pytest.importorskip("litellm")

from praisonaiagents import Agent  # noqa: E402

MODEL = "anthropic/claude-3-5-sonnet-20240620"


def _litellm():
    import litellm
    return litellm


def _reply(model, text):
    return _litellm().ModelResponse(model=model, usage={
        "prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        choices=[{"index": 0, "finish_reason": "stop",
                  "message": {"role": "assistant", "content": text}}])


def _chunks(model, text):
    litellm = _litellm()
    yield litellm.ModelResponseStream(model=model, choices=[{
        "index": 0, "delta": {"role": "assistant", "content": text}}])
    yield litellm.ModelResponseStream(model=model, choices=[{
        "index": 0, "delta": {}, "finish_reason": "stop"}])


@pytest.fixture
def sent(monkeypatch):
    """Record the ``messages`` of every model call; answer "A1", "A2", ..."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(Agent, "_default_model", None)
    monkeypatch.setattr(Agent, "_default_model_checked", False)
    requests = []

    def fake(*a, **k):
        requests.append(k.get("messages"))
        text = f"A{len(requests)}"
        if k.get("stream"):
            return _chunks(k.get("model"), text)
        return _reply(k.get("model"), text)

    async def afake(*a, **k):
        return fake(*a, **k)

    litellm = _litellm()
    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(litellm, "acompletion", afake)
    return requests


def _turns(messages):
    return [(m["role"], m["content"]) for m in messages if m["role"] != "system"]


def _agent():
    return Agent(name="p", instructions="Be brief.", llm=MODEL, output="silent")


def test_chat_sends_the_prompt_once(sent):
    agent = _agent()
    agent.chat("Q1")
    agent.chat("Q2")
    assert _turns(sent[0]) == [("user", "Q1")]
    assert _turns(sent[1]) == [("user", "Q1"), ("assistant", "A1"), ("user", "Q2")]


def test_achat_sends_the_prompt_once(sent):
    agent = _agent()

    async def run():
        await agent.achat("Q1")
        await agent.achat("Q2")

    asyncio.run(run())
    assert _turns(sent[0]) == [("user", "Q1")]
    assert _turns(sent[1]) == [("user", "Q1"), ("assistant", "A1"), ("user", "Q2")]


def test_streamed_turn_sends_the_prompt_once(sent):
    agent = _agent()
    assert "".join(agent.start("Q1", stream=True)) == "A1"
    assert _turns(sent[0]) == [("user", "Q1")]


def test_history_still_records_each_turn_once(sent):
    agent = _agent()
    agent.chat("Q1")
    agent.chat("Q2")
    assert [(m["role"], m["content"]) for m in agent.chat_history] == [
        ("user", "Q1"), ("assistant", "A1"), ("user", "Q2"), ("assistant", "A2")]


def test_repeating_the_last_question_is_still_one_turn(sent):
    # A user who asks the same thing twice in a row sends it once per request,
    # with the earlier exchange kept as history.
    agent = _agent()
    agent.chat("Q1")
    agent.chat("Q1")
    assert _turns(sent[1]) == [("user", "Q1"), ("assistant", "A1"), ("user", "Q1")]
