"""PraisonAI Unified Dashboard — single host for all sidebar features.

Loaded by ``praisonai unified`` (aiui mode) via ``build_host_app()``.
"""

import os
from praisonai.integration.host_app import UIPreset, build_ui_app

app = build_ui_app(UIPreset(
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
    theme={"preset": "blue", "dark_mode": True, "radius": "lg"},
    agent_kwargs={
        "name": "PraisonAI",
        "instructions": "You are a helpful assistant for the PraisonAI unified dashboard.",
        "llm": os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
    },
    starters=[
        {"label": "Dashboard", "message": "Show me the dashboard overview", "icon": "📊"},
        {"label": "Agents", "message": "List all available agents", "icon": "🤖"},
        {"label": "Help", "message": "How do I use this dashboard?", "icon": "❓"},
        {"label": "Status", "message": "Check system status", "icon": "🔍"},
    ],
    welcome="🌟 Welcome to PraisonAI Unified Dashboard! Access all features from the sidebar.",
))