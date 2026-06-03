"""PraisonAI Unified Dashboard — single host for all sidebar features.

Loaded by ``praisonai unified`` (aiui mode) via ``build_host_app()``.
"""

import os

import praisonaiui as aiui
from praisonai.integration.host_app import configure_host, create_host_app, is_legacy_host

configure_host(
    title="PraisonAI Unified Dashboard",
    logo="🌟",
    pages=[
        "chat",
        "agents",
        "memory",
        "knowledge",
        "skills",
        "sessions",
        "usage",
        "config",
        "logs",
    ],
    agent_kwargs={
        "name": "PraisonAI",
        "instructions": "You are a helpful assistant for the PraisonAI unified dashboard.",
        "llm": os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
    },
)


@aiui.welcome
async def on_welcome():
    await aiui.say("🌟 Welcome to PraisonAI Unified Dashboard!")
    await aiui.say("Use the sidebar to access chat, agents, memory, and more.")


if is_legacy_host():

    @aiui.reply
    async def on_reply(message: str, settings: dict | None = None):
        await aiui.think("Processing...")
        await aiui.say(f"Unified Dashboard received: {message}")


app = create_host_app()
