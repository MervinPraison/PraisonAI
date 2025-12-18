"""
AG-UI Protocol Integration for PraisonAI Agents

This module provides AG-UI (Agent-User Interface) protocol support,
enabling PraisonAI Agents to be exposed via a standardized streaming API
compatible with CopilotKit and other AG-UI frontends.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.ui.agui import AGUI
    from fastapi import FastAPI

    agent = Agent(name="Assistant", role="Helper", goal="Help users")
    agui = AGUI(agent=agent)

    app = FastAPI()
    app.include_router(agui.get_router())
"""

from praisonaiagents.ui.agui.agui import AGUI

__all__ = ["AGUI"]
