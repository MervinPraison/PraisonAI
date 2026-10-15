"""Issue #5850: the built-in ``clarify`` tool must reach the user on bot turns.

Without a bound handler ``clarify`` returns a "best judgment" string and the
agent silently guesses. A bot turn now binds a handler that delivers the
question (choices as ``MessagePresentation.question()`` reply buttons) and
tells the agent to stop and wait for the next message.
"""

import asyncio

import pytest

from praisonaiagents.tools.clarify import clarify


class _ClarifyingAgent:
    """Minimal agent whose turn calls the shared ``clarify`` tool."""

    def __init__(self, choices=None):
        self.chat_history = []
        self.choices = choices
        self.tool_result = None

    def chat(self, prompt):
        self.tool_result = asyncio.run(
            clarify.run(question="Which environment?", choices=self.choices)
        )
        return "Which environment? staging / production"


@pytest.mark.asyncio
async def test_bot_turn_routes_clarify_to_user_with_question_buttons():
    from praisonai_bot.bots._session import BotSessionManager

    session = BotSessionManager()
    agent = _ClarifyingAgent(choices=["staging", "production"])

    reply = await session.chat(agent, "u1", "deploy it")

    assert reply == "Which environment? staging / production"
    assert "best judgment" not in agent.tool_result
    assert "Do not guess" in agent.tool_result

    presentation = session.pop_last_presentation("u1")
    assert presentation is not None
    buttons = [b for block in presentation.blocks for b in (block.buttons or [])]
    assert [b.label for b in buttons] == ["staging", "production"]


@pytest.mark.asyncio
async def test_free_text_clarify_has_no_buttons_and_binding_is_turn_scoped():
    from praisonai_bot.bots._session import BotSessionManager

    session = BotSessionManager()
    agent = _ClarifyingAgent()

    await session.chat(agent, "u1", "deploy it")

    assert "Do not guess" in agent.tool_result
    assert session.pop_last_presentation("u1") is None
    # Outside a bot turn the headless fallback is unchanged.
    assert "best judgment" in await clarify.run(question="Which environment?")
