"""Categorised help panels for the PraisonAI CLI.

Single source of truth mapping every top-level command to a stable help
category. The category name is used verbatim as Typer's ``rich_help_panel`` so
``praisonai --help`` groups commands into discoverable panels instead of one
flat wall of ~90 commands.

This is purely CLI presentation — no command is removed, renamed, or hidden.
Any command not listed here falls back to :data:`DEFAULT_CATEGORY` (*Advanced*)
so nothing is ever dropped from ``--help``.
"""

from __future__ import annotations

# Fixed, ordered set of categories. Order here is documentation only; Typer
# renders panels in first-seen order as commands are grouped.
CATEGORY_GET_STARTED = "Get started"
CATEGORY_RUN_CHAT = "Run & chat"
CATEGORY_SESSIONS = "Sessions & state"
CATEGORY_CONFIG = "Config & setup"
CATEGORY_TOOLS = "Tools & knowledge"
CATEGORY_SERVE = "Serve & integrate"
CATEGORY_ADVANCED = "Advanced"

#: Category used for any command without an explicit mapping.
DEFAULT_CATEGORY = CATEGORY_ADVANCED

#: Ordered list of the canonical categories (for tests / documentation).
CATEGORIES = (
    CATEGORY_GET_STARTED,
    CATEGORY_RUN_CHAT,
    CATEGORY_SESSIONS,
    CATEGORY_CONFIG,
    CATEGORY_TOOLS,
    CATEGORY_SERVE,
    CATEGORY_ADVANCED,
)

#: Command name -> category. Commands absent here inherit ``DEFAULT_CATEGORY``.
COMMAND_CATEGORIES: dict[str, str] = {
    # Get started — the everyday first-run path.
    "init": CATEGORY_GET_STARTED,
    "setup": CATEGORY_GET_STARTED,
    "onboard": CATEGORY_GET_STARTED,
    "doctor": CATEGORY_GET_STARTED,
    "models": CATEGORY_GET_STARTED,
    "version": CATEGORY_GET_STARTED,
    "upgrade": CATEGORY_GET_STARTED,
    "uninstall": CATEGORY_GET_STARTED,

    # Run & chat — invoke agents interactively or headless.
    "run": CATEGORY_RUN_CHAT,
    "chat": CATEGORY_RUN_CHAT,
    "code": CATEGORY_RUN_CHAT,
    "ui": CATEGORY_RUN_CHAT,
    "tui": CATEGORY_RUN_CHAT,
    "call": CATEGORY_RUN_CHAT,
    "realtime": CATEGORY_RUN_CHAT,
    "research": CATEGORY_RUN_CHAT,
    "loop": CATEGORY_RUN_CHAT,
    "agents": CATEGORY_RUN_CHAT,
    "agent": CATEGORY_RUN_CHAT,

    # Sessions & state — persistence, history, checkpoints.
    "session": CATEGORY_SESSIONS,
    "checkpoint": CATEGORY_SESSIONS,
    "context": CATEGORY_SESSIONS,
    "memory": CATEGORY_SESSIONS,
    "todo": CATEGORY_SESSIONS,
    "queue": CATEGORY_SESSIONS,
    "traces": CATEGORY_SESSIONS,
    "replay": CATEGORY_SESSIONS,

    # Config & setup — configuration, credentials, environment.
    "config": CATEGORY_CONFIG,
    "auth": CATEGORY_CONFIG,
    "env": CATEGORY_CONFIG,
    "permissions": CATEGORY_CONFIG,
    "rules": CATEGORY_CONFIG,
    "hooks": CATEGORY_CONFIG,
    "paths": CATEGORY_CONFIG,
    "port": CATEGORY_CONFIG,
    "validate": CATEGORY_CONFIG,
    "completion": CATEGORY_CONFIG,

    # Tools & knowledge — agent-callable tools, RAG, skills, templates.
    "tools": CATEGORY_TOOLS,
    "skills": CATEGORY_TOOLS,
    "knowledge": CATEGORY_TOOLS,
    "rag": CATEGORY_TOOLS,
    "index": CATEGORY_TOOLS,
    "query": CATEGORY_TOOLS,
    "search": CATEGORY_TOOLS,
    "templates": CATEGORY_TOOLS,
    "recipe": CATEGORY_TOOLS,
    "workflow": CATEGORY_TOOLS,
    "mcp": CATEGORY_TOOLS,
    "browser": CATEGORY_TOOLS,
    "commit": CATEGORY_TOOLS,
    "docs": CATEGORY_TOOLS,

    # Serve & integrate — servers, gateways, deployment, integrations.
    "serve": CATEGORY_SERVE,
    "app": CATEGORY_SERVE,
    "acp": CATEGORY_SERVE,
    "daemon": CATEGORY_SERVE,
    "attach": CATEGORY_SERVE,
    "deploy": CATEGORY_SERVE,
    "publish": CATEGORY_SERVE,
    "schedule": CATEGORY_SERVE,
    "gateway": CATEGORY_SERVE,
    "bot": CATEGORY_SERVE,
    "pairing": CATEGORY_SERVE,
    "identity": CATEGORY_SERVE,
    "kanban": CATEGORY_SERVE,
    "n8n": CATEGORY_SERVE,
    "flow": CATEGORY_SERVE,
    "dashboard": CATEGORY_SERVE,
    "claw": CATEGORY_SERVE,
    "up": CATEGORY_SERVE,
    "endpoints": CATEGORY_SERVE,
    "github": CATEGORY_SERVE,
    "mint_link": CATEGORY_SERVE,

    # Advanced — deep / diagnostic / power-user commands.
    "debug": CATEGORY_ADVANCED,
    "diag": CATEGORY_ADVANCED,
    "lsp": CATEGORY_ADVANCED,
    "obs": CATEGORY_ADVANCED,
    "langfuse": CATEGORY_ADVANCED,
    "langextract": CATEGORY_ADVANCED,
    "profile": CATEGORY_ADVANCED,
    "benchmark": CATEGORY_ADVANCED,
    "eval": CATEGORY_ADVANCED,
    "test": CATEGORY_ADVANCED,
    "examples": CATEGORY_ADVANCED,
    "batch": CATEGORY_ADVANCED,
    "train": CATEGORY_ADVANCED,
    "tracker": CATEGORY_ADVANCED,
    "audit": CATEGORY_ADVANCED,
    "managed": CATEGORY_ADVANCED,
    "plugins": CATEGORY_ADVANCED,
    "sandbox": CATEGORY_ADVANCED,
    "registry": CATEGORY_ADVANCED,
    "package": CATEGORY_ADVANCED,
    "command": CATEGORY_ADVANCED,
    "standardise": CATEGORY_ADVANCED,
    "standardize": CATEGORY_ADVANCED,
}


def category_for(name: str) -> str:
    """Return the help category for ``name`` (``DEFAULT_CATEGORY`` if unmapped)."""
    return COMMAND_CATEGORIES.get(name, DEFAULT_CATEGORY)
