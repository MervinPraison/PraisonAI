"""Real agent output retains StepResult state and stop behavior on cache hits."""

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Set RUN_REAL_KEY_TESTS=1 and OPENAI_API_KEY for the real agentic test",
)


def test_cached_real_agent_step_retains_variables_and_stop():
    from praisonaiagents import Agent
    from praisonaiagents.llm.llm import LLM
    from praisonaiagents.workflows.workflows import AgentFlow, StepResult

    agent = Agent(
        name="cache-smoke",
        instructions="Answer briefly.",
        llm=LLM(
            model=os.environ.get("PRAISONAI_TEST_MODEL", "gpt-4o-mini"),
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL"),
        ),
        output="silent",
    )
    calls = []

    def finish(ctx):
        calls.append("finish")
        response = agent.start("Say hello in one sentence.")
        print(response)
        assert isinstance(response, str) and response.strip()
        return StepResult(
            output=response, stop_workflow=True, variables={"answer": response}
        )

    def downstream(ctx):
        calls.append("downstream")
        return "unexpected"

    flow = AgentFlow(steps=[finish, downstream], cache=True)
    first = flow.run("same", verbose=False)
    second = flow.run("same", verbose=False)

    assert calls == ["finish"]
    assert first == second
    assert second["variables"]["answer"] == second["output"]
