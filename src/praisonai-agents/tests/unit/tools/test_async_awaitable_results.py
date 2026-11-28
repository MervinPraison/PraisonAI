"""Async dispatch must execute awaitables returned by synchronous wrappers."""

import asyncio
from types import SimpleNamespace

import pytest

from praisonaiagents import Agent, tool
from praisonaiagents.config import ToolConfig
from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.tools.base import BaseTool
from praisonaiagents.tools.injected import get_current_state


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["decorated", "base", "callable"])
async def test_async_dispatch_awaits_wrapped_result(kind, isolated_home):
    states = []

    async def lookup(value: int) -> str:
        """Look up the requested value."""
        await asyncio.sleep(0)
        states.append(get_current_state())
        return f"found:{value}"

    class Lookup(BaseTool):
        name = "lookup"
        description = "Look up the requested value."

        def run(self, value: int):
            return lookup(value)

    def wrapped(value: int):
        """Look up the requested value."""
        return lookup(value)

    target = {"decorated": tool(lookup), "base": Lookup(), "callable": wrapped}[kind]
    name = target.name if isinstance(target, BaseTool) else target.__name__
    with Agent(name="lookup-agent", instructions="Look up records", tools=[target],
               reflection=False, rules=False, output="silent") as agent:
        result = await agent.execute_tool_async(name, {"value": 7})
    assert result == "found:7"
    assert len(states) == 1 and states[0].metadata["agent_name"] == "lookup-agent"


@pytest.mark.asyncio
async def test_wrapped_coroutine_obeys_tool_timeout(isolated_home):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    @tool
    async def wait_for_record() -> str:
        """Wait for a record to become available."""
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with Agent(instructions="Wait for records", tools=[wait_for_record],
               reflection=False, rules=False, output="silent",
               tool_config=ToolConfig(timeout=1)) as agent:
        result = await agent.execute_tool_async("wait_for_record", {})
    assert started.is_set() and cancelled.is_set()
    assert result["timeout"] is True


@pytest.mark.asyncio
async def test_wrapped_coroutine_error_reaches_caller(isolated_home):
    @tool
    async def lookup_record() -> str:
        """Look up a record."""
        raise RuntimeError("record service unavailable")

    with Agent(instructions="Look up records", tools=[lookup_record],
               reflection=False, rules=False, output="silent") as agent:
        result = await agent.execute_tool_async("lookup_record", {})
    assert "record service unavailable" in result["error"]


@pytest.mark.asyncio
async def test_astart_sends_wrapped_tool_result(isolated_home):
    from openai.types.chat import ChatCompletion

    tool_messages = []

    @tool
    async def lookup_record(value: int) -> str:
        """Look up a record by its numeric ID."""
        return f"record:{value}"

    async def reply(*, messages, **kwargs):
        results = [m["content"] for m in messages if m["role"] == "tool"]
        if results:
            tool_messages.extend(results)
            message = {"role": "assistant", "content": "done"}
        else:
            message = {
                "role": "assistant",
                "tool_calls": [{
                    "id": "lookup-1",
                    "type": "function",
                    "function": {"name": "lookup_record", "arguments": '{"value": 7}'},
                }],
            }
        return ChatCompletion.model_validate({
            "id": "completion-1", "object": "chat.completion",
            "created": 1, "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "stop" if results else "tool_calls"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        })

    client = OpenAIClient(api_key="fixture-key", base_url="https://fixture.invalid/v1")
    client._async_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=reply)),
    )
    with Agent(
        instructions="Look up records", llm="gpt-4o-mini", tools=[lookup_record],
        reflection=False, rules=False, output="silent",
    ) as agent:
        agent._Agent__openai_client = client
        result = await agent.astart("Look up record 7", stream=False)

    assert result == "done"
    assert len(tool_messages) == 1 and "record:7" in tool_messages[0]
