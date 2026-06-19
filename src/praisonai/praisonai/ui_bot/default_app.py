"""PraisonAI Bot UI — Bot interface with step visualization.

Loaded by ``praisonai ui bot`` → ``aiui run app.py``.
Replaces ui/bot.py (Chainlit) with aiui implementation.

Requires: pip install "praisonai[ui]"
"""

import os
from praisonai.integration.host_app import UIPreset, build_ui_app

app = build_ui_app(UIPreset(
    title="PraisonAI Bot",
    logo="🤖",
    pages=["chat", "sessions"],
    theme={"preset": "green", "dark_mode": True, "radius": "lg"},
    agent_kwargs={
        "name": "PraisonBot",
        "instructions": "You are a helpful bot assistant. Break down your reasoning into clear steps.",
        "llm": os.getenv("MODEL_NAME", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
    },
    starters=[
        {"label": "Help", "message": "What can you help me with?", "icon": "❓"},
        {"label": "Status", "message": "What's your current status?", "icon": "📊"},
        {"label": "Commands", "message": "What commands do you understand?", "icon": "⌨️"},
        {"label": "About", "message": "Tell me about yourself", "icon": "ℹ️"},
    ],
    welcome="🤖 Hi! I'm your PraisonAI Bot. I can help with various tasks and show you step-by-step reasoning.",
))