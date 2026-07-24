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

With ``--generate`` (and a provider credential present), init additionally runs
a short analysis agent that inspects the repository (top-level tree, detected
manifests, README head) and writes a concise, repository-tailored ``AGENTS.md``
at the repo root — immediately discovered by the rules loader on the next run.
Generation is non-destructive (respects ``--force``) and falls back to the
static scaffold when no credential is available or generation fails.
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


def _prescan_repo(root: Path) -> str:
    """Build a cheap, token-bounded snapshot of the repository for analysis.

    Captures the top-level tree, any detected manifest/CI files, and the head of
    the README so the analysis agent has high-signal context without reading the
    whole tree. Kept intentionally small to bound tokens and cost.
    """
    lines: list[str] = []

    try:
        entries = sorted(
            p.name + ("/" if p.is_dir() else "")
            for p in root.iterdir()
            if not p.name.startswith(".git")
        )
    except OSError:
        entries = []
    if entries:
        lines.append("Top-level entries:")
        lines.extend(f"  {e}" for e in entries[:60])

    manifests = (
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
        "package.json", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
        "Makefile", "Dockerfile", "docker-compose.yml", "tox.ini",
    )
    found = [m for m in manifests if (root / m).exists()]
    if found:
        lines.append("")
        lines.append(f"Detected manifests: {', '.join(found)}")

    for readme in ("README.md", "README.rst", "README.txt", "README"):
        rp = root / readme
        if rp.exists():
            try:
                head = rp.read_text(encoding="utf-8", errors="replace")[:1500]
            except OSError:
                break
            lines.append("")
            lines.append(f"{readme} (head):")
            lines.append(head)
            break

    return "\n".join(lines)


def _generate_agents_md(root: Path, model: str) -> str:
    """Run a read-only analysis agent that produces a repo-tailored AGENTS.md.

    Reuses the existing Agent runtime with the current provider credential. Feeds
    it a cheap pre-scan so it can focus on high-signal, project-specific context.
    Raises on any failure so the caller can fall back to the static scaffold.
    """
    from praisonaiagents import Agent

    prescan = _prescan_repo(root)
    prompt = (
        "Analyse the repository described below and write a concise AGENTS.md "
        "capturing only high-signal, project-specific context an AI coding agent "
        "needs on first contact: how to build, test and run; key directories; "
        "conventions; and notable constraints or gotchas. Omit generic "
        "boilerplate. Output ONLY the markdown body, no code fences.\n\n"
        f"Repository snapshot:\n{prescan}"
    )

    agent = Agent(
        instructions=(
            "You produce concise, accurate, project-specific AGENTS.md files. "
            "Prefer concrete commands and paths over generic advice."
        ),
        llm=model,
    )
    result = agent.start(prompt)
    text = str(result).strip()
    if not text:
        raise ValueError("empty generation result")
    return text if text.endswith("\n") else text + "\n"


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
    generate: bool = typer.Option(
        False,
        "--generate",
        "-g",
        help="Analyse the repository and generate a tailored AGENTS.md "
             "(requires a provider credential; falls back to the static scaffold)",
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

    # Optional agent-driven generation of a repository-tailored AGENTS.md.
    # Non-destructive (respects --force) and degrades gracefully: when no
    # provider credential is present or generation fails, the static scaffold
    # above remains the guaranteed result. The file lands at the repo root so
    # rules_manager discovers it on the next run.
    if generate:
        agents_path = base.parent / "AGENTS.md"
        if agents_path.exists() and not force:
            output.print_warning(
                f"Skipped generation (already exists, use --force): {agents_path}"
            )
        elif not provider_detected:
            output.print_warning(
                "Skipped --generate: no provider credential detected. "
                "Falling back to the static scaffold above."
            )
        else:
            try:
                content = _generate_agents_md(base.parent, scaffold_model)
            except Exception as exc:  # noqa: BLE001 - fall back, never fail init
                output.print_warning(
                    f"Generation failed ({exc}); kept the static scaffold above."
                )
            else:
                try:
                    agents_path.write_text(content, encoding="utf-8")
                except OSError as exc:
                    output.print_error(
                        f"Failed to write {agents_path}: {exc.strerror or exc}",
                        remediation="Check write permissions and free disk space.",
                    )
                    raise typer.Exit(code=1)
                output.print_success(f"Generated {agents_path}")

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
