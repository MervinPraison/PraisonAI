"""Opt-in inference through an async decorated tool and Agent.astart."""

import asyncio
import os

import pytest


@pytest.mark.live
def test_agent_uses_async_decorated_tool(monkeypatch, tmp_path):
    from praisonaiagents import Agent, tool

    model = os.environ.get("PRAISONAI_TEST_MODEL")
    if not model:
        pytest.skip("Set PRAISONAI_TEST_MODEL to choose the live provider explicitly")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    calls = []

    @tool
    async def lookup_record(value: int) -> str:
        """Return the status of a record by its numeric ID."""
        await asyncio.sleep(0)
        calls.append(value)
        return f"Record {value} is approved."

    options = dict(
        instructions="Use lookup_record when asked about a record. Report its exact status.",
        llm={"model": model, "temperature": 0, "max_tokens": 128},
        tools=[lookup_record],
        reflection=False, rules=False, output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    with Agent(**options) as agent:
        greeting = agent.start("Say ready without using a tool.")
        print("Full Agent.start output:", greeting)
        assert isinstance(greeting, str) and greeting.strip()
        answer = asyncio.run(agent.astart("Look up record 7 using lookup_record."))
        print("Full Agent.astart output:", answer)
        assert calls == [7]
        assert isinstance(answer, str) and "approved" in answer.lower()
