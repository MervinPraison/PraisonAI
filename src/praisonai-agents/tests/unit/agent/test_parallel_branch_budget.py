"""Shared-agent workflow branches must report spend to the original agent."""

import copy
import threading

import pytest

litellm = pytest.importorskip("litellm")
from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.errors import BudgetExceededError
from praisonaiagents.workflows import Workflow, parallel


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)


def test_parallel_shared_agent_spend_and_budget(monkeypatch):
    barrier = threading.Barrier(2)
    calls = []

    def completion(*args, **kwargs):
        calls.append(1)
        barrier.wait(timeout=10)
        return litellm.ModelResponse(
            model=kwargs['model'],
            usage={"prompt_tokens": 1500, "completion_tokens": 1500, "total_tokens": 3000},
            choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        )

    monkeypatch.setattr(litellm, "completion", completion)
    agent = Agent(name="worker", instructions="work", llm="anthropic/claude-3-5-sonnet-20240620",
                  output="silent", execution=ExecutionConfig(max_budget=1.0))
    result = Workflow(steps=[parallel([agent, agent])]).start("work")
    assert result["status"] == "completed"
    assert len(calls) == 2
    assert agent.cost_summary["llm_calls"] == 2
    assert agent.cost_summary["tokens_in"] == 3000
    assert agent.cost_summary["tokens_out"] == 3000
    assert agent.total_cost > 0
    agent._max_budget = agent.total_cost
    with pytest.raises(BudgetExceededError):
        agent.chat("after budget")
    assert len(calls) == 2


def test_queued_branch_cannot_start_after_budget_is_spent(monkeypatch):
    calls = []

    def completion(*args, **kwargs):
        calls.append(1)
        return litellm.ModelResponse(
            model=kwargs["model"],
            usage={"prompt_tokens": 1500, "completion_tokens": 1500, "total_tokens": 3000},
            choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        )

    monkeypatch.setattr(litellm, "completion", completion)
    agent = Agent(name="worker", instructions="work", llm="anthropic/claude-3-5-sonnet-20240620",
                  output="silent", execution=ExecutionConfig(max_budget=0.001))
    Workflow(steps=[parallel([agent, agent], max_workers=1)]).start("work")
    assert len(calls) == 1
    assert agent.cost_summary["llm_calls"] == 1


def test_deepcopy_keeps_accounting_independent():
    agent = Agent(name="worker", instructions="work", output="silent")
    clone = copy.deepcopy(agent)
    clone._record_llm_usage(3, 4, 0.25)
    assert clone.cost_summary["cost"] == 0.25
    assert agent.cost_summary["cost"] == 0
