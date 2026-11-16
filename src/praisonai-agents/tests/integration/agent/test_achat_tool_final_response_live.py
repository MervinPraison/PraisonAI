"""Live check that async chat with a tool returns a model-written final answer.

Exercises the post-tool follow-up request in ``ChatMixin._achat_completion``
by turning off the default unified dispatch, so ``_achat_impl`` takes the
legacy OpenAI-client branch. Skipped unless ``OPENAI_API_KEY`` is set.
"""
import os

import pytest

from praisonaiagents import Agent


def get_secret_number() -> str:
    """Return the secret number."""
    return "4217"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
async def test_achat_with_tool_returns_final_answer_live():
    agent = Agent(
        name="test",
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini",
        tools=[get_secret_number],
    )
    # The default unified path never calls _achat_completion.
    agent._use_unified_llm_dispatch = False
    result = await agent.astart(
        "Use the get_secret_number tool, then reply with one sentence that "
        "contains the secret number."
    )
    print(f"Agent output: {result}")
    assert result
    assert "4217" in str(result)
    # Without the fix the raw tool output ("4217") is returned unchanged.
    assert str(result).strip() != "4217"
