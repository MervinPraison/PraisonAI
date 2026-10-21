"""Workflow dependents must honor failure policy after synchronous predecessors."""
import asyncio

import pytest

from praisonaiagents import Agent, AgentTeam, Task


class ScriptedAgent(Agent):
    """Exercise production task scheduling without provider requests."""

    def __init__(self, name, reply):
        super().__init__(name=name, instructions="test", llm="gpt-4o-mini")
        self.reply = reply
        self.calls = 0

    def chat(self, prompt, **kwargs):
        """Record a real dispatch of this task's agent."""
        self.calls += 1
        return self.reply

    async def achat(self, prompt, **kwargs):
        """Record asynchronous dispatch through the same fixture."""
        return self.chat(prompt, **kwargs)


@pytest.mark.parametrize("entry", ["start", "astart"])
@pytest.mark.parametrize("upstream_async", [False, True])
@pytest.mark.parametrize("downstream_async", [False, True])
@pytest.mark.parametrize("policy", ["stop", "continue", "skip"])
def test_workflow_failed_predecessor_policy(entry, upstream_async, downstream_async, policy):
    """Default dependents do not execute; explicit degraded-mode ones still do."""
    upstream = ScriptedAgent("upstream", None)
    downstream = ScriptedAgent("downstream", "done")
    first = Task(name="first", description="first", agent=upstream,
                 is_start=True, next_tasks=["second"], async_execution=upstream_async, max_retries=1)
    flags = {"on_error": "continue"} if policy == "continue" else {}
    if policy == "skip":
        flags["skip_on_failure"] = True
    second = Task(name="second", description="second", agent=downstream,
                  async_execution=downstream_async, max_retries=1, **flags)
    team = AgentTeam(agents=[upstream, downstream], tasks=[first, second], process="workflow")
    if entry == "astart":
        asyncio.run(team.astart())
    else:
        team.start()
    assert first.status == "failed"
    assert upstream.calls == 1
    assert downstream.calls == (0 if policy == "stop" else 1)
