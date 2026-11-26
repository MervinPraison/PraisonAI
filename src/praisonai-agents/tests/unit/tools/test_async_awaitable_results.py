"""Async dispatch must execute awaitables returned by synchronous wrappers."""

import asyncio

import pytest

from praisonaiagents import Agent, tool
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
               reflection=False, rules=False, output="silent") as agent:
        agent._tool_timeout = 1
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
