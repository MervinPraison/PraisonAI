"""A tool failure must reach the caller as a tool failure.

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
from praisonaiagents.errors import ToolExecutionError
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

    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini", tools=[send_email])

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


def test_chat_raises_tool_execution_error(monkeypatch):
    """A failing tool must surface as ToolExecutionError, not as None."""
    agent, _rec, runs = _agent_with_failing_tool("smtp down", monkeypatch)
    with pytest.raises(ToolExecutionError):
        agent.chat("send the email")
    # The failing tool must have actually run, proving the error surfaced
    # *because of* the tool call rather than before it. The tool executor retries
    # a failing tool up to 3 times, and every attempt targets the same recipient.
    assert runs and all(to == "a@b.com" for to in runs)


def test_tool_error_text_is_not_classified_as_an_llm_error(monkeypatch):
    """A tool whose message looks like a rate limit must not re-drive the model.

    Without the fix the framework classifies the *tool's* text as a retryable
    LLM error, sleeps, and calls the model a second time with no tool result --
    returning that answer to the user as a success.
    """
    agent, rec, runs = _agent_with_failing_tool("429 too many requests", monkeypatch)
    with pytest.raises(ToolExecutionError):
        agent.chat("send the email")

    assert runs and all(to == "a@b.com" for to in runs), (
        "the failing tool must have executed"
    )
    assert len(rec.requests) == 1, (
        f"model was re-driven {len(rec.requests)} times after a tool failure; "
        f"last request carried roles "
        f"{[m['role'] for m in rec.requests[-1]['messages']]}"
    )
