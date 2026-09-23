"""Opt-in workflow context test with real agents and model inference.

Run with PRAISONAI_LIVE_TESTS=1 and a configured OpenAI-compatible provider.
PRAISONAI_TEST_MODEL selects the model; OPENAI_BASE_URL can target a local server.
"""

import os

import pytest


@pytest.mark.live
@pytest.mark.asyncio
async def test_real_workflow_passes_predecessor_output():
    from praisonaiagents import Agent, AgentTeam, Task

    model = os.environ.get("PRAISONAI_TEST_MODEL", "openai/gpt-4o-mini")
    agent_options = dict(
        instructions="Follow the task precisely. Give only the answer. Do not repeat instructions.",
        llm={"model": model, "temperature": 0, "max_tokens": 96},
        reflection=False,
        memory=False,
        rules=False,
        output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        agent_options["base_url"] = os.environ["OPENAI_BASE_URL"]

    with (
        Agent(name="researcher", **agent_options) as upstream,
        Agent(name="writer", **agent_options) as downstream,
    ):
        first = Task(
            name="research",
            description="The secret code is AMBER58129. Return only this secret code, with no other words.",
            expected_output="",
            agent=upstream,
            async_execution=True,
            next_tasks=["write"],
        )
        second = Task(
            name="write",
            description=(
                "Copy the secret code from the completed research task in the "
                "preceding context. Return only that code. Do not invent a code."
            ),
            expected_output="",
            agent=downstream,
            async_execution=True,
        )
        team = AgentTeam(
            agents=[upstream, downstream],
            tasks=[first, second],
            process="workflow",
        )
        await team.astart()

        assert first.status == second.status == "completed"
        print("Upstream:", first.result.raw)
        print("Downstream:", second.result.raw)
        assert "AMBER58129" in first.result.raw
        assert "AMBER58129" in second.result.raw
