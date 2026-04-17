"""PraisonAIUI — Default App (Dashboard with Agents + Feature Explorer).

Loaded by ``praisonai claw`` → ``aiui run app.py``.
All built-in sidebar pages are enabled by default.

Agents: Researcher, Writer, Coder
Custom page: Feature Explorer
"""

import os
import praisonaiui as aiui

# ── Wire PraisonAI native sessions into aiui dashboard ─────
try:
    from praisonai.ui._aiui_datastore import PraisonAISessionDataStore
    aiui.set_datastore(PraisonAISessionDataStore())
except ImportError:
    # aiui or praisonaiagents not available - sessions won't persist
    pass

# ── Dashboard style ─────────────────────────────────────────
aiui.set_style("dashboard")
aiui.set_pages([
    "chat",        # Core AI chat
    "channels",    # Messaging platforms
    "agents",      # Agent management
    "skills",      # Available tools
    "memory",      # Agent memory
    "knowledge",   # Knowledge base
    "cron",        # Scheduled jobs
    "guardrails",  # Safety rules
    "sessions",    # Conversation history
    "usage",       # Token usage & costs
    "config",      # Runtime configuration
    "logs",        # Server logs
    "debug",       # System debug info
])

# ── Agent definitions ───────────────────────────────────────
AGENTS = [
    {
        "agent_id": "researcher",
        "name": "Researcher",
        "description": "Research assistant — finds and summarizes information",
        "instructions": (
            "You are a research assistant. Provide well-structured answers "
            "with key facts. Keep responses concise but informative."
        ),
        "model": os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
        "icon": "🔬",
    },
    {
        "agent_id": "writer",
        "name": "Writer",
        "description": "Creative writer — generates content on any topic",
        "instructions": (
            "You are a creative writer. Write engaging content in a clear, "
            "professional style. Keep responses focused and well-organized."
        ),
        "model": os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
        "icon": "✍️",
    },
    {
        "agent_id": "coder",
        "name": "Coder",
        "description": "Coding assistant — Python, JavaScript, and more",
        "instructions": (
            "You are a coding assistant. Write clean, well-commented "
            "code with explanations. Support Python, JavaScript, and "
            "other popular languages."
        ),
        "model": os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
        "icon": "💻",
    },
]



# ── Custom page: Feature Explorer ───────────────────────────

@aiui.page(
    "explorer",
    title="Explorer",
    icon="🔬",
    group="Control",
    order=55,
)
async def explorer_page():
    """Three-column feature explorer — custom view renders in JS."""
    return aiui.layout([
        aiui.text("Feature Explorer loads via custom view module."),
    ])


# ── Register agents in dashboard CRUD ───────────────────────

def _register_agents_in_dashboard():
    """Bridge agents into the dashboard agents_crud feature."""
    from praisonaiui.features.agents import get_agent_registry

    registry = get_agent_registry()
    existing = registry.list_all()
    existing_names = {a.get("name") for a in existing}

    for agent_def in AGENTS:
        if agent_def["name"] in existing_names:
            continue
        registry.create({
            "name": agent_def["name"],
            "description": agent_def["description"],
            "instructions": agent_def["instructions"],
            "model": agent_def["model"],
            "icon": agent_def["icon"],
        })
        print(f"   ✓ Agent: {agent_def['icon']} {agent_def['name']}")

try:
    _register_agents_in_dashboard()
except Exception as e:
    print(f"   ⚠️  Agent registration failed (non-fatal): {e}")
