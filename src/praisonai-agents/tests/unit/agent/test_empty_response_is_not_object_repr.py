"""A model response with no content must not become the SDK object's repr.

`_extract_llm_response_content` ended in `return str(response)`, reached whenever
`message.content` is falsy and there are no tool_calls -- a content filter, a
refusal, or `finish_reason="length"` with zero output tokens.  `achat()` uses it,
so the user's answer became several hundred characters of `ChatCompletion(...)`
repr, which was then written into chat_history and replayed to the model.

The sync path already does the right thing (`content.strip() if content else ""`).
"""
import asyncio
import types

from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from praisonaiagents import Agent
from praisonaiagents.llm.openai_client import OpenAIClient


def _filtered_response():
    """A real SDK object as returned when the content filter trips."""
    return ChatCompletion(
        id="chatcmpl-test", created=0, model="gpt-4o-mini", object="chat.completion",
        choices=[Choice(finish_reason="content_filter", index=0, logprobs=None,
                        message=ChatCompletionMessage(content=None, role="assistant"))],
    )


def test_extractor_returns_empty_not_repr():
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini")
    out = agent._extract_llm_response_content(_filtered_response())
    assert not out.startswith("ChatCompletion("), (
        f"got {len(out)} chars of object repr as the assistant's answer: {out[:80]!r}")
    assert out == ""


def test_extractor_matches_the_sync_path():
    """Sync uses `content.strip() if content else ''`; async must agree."""
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini")
    resp = _filtered_response()
    content = resp.choices[0].message.content
    sync_style = content.strip() if content else ""
    assert agent._extract_llm_response_content(resp) == sync_style


def test_achat_does_not_write_object_repr_into_chat_history():
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini")

    async def _create(**kwargs):
        return _filtered_response()

    def _create_sync(**kwargs):
        return _filtered_response()

    client = OpenAIClient(api_key="sk-not-a-real-key")
    client._sync_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create_sync)),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(parse=_create_sync))),
        responses=None)
    client._async_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create)),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(parse=_create))),
        responses=None)
    agent._Agent__openai_client = client
    agent._unified_dispatcher = None

    result = asyncio.run(agent.achat("say something blocked"))

    assert result == "", f"expected empty async result, got {result!r}"
    for m in agent.chat_history:
        assert not str(m.get("content", "")).startswith("ChatCompletion("), (
            f"object repr persisted into chat_history: {str(m['content'])[:80]!r}")
    assistant_msgs = [m for m in agent.chat_history if m.get("role") == "assistant"]
    assert assistant_msgs, "no assistant message written to chat_history"
    assert assistant_msgs[-1].get("content", None) == "", (
        f"assistant chat_history entry must be empty, got "
        f"{assistant_msgs[-1].get('content')!r}")


def test_extractor_warns_on_refusal_even_when_finish_reason_stop(caplog):
    """A refusal with finish_reason='stop' must still surface a warning."""
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini")
    resp = ChatCompletion(
        id="chatcmpl-test", created=0, model="gpt-4o-mini", object="chat.completion",
        choices=[Choice(finish_reason="stop", index=0, logprobs=None,
                        message=ChatCompletionMessage(
                            content=None, role="assistant",
                            refusal="I can't help with that."))],
    )
    with caplog.at_level("WARNING"):
        out = agent._extract_llm_response_content(resp)
    assert out == ""
    assert any("refused=True" in r.getMessage() for r in caplog.records), (
        "expected a warning when the model refused")
    assert not any("I can't help with that." in r.getMessage() for r in caplog.records), (
        "refusal text must not be logged")
