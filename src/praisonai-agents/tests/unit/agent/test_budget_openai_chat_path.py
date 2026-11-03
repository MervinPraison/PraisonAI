"""Sync OpenAI-client chat must surface BudgetExceededError, not return None."""
from unittest.mock import patch

import pytest

from praisonaiagents import Agent, BudgetExceededError, ExecutionConfig


def test_sync_chat_reraises_budget_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # client is built lazily; no request is sent
    agent = Agent(
        name="b", instructions="x", llm="gpt-4o-mini", output="silent",
        execution=ExecutionConfig(max_budget=0.01),
    )
    with patch.object(
        agent, "_chat_completion",
        side_effect=BudgetExceededError("b", 0.02, 0.01),
    ):
        with pytest.raises(BudgetExceededError):
            agent.chat("hello")
