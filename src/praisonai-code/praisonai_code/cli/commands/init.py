"""
Project scaffolding command for the `.praisonai/` convention.

`praisonai init` creates a working starter project structure that the existing
`CustomDefinitionsDiscovery` loader already understands:

    .praisonai/
      config.yaml            # sensible defaults (model, output mode)
      agents/assistant.md    # working starter agent (frontmatter + body)
      commands/review.md     # working starter command using $ARGUMENTS / @file
      tools/example.py       # commented @tool example (opt-in to load)

The scaffolded files are immediately discoverable and runnable via
`praisonai run --agent assistant ...` and `praisonai run --command review ...`.
Tools dropped in `.praisonai/tools/*.py` execute local code, so loading them is
opt-in: pass `--allow-local-tools` (or set `PRAISONAI_ALLOW_LOCAL_TOOLS=true`)
on `run` to enable them. Without the opt-in, `run` prints a one-line hint when
tool files are present so the enable step is never a silent no-op.
"""

from pathlib import Path

import typer

from ..output.console import get_output_controller
from ..utils.project import get_git_root

app = typer.Typer(help="Initialise the .praisonai/ project convention")


STARTER_CONFIG = """\
# yaml-language-server: $schema=https://raw.githubusercontent.com/MervinPraison/PraisonAI/main/src/praisonai/praisonai/cli/configuration/config.schema.json
# PraisonAI project configuration
# Defaults applied to scaffolded agents and commands.
# Sections are nested exactly as the resolver consumes them.
agent:
  model: {model}
output:
  format: text
"""

STARTER_AGENT_MD = """\
---
model: {model}
role: Assistant
goal: Help the user accomplish tasks accurately and concisely
instructions: |
  You are a helpful assistant. Answer clearly and concisely.
  When you are unsure, say so instead of guessing.
---
You are a helpful assistant for this project.

Be concise, accurate, and practical. Prefer actionable answers.
"""

STARTER_COMMAND_MD = """\
---
description: Review the provided code or file and suggest improvements
---
Review the following and suggest concrete improvements
(correctness, readability, performance, and security):

$ARGUMENTS

If a file path is provided, here are its contents:

@$ARGUMENTS
"""

STARTER_TOOL_PY = '''\
"""Project-local tools for this .praisonai/ project.

Every public callable in this directory is made available to the agent on
`praisonai run` — no --tools flag required. Decorate a function with @tool for
a rich schema, or just define a plain function.

Loading executes this file, so it is OPT-IN. Enable it on `run` with either:

    praisonai run --allow-local-tools "use the greet tool to greet Ada"
    # or: export PRAISONAI_ALLOW_LOCAL_TOOLS=true

Without the opt-in, `run` prints a one-line hint (it never silently skips).
Uncomment the example below to try it.
"""

# from praisonaiagents import tool
#
#
# @tool
# def greet(name: str) -> str:
#     """Return a friendly greeting for the given name."""
#     return f"Hello, {name}!"
'''


def _any_provider_credential() -> bool:
    """Return True if any supported provider credential is present in env."""
    import os

    # Derive the credential keys from the single source of truth so this
    # detection never drifts from default_model_for_available_provider().
    try:
        from praisonai_code.llm.env import _PROVIDER_DEFAULTS
        known_keys = tuple(key_var for key_var, _ in _PROVIDER_DEFAULTS)
    except Exception:
        known_keys = (
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
            "GEMINI_API_KEY", "GROQ_API_KEY", "COHERE_API_KEY",
            "OLLAMA_HOST",
        )
    return any(os.environ.get(k) for k in known_keys)


def _write(path: Path, content: str, force: bool) -> bool:
    """Write content to path. Returns True if written, False if skipped."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


@app.callback(invoke_without_command=True)
def init(
    ctx: typer.Context,
    global_: bool = typer.Option(
        False,
        "--global",
        help="Scaffold the user-global ~/.praisonai/ directory instead of the project",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing files",
    ),
) -> None:
    """Scaffold the .praisonai/ project convention (config + starter agent + command)."""
    # Allow subcommands (none currently) to run without scaffolding.
    if ctx.invoked_subcommand is not None:
        return

    output = get_output_controller()

    if global_:
        base = Path.home() / ".praisonai"
    else:
        base = (get_git_root() or Path.cwd()) / ".praisonai"

    # Scaffold the default model that matches the user's detected provider
    # credential via the shared resolver, so init stays consistent with `run`,
    # the bare TUI, and `setup`. Falls back to the terminal default when none is
    # detected. persist/notify are disabled: scaffolding must not record a
    # recency choice or emit the run-time inference notice.
    try:
        from ..configuration.model_resolver import resolve_default_model
        detected_model = resolve_default_model(None, persist=False, notify=False)
    except Exception:
        from praisonai_code.llm.env import DEFAULT_FALLBACK_MODEL
        detected_model = DEFAULT_FALLBACK_MODEL

    provider_detected = _any_provider_credential()
    scaffold_model = detected_model

    targets = [
        (base / "config.yaml", STARTER_CONFIG.format(model=scaffold_model)),
        (base / "agents" / "assistant.md", STARTER_AGENT_MD.format(model=scaffold_model)),
        (base / "commands" / "review.md", STARTER_COMMAND_MD),
        (base / "tools" / "example.py", STARTER_TOOL_PY),
    ]

    written = []
    skipped = []
    try:
        for path, content in targets:
            if _write(path, content, force):
                written.append(path)
            else:
                skipped.append(path)
    except OSError as exc:
        output.print_error(
            f"Failed to write {exc.filename or base}: {exc.strerror or exc}",
            remediation="Check that you have write permissions and free disk space.",
        )
        raise typer.Exit(code=1)

    for path in written:
        output.print_info(f"Created {path}")
    for path in skipped:
        output.print_warning(f"Skipped (already exists, use --force): {path}")

    if written:
        output.print_success(f"Initialised {base}")
        if provider_detected:
            output.print_info(f"Detected provider — scaffolded model: {scaffold_model}")
        else:
            output.print_warning(
                f"No provider credential detected — scaffolded placeholder model "
                f"'{scaffold_model}'. Set one of OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                f"GEMINI_API_KEY/GOOGLE_API_KEY, GROQ_API_KEY, COHERE_API_KEY or "
                f"OLLAMA_HOST, then update the model if needed."
            )
        output.print_info("You can now run:")
        output.print_info('  praisonai run --agent assistant "hello"')
        output.print_info('  praisonai run --command review "src/foo.py"')
        output.print_info(
            "Project-local tools are opt-in — add --allow-local-tools "
            "(or set PRAISONAI_ALLOW_LOCAL_TOOLS=true) to load .praisonai/tools/*.py."
        )
    elif skipped:
        output.print_info(
            "Nothing to do — .praisonai/ already initialised. Use --force to overwrite."
        )
