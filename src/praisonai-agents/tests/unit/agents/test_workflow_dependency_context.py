"""Workflow prompts must include results from pending predecessor tasks."""

import pytest

from praisonaiagents import Agent, AgentTeam, Task


class RecordingAgent(Agent):
    def __init__(self, name, reply):
        super().__init__(name=name, instructions="Follow the task.")
        self.reply = reply
        self.prompts = []

    def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.reply

    async def achat(self, prompt, **kwargs):
        return self.chat(prompt, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("upstream_async", [False, True])
@pytest.mark.parametrize("downstream_async", [False, True])
@pytest.mark.parametrize("retry", [False, True])
async def test_workflow_resolves_context_after_dependencies_finish(
    monkeypatch, upstream_async, downstream_async, retry
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setenv("PRAISONAI_TELEMETRY_DISABLED", "true")
    monkeypatch.setenv("DO_NOT_TRACK", "true")

    with (
        RecordingAgent("researcher", "UPSTREAM_RESULT_271828") as upstream,
        RecordingAgent("writer", "Written report") as downstream,
    ):
        first = Task(
            name="research",
            description="Research the topic",
            expected_output="Research findings",
            agent=upstream,
            async_execution=upstream_async,
            next_tasks=["write"],
        )
        second = Task(
            name="write",
            description="Write using previous findings",
            expected_output="A report",
            agent=downstream,
            async_execution=downstream_async,
            retry_delay=0,
        )
        if retry:
            second.validation_feedback = {
                "validation_response": "Include the original source",
                "rejected_output": "Report without a source",
            }

        def completed(task, output):
            return task is first or len(downstream.prompts) == (2 if retry else 1)

        team = AgentTeam(
            agents=[upstream, downstream],
            tasks=[first, second],
            process="workflow",
            hooks={"completion_checker": completed},
        )
        await team.astart()

        assert first.status == second.status == "completed"
        assert len(downstream.prompts) == (2 if retry else 1)
        for prompt in downstream.prompts:
            assert "research: UPSTREAM_RESULT_271828" in prompt
            if retry:
                assert "Include the original source" in prompt
                assert "Report without a source" in prompt
        assert second.validation_feedback is None
