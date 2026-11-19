"""A tool failure must reach the model as a tool failure (D-03), never as an LLM error.

`_chat_completion` wraps its body in a blanket `except Exception`, which also
catches the `ToolExecutionError` raised by the sync tool executor and re-raises
it as `LLMError`.  Three consequences, all covered here:

  * `chat()` swallows the error and returns None instead of raising.
  * The tool's message is fed to the *LLM* error classifier, so a tool whose
    text resembles a rate limit makes the framework sleep and re-drive the model.
  * On that re-drive the model is called again with no tool result at all, and
    its answer is returned to the user as a success.
"""
import json
import types

import pytest

from praisonaiagents import Agent
from praisonaiagents.llm.openai_client import OpenAIClient


class _Fn:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args)


class _ToolCall:
    def __init__(self, id, name, args):
        self.id = id
        self.type = "function"
        self.function = _Fn(name, args)

    def model_dump(self):
        return {"id": self.id, "type": "function",
                "function": {"name": self.function.name,
                             "arguments": self.function.arguments}}


class _Msg:
    role = "assistant"
    refusal = None
    parsed = None

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [t.model_dump() for t in self.tool_calls]
        return d


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15
    completion_tokens_details = None
    prompt_tokens_details = None

    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class _Resp:
    id = "chatcmpl-test"
    created = 0
    object = "chat.completion"
    model = "gpt-4o-mini"

    def __init__(self, msg, finish_reason="stop"):
        self.choices = [types.SimpleNamespace(message=msg, finish_reason=finish_reason,
                                              index=0, delta=None)]
        self.usage = _Usage()


class _Recorder:
    """Scripted transport. The sync agent path dispatches through
    ``asyncio.run(achat_completion(...))``, so both spellings are needed."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def _next(self, kwargs):
        self.requests.append(kwargs)
        i = len(self.requests) - 1
        return self.script[i] if i < len(self.script) else _Resp(_Msg(content="fallback"))

    def create(self, **kwargs):
        return self._next(kwargs)


class _ARecorder:
    def __init__(self, rec):
        self.rec = rec

    async def create(self, **kwargs):
        return self.rec._next(kwargs)


def _agent_with_failing_tool(message, monkeypatch):
    """Agent whose only tool always raises `message`, with a scripted transport."""
    runs = []

    def send_email(to: str) -> str:
        """Send an email to a recipient."""
        runs.append(to)
        raise RuntimeError(message)

    # send_email is approval-gated by default; approve so the tool runs and fails.
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini", tools=[send_email], approval=True)

    rec = _Recorder([
        _Resp(_Msg(tool_calls=[_ToolCall("c1", "send_email", {"to": "a@b.com"})]),
              finish_reason="tool_calls"),
        _Resp(_Msg(content="CONFIDENT ANSWER WITH NO TOOL RESULT")),
    ])
    client = OpenAIClient(api_key="sk-not-a-real-key")
    fake = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=rec),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(completions=rec)),
        responses=None,
    )
    arec = _ARecorder(rec)
    afake = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=arec),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(completions=arec)),
        responses=None,
    )
    client._sync_client = fake
    client._async_client = afake
    agent._Agent__openai_client = client
    agent._unified_dispatcher = None

    # never actually sleep out a backoff in a unit test
    monkeypatch.setattr("time.sleep", lambda _d: None)
    return agent, rec, runs


def _tool_results(rec):
    return [m["content"] for m in rec.requests[-1]["messages"] if m.get("role") == "tool"]


def test_chat_reports_tool_error_to_model(monkeypatch):
    """A failing tool runs once and its error reaches the model (D-03).

    Was: the turn ended with ToolExecutionError after three runs.
    """
    agent, rec, runs = _agent_with_failing_tool("smtp down", monkeypatch)
    out = agent.chat("send the email")
    assert runs == ["a@b.com"]
    assert len(rec.requests) == 2
    assert any("smtp down" in c for c in _tool_results(rec))
    assert out == "CONFIDENT ANSWER WITH NO TOOL RESULT"


def test_tool_error_text_is_not_classified_as_an_llm_error(monkeypatch):
    """A tool whose message looks like a rate limit must not re-drive the model
    without the tool result.

    Without the fix the framework classified the *tool's* text as a retryable
    LLM error, slept, and called the model again with no tool result. Now the
    second model call carries the tool's error as its result. The text matches
    the tool RetryPolicy's ``rate_limit`` type, so the tool itself may retry.
    """
    agent, rec, runs = _agent_with_failing_tool("429 too many requests", monkeypatch)
    agent.chat("send the email")

    assert runs and all(to == "a@b.com" for to in runs), (
        "the failing tool must have executed"
    )
    assert len(rec.requests) == 2
    assert any("429 too many requests" in c for c in _tool_results(rec)), (
        "the follow-up model call must carry the tool's error as its result"
    )
