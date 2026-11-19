"""PraisonAI Chat UI — the dashboard's pages around one chat agent.

Loaded by ``praisonai ui`` → ``aiui run app.py``.
Same sidebar pages as ``praisonai dashboard`` (DASHBOARD_PAGES).

Requires: pip install "praisonai[ui]"
Set OPENAI_API_KEY before running.

Run:
    praisonai ui
"""

import os
from praisonai.integration.host_app import DASHBOARD_PAGES, UIPreset, build_ui_app

# Custom agent factory for chat with external tools
def create_chat_agent(settings):
    try:
        from praisonaiagents import Agent
        from praisonai.ui._external_agents import external_agent_tools
        
        tools = external_agent_tools(
            settings or {},
            workspace=os.environ.get("PRAISONAI_WORKSPACE", "."),
        )
        return Agent(
            name="PraisonAI",
            instructions="You are a helpful assistant. Delegate coding/analysis tasks to external subagents when available.",
            llm=os.getenv("MODEL_NAME", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
            tools=tools if tools else None,
        )
    except ImportError:
        return None

app = build_ui_app(UIPreset(
    title="PraisonAI Chat",
    logo="🤖",
    pages=DASHBOARD_PAGES,
    theme={"preset": "blue", "dark_mode": True, "radius": "lg"},
    agent_kwargs={
        "name": "PraisonAI",
        "instructions": "You are a helpful assistant. Delegate coding/analysis tasks to external subagents when available.",
        "llm": os.getenv("MODEL_NAME", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
    },
    starters=[
        {"label": "Research", "message": "Research the latest AI trends", "icon": "🔬"},
        {"label": "Write", "message": "Write a blog post about AI agents", "icon": "✍️"},
        {"label": "Code", "message": "Write a Python function to sort a list", "icon": "💻"},
        {"label": "Brainstorm", "message": "Give me 5 startup ideas using AI agents", "icon": "💡"},
    ],
    welcome="👋 Hi! I'm your PraisonAI assistant. Ask me anything!",
    openai_fallback=True,
    agent_factory=create_chat_agent,
))