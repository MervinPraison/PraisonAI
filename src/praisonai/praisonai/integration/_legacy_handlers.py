"""Shared legacy @aiui.reply handlers for bundled default apps."""

from __future__ import annotations


def register_legacy_reply(aiui, *, agent_name: str = "PraisonAI"):
    """Register callback-only reply handler when ``PRAISONAI_HOST_LEGACY=1``."""

    @aiui.reply
    async def legacy_reply(message: str, session_id: str = "default"):
        from praisonaiagents import Agent

        agent = Agent(
            name=agent_name,
            instructions="You are a helpful assistant.",
            llm="gpt-4o-mini",
        )
        return agent.run(message)
