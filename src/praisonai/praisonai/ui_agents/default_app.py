"""PraisonAI Agents UI — YAML-defined agents dashboard.

Loaded by ``praisonai ui agents`` → ``aiui run app.py``.
Replaces ui/agents.py (Chainlit) with aiui implementation.

Requires: pip install "praisonai[ui]"
"""

import os
from praisonai.integration.host_app import UIPreset, build_ui_app

def load_agents_from_yaml():
    """Load agents from agents.yaml and register them."""
    try:
        import yaml
        from praisonaiui.features.agents import get_agent_registry
        
        if os.path.exists("agents.yaml"):
            with open("agents.yaml", "r") as f:
                config = yaml.safe_load(f)
                
            if config and "agents" in config:
                registry = get_agent_registry()
                for agent in config["agents"]:
                    registry.register(agent["name"], agent)
    except Exception as e:
        print(f"Failed to load agents from YAML: {e}")

app = build_ui_app(UIPreset(
    title="PraisonAI Agents",
    logo="🤖",
    pages=["chat", "agents", "memory", "sessions"],
    theme={"preset": "blue", "dark_mode": True, "radius": "lg"},
    agent_kwargs={
        "name": "AgentsRunner",
        "instructions": "You are an agent runner that coordinates YAML-defined workflows.",
        "llm": os.getenv("MODEL_NAME", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
    },
    starters=[
        {"label": "List Agents", "message": "Show me available agents", "icon": "📋"},
        {"label": "Run Workflow", "message": "Execute the default workflow", "icon": "▶️"},
        {"label": "Agent Status", "message": "Check agent system status", "icon": "📊"},
        {"label": "Help", "message": "How do I define agents in YAML?", "icon": "❓"},
    ],
    welcome="🤖 Welcome to PraisonAI Agents! I coordinate YAML-defined agent workflows.",
    agent_loader=load_agents_from_yaml,
))