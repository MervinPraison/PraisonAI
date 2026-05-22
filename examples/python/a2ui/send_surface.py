#!/usr/bin/env python3
"""Minimal A2UI example — agent + send_a2ui_messages tool.

Install:
    pip install praisonaiagents[a2ui]

Run:
    python send_surface.py

For live rendering, use PraisonAIUI with AG-UI (/agui) — see integrate-a2ui-frontend docs.
"""

from praisonaiagents import Agent
from praisonaiagents.tools.a2ui_tools import send_a2ui_messages

agent = Agent(
    name="ui-assistant",
    instructions=(
        "When asked for UI, call send_a2ui_messages with A2UI v0.9 JSON "
        "(createSurface on surface id 'main')."
    ),
    tools=[send_a2ui_messages],
)

if __name__ == "__main__":
    result = agent.start("Show a simple welcome card on surface main")
    print(result)
