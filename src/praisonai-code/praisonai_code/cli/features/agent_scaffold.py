"""
Interactive, LLM-assisted authoring for custom agent definitions.

Backs ``praisonai agent create`` (see ``commands/agent.py``): turns a one-line
description into a valid, permission-scoped ``.praisonai/agents/<name>.md`` that
``CustomDefinitionsDiscovery._load_agent`` re-parses losslessly.

Design notes (kept lightweight, no new runtime surface):
- Permission presets are the existing ``mode`` shorthands already understood by
  ``resolve_permission_config`` (``MODE_RULES``): ``full``/``read-only``/
  ``review``. The chosen preset is written to the ``mode`` frontmatter key, so
  the authored agent inherits the identical permission grammar the runtime uses
  — no parallel permission vocabulary is introduced here.
- The system-prompt draft reuses the plain ``Agent`` generation path already
  proven by ``init --generate`` (``commands/init.py``). Generation is guarded:
  any failure degrades to an editable stub so file creation never blocks.
"""

from pathlib import Path
from typing import Optional

import yaml

from .custom_definitions import MODE_RULES

# User-facing permission presets → the ``mode`` frontmatter value they map to.
# Every value is a key of MODE_RULES so it resolves through the runtime's
# existing permission grammar unchanged. Ordered for stable interactive display.
PERMISSION_PRESETS = {
    "read-only": "read-only",
    "review": "review",
    "full": "full",
}

DEFAULT_PERMISSION = "full"


def validate_agent_name(name: str) -> str:
    """Return a sanitised agent name or raise ``ValueError``.

    The name becomes a file stem under ``.praisonai/agents/``, so it must be a
    single path-free token. Rejecting separators and traversal components keeps
    every write contained within the chosen agents directory (no ``../`` escape,
    no absolute paths).
    """
    candidate = (name or "").strip()
    if not candidate:
        raise ValueError("Agent name must not be empty.")
    if candidate in {".", ".."} or any(sep in candidate for sep in ("/", "\\")):
        raise ValueError(
            f"Invalid agent name {name!r}: use a simple name without path "
            "separators (e.g. 'code-reviewer')."
        )
    if Path(candidate).name != candidate:
        raise ValueError(
            f"Invalid agent name {name!r}: use a simple name without path "
            "separators (e.g. 'code-reviewer')."
        )
    return candidate


def resolve_agents_dir(global_: bool) -> Path:
    """Return the target ``.praisonai/agents/`` directory (project or global)."""
    from ..utils.project import get_git_root

    if global_:
        base = Path.home() / ".praisonai"
    else:
        base = (get_git_root() or Path.cwd()) / ".praisonai"
    return base / "agents"


def draft_system_prompt(description: str, role: str, model: Optional[str]) -> Optional[str]:
    """Draft a system prompt from a one-line description via the Agent runtime.

    Reuses the same plain ``Agent.run`` path as ``init --generate``. Returns the
    drafted prompt text, or ``None`` on any failure so the caller can fall back
    to an editable stub (generation must never block file creation).
    """
    try:
        from praisonaiagents import Agent

        prompt = (
            "Write a concise, high-quality system prompt for a custom AI agent.\n"
            f"The agent's role: {role}\n"
            f"The agent's purpose (from the author): {description}\n\n"
            "Output ONLY the system prompt body as plain markdown — no code "
            "fences, no preamble, no frontmatter. Address the agent in the "
            "second person, state its responsibilities, and note when it should "
            "ask for clarification instead of guessing."
        )
        agent = Agent(
            instructions=(
                "You write clear, focused system prompts for AI agents. "
                "Prefer concrete guidance over generic filler."
            ),
            llm=model,
        )
        result = agent.run(prompt)
        text = (result or "").strip()
        return text or None
    except Exception:
        return None


def _stub_system_prompt(description: str) -> str:
    """Editable fallback body used when LLM drafting is unavailable."""
    return (
        f"You are an agent whose purpose is: {description}\n\n"
        "Describe how you should behave here. Be specific about your "
        "responsibilities, and ask for clarification instead of guessing."
    )


def render_agent_markdown(
    *,
    description: str,
    role: str,
    goal: str,
    model: Optional[str],
    permission: str,
    body: str,
) -> str:
    """Render a ``.praisonai/agents/<name>.md`` document (frontmatter + body).

    The frontmatter is serialised with ``yaml.safe_dump`` so it round-trips
    through ``CustomDefinitionsDiscovery._parse_markdown_frontmatter`` cleanly.
    The permission preset is emitted as ``mode`` (a MODE_RULES key), which the
    runtime resolves via ``resolve_permission_config`` — no parallel grammar.
    """
    frontmatter: dict = {}
    if model:
        frontmatter["model"] = model
    frontmatter["role"] = role
    frontmatter["goal"] = goal

    mode_value = PERMISSION_PRESETS.get(permission, permission)
    if mode_value not in MODE_RULES:
        raise ValueError(
            f"Unknown permission preset: {permission!r}. "
            f"Valid presets: {sorted(PERMISSION_PRESETS)}"
        )
    # ``full`` carries no restrictions; omit it to keep the file minimal while
    # still round-tripping (absence of ``mode`` == full toolset).
    if mode_value != "full":
        frontmatter["mode"] = mode_value

    fm_text = yaml.safe_dump(frontmatter, sort_keys=False, default_flow_style=False)
    body_text = body.strip()
    return f"---\n{fm_text}---\n{body_text}\n"


def write_agent_definition(
    *,
    name: str,
    description: str,
    role: str,
    goal: str,
    model: Optional[str],
    permission: str,
    agents_dir: Path,
    body: Optional[str] = None,
    force: bool = False,
) -> Path:
    """Write ``<agents_dir>/<name>.md`` and return its path.

    Raises ``FileExistsError`` when the target exists and ``force`` is False, so
    the caller can surface a clear message without overwriting user work.
    """
    safe_name = validate_agent_name(name)
    target = agents_dir / f"{safe_name}.md"
    if target.exists() and not force:
        raise FileExistsError(str(target))

    content = render_agent_markdown(
        description=description,
        role=role,
        goal=goal,
        model=model,
        permission=permission,
        body=body if body is not None else _stub_system_prompt(description),
    )
    agents_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target
