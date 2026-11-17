"""A failed model call must not end an autonomous run as a success (F-21).

chat()/achat() return None on a failed LLM call (the error is on
agent._last_error). The autonomy loops took that None as the answer:
success=True, completion_reason="goal", output="None".
"""

import asyncio

import pytest

from praisonaiagents import Agent


def _agent(mode):
    agent = Agent(name="a", instructions="hi", autonomy=True)

    def failed(prompt, **kw):
        agent._last_error = RuntimeError("model down")
        return None

    async def afailed(prompt, **kw):
        return failed(prompt)

    agent.chat, agent.achat = failed, afailed
    return agent


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_failed_call_ends_the_run_as_an_error(mode, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = _agent(mode)
    run = agent.run_autonomous("go", max_iterations=3) if mode == "sync" \
        else asyncio.run(agent.run_autonomous_async("go", max_iterations=3))
    assert (run.success, run.completion_reason) == (False, "error")
    assert run.error == "model down" and run.output == "model down"


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_a_real_answer_still_completes(mode, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="hi", autonomy=True)
    agent.chat = lambda p, **kw: "done"

    async def achat(p, **kw):
        return "done"

    agent.achat = achat
    run = agent.run_autonomous("go", max_iterations=3) if mode == "sync" \
        else asyncio.run(agent.run_autonomous_async("go", max_iterations=3))
    assert (run.success, run.completion_reason, run.output) == (True, "goal", "done")
