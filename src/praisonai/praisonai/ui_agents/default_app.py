"""PraisonAI Agents UI — YAML-defined agents dashboard.

Loaded by ``praisonai ui agents`` → ``aiui run app.py``.
Replaces ui/agents.py (Chainlit) with aiui implementation.

Requires: pip install "praisonai[ui]"
"""

import os
import praisonaiui as aiui
from praisonai.ui._aiui_datastore import PraisonAISessionDataStore

# ── Set up datastore bridge ─────────────────────────────────
aiui.set_datastore(PraisonAISessionDataStore())

# ── Dashboard style ─────────────────────────────────────────
aiui.set_style("dashboard")
aiui.set_branding(title="PraisonAI Agents", logo="🤖")
aiui.set_theme(preset="blue", dark_mode=True, radius="lg")
aiui.set_pages([
    "chat",
    "agents",
    "memory",
    "sessions",
])

# ── Load agents from YAML ───────────────────────────────────
def _load_agents_from_yaml():
    """Load agents from agents.yaml file if available."""
    agents_file = os.path.join(os.getcwd(), "agents.yaml")
    if not os.path.exists(agents_file):
        return []
    
    try:
        import yaml
        with open(agents_file, 'r') as f:
            config = yaml.safe_load(f)
        
        agents = []
        if 'agents' in config:
            for agent_def in config['agents']:
                agents.append({
                    "name": agent_def.get('name', 'Agent'),
                    "description": agent_def.get('description', 'YAML-defined agent'),
                    "instructions": agent_def.get('instructions', agent_def.get('role', '')),
                    "model": agent_def.get('model', os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
                    "icon": "🤖",
                })
        return agents
    except Exception as e:
        print(f"⚠️  Failed to load agents.yaml: {e}")
        return []

# ── Register YAML agents ────────────────────────────────────
yaml_agents = _load_agents_from_yaml()
if yaml_agents:
    try:
        from praisonaiui.features.agents import get_agent_registry
        registry = get_agent_registry()
        
        for agent_def in yaml_agents:
            registry.create(agent_def)
            print(f"   ✓ Agent: {agent_def['icon']} {agent_def['name']}")
    except Exception as e:
        print(f"   ⚠️  Agent registration failed: {e}")
else:
    print("   ℹ️  No agents.yaml found, using default agents")

# ── Default agents if no YAML ───────────────────────────────
if not yaml_agents:
    DEFAULT_AGENTS = [
        {
            "name": "Assistant",
            "description": "General purpose AI assistant",
            "instructions": "You are a helpful AI assistant. Provide clear and accurate responses.",
            "model": os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
            "icon": "🤖",
        },
    ]
    
    try:
        from praisonaiui.features.agents import get_agent_registry
        registry = get_agent_registry()
        
        for agent_def in DEFAULT_AGENTS:
            registry.create(agent_def)
            print(f"   ✓ Default Agent: {agent_def['icon']} {agent_def['name']}")
    except Exception as e:
        print(f"   ⚠️  Default agent registration failed: {e}")

@aiui.starters
async def get_starters():
    """Suggest conversation starters for agents."""
    return [
        {"label": "Run Task", "message": "Execute the task defined in agents.yaml", "icon": "▶️"},
        {"label": "List Agents", "message": "What agents are available?", "icon": "👥"},
        {"label": "Agent Status", "message": "Show status of all agents", "icon": "📊"},
    ]

@aiui.welcome
async def on_welcome():
    """Welcome message."""
    await aiui.say("👋 Welcome to PraisonAI Agents! This interface runs YAML-defined multi-agent workflows.")

# Session-scoped agent cache
_agents_cache = {}

@aiui.reply
async def on_message(message: str):
    """Handle messages with agent execution."""
    await aiui.think("Processing...")
    
    try:
        from praisonaiagents import Agent
        
        # Create or get cached agent
        session_id = getattr(aiui.current_session, 'id', 'default')
        if session_id not in _agents_cache:
            _agents_cache[session_id] = Agent(
                name="AgentsRunner",
                instructions="You are an agent runner that coordinates YAML-defined workflows.",
                llm=os.getenv("MODEL_NAME", "gpt-4o-mini"),
            )
        
        agent = _agents_cache[session_id]
        result = await agent.achat(str(message))
        
        # Stream the response
        response_text = str(result) if result else "No response"
        words = response_text.split(" ")
        for i, word in enumerate(words):
            await aiui.stream_token(word + (" " if i < len(words) - 1 else ""))
            
    except Exception as e:
        await aiui.say(f"❌ Error: {e}")

@aiui.cancel
async def on_cancel():
    await aiui.say("⏹️ Stopped.")