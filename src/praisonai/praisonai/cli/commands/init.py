"""
Project scaffolding command for the `.praisonai/` convention.

`praisonai init` creates a working starter project structure that the existing
`CustomDefinitionsDiscovery` loader already understands:

    .praisonai/
      config.yaml            # sensible defaults (model, output mode)
      agents/assistant.md    # working starter agent (frontmatter + body)
      commands/review.md     # working starter command using $ARGUMENTS / @file

The scaffolded files are immediately discoverable and runnable via
`praisonai agent run assistant ...` and `praisonai command run review ...`.
"""

from pathlib import Path

import typer

from ..output.console import get_output_controller
from ..utils.project import get_git_root

app = typer.Typer(help="Initialise the .praisonai/ project convention")


STARTER_CONFIG = """\
# PraisonAI project configuration
# Defaults applied to scaffolded agents and commands.
model: gpt-4o-mini
output: text
"""

STARTER_AGENT_MD = """\
---
model: gpt-4o-mini
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

    targets = [
        (base / "config.yaml", STARTER_CONFIG),
        (base / "agents" / "assistant.md", STARTER_AGENT_MD),
        (base / "commands" / "review.md", STARTER_COMMAND_MD),
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
        output.print_info("You can now run:")
        output.print_info('  praisonai agent run assistant "hello"')
        output.print_info('  praisonai command run review "src/foo.py"')
    elif skipped:
        output.print_info(
            "Nothing to do — .praisonai/ already initialised. Use --force to overwrite."
        )
