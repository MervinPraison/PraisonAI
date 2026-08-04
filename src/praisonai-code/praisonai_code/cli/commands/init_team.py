"""Multi-agent project scaffold for `praisonai init team <name>`.

Generates a runnable, YAML-first ``AgentTeam`` starter project:

    <name>/
      .env.example              # required provider credential(s)
      .gitignore                # .env, __pycache__, .venv
      README.md                 # edit-YAML-then-run quickstart
      pyproject.toml            # optional (skip with --no-pyproject)
      <slug>/
        __init__.py
        main.py                 # run() entry point
        team.py                 # build_team() factory over the SDK
        config/
          agents.yaml           # role/goal/backstory per agent + process
          tasks.yaml            # description/expected_output/agent/context

The package sits at the project root (flat layout) so ``python -m <slug>.main``
runs out-of-the-box from the project directory without an install step.

The generated ``team.py`` consumes the existing ``AgentTeam`` / ``Agent`` /
``Task`` runtime from ``praisonaiagents`` — no new SDK surface is introduced.
Templates are ASCII-only so they render safely on Windows (cp1252) consoles.
"""

from __future__ import annotations

import keyword
import re
from pathlib import Path

import typer

from ..output.console import get_output_controller

VALID_PROCESSES = ("sequential", "hierarchical")


def slugify(name: str) -> str:
    """Turn a project name into a valid Python package identifier.

    ``my-research-crew`` -> ``my_research_crew``. Collapses any run of
    non-alphanumeric characters to a single underscore, lowercases, and
    prefixes an underscore if the result would start with a digit.
    """
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    if not slug:
        raise ValueError(f"Cannot derive a package name from {name!r}")
    if slug[0].isdigit():
        slug = f"_{slug}"
    if keyword.iskeyword(slug) or keyword.issoftkeyword(slug):
        slug = f"{slug}_team"
    return slug


def _agents_yaml(process: str, agent_count: int) -> str:
    base = [
        (
            "researcher",
            "Research Analyst",
            "Senior Research Analyst",
            "Find accurate, up-to-date information on the assigned topic",
            "You excel at synthesising sources into concise research briefs.",
        ),
        (
            "writer",
            "Content Writer",
            "Technical Writer",
            "Turn research into clear, engaging prose",
            "You transform notes into polished, well-structured articles.",
        ),
        (
            "reviewer",
            "Editor",
            "Senior Editor",
            "Ensure the final output is accurate and well written",
            "You catch errors and improve clarity, tone, and structure.",
        ),
    ]
    lines = [f"process: {process}", "", "agents:"]
    for i in range(agent_count):
        key, name, role, goal, backstory = base[i % len(base)]
        if i >= len(base):
            key = f"{key}_{i + 1}"
        lines += [
            f"  {key}:",
            f"    name: {name}",
            f"    role: {role}",
            f"    goal: {goal}",
            "    backstory: >",
            f"      {backstory}",
        ]
    return "\n".join(lines) + "\n"


def _tasks_yaml(agent_count: int) -> str:
    lines = ["tasks:"]
    lines += [
        "  - description: >",
        "      Research the latest developments in {{topic}}.",
        "      Focus on practical applications and key players.",
        "    expected_output: >",
        "      A bullet-point research brief with at least 5 findings and 3 sources.",
        "    agent: researcher",
    ]
    if agent_count >= 2:
        lines += [
            "  - description: >",
            "      Using the research brief, write a 300-word summary article about {{topic}}.",
            "    expected_output: >",
            "      A markdown article with title, intro, body, and conclusion.",
            "    agent: writer",
            "    context:",
            "      - Research the latest developments in {{topic}}.",
        ]
    return "\n".join(lines) + "\n"


TEAM_PY = '''\
"""AgentTeam assembly - edit config/agents.yaml and config/tasks.yaml."""

from pathlib import Path

import yaml
from praisonaiagents import Agent, AgentTeam, Task

CONFIG_DIR = Path(__file__).parent / "config"


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_team(variables: dict | None = None) -> AgentTeam:
    agents_cfg = load_yaml("agents.yaml")
    tasks_cfg = load_yaml("tasks.yaml")

    agents = {
        key: Agent(**spec)
        for key, spec in agents_cfg["agents"].items()
    }

    tasks = []
    for spec in tasks_cfg["tasks"]:
        spec = dict(spec)
        agent_key = spec.pop("agent", None)
        tasks.append(Task(agent=agents.get(agent_key), **spec))

    return AgentTeam(
        agents=list(agents.values()),
        tasks=tasks,
        process=agents_cfg.get("process", "sequential"),
        variables=variables or {},
    )
'''


def _main_py(slug: str) -> str:
    return (
        f'"""Entry point for {slug} - generated by praisonai init team."""\n\n'
        f"from {slug}.team import build_team\n\n\n"
        "def run():\n"
        "    # `variables` fill the double-brace placeholders in the YAML config.\n"
        '    team = build_team(variables={"topic": "AI agents"})\n'
        "    result = team.start()\n"
        "    print(result)\n\n\n"
        'if __name__ == "__main__":\n'
        "    run()\n"
    )


def _readme(name: str, slug: str, process: str) -> str:
    return (
        f"# {name}\n\n"
        "A multi-agent PraisonAI team project generated by `praisonai init team`.\n\n"
        "## Prerequisites\n\n"
        "- Python 3.10+\n"
        "- A provider API key (e.g. `OPENAI_API_KEY`)\n\n"
        "## Setup\n\n"
        "```bash\n"
        "cp .env.example .env   # then edit and add your key\n"
        "pip install praisonaiagents pyyaml\n"
        "```\n\n"
        "## Customise\n\n"
        f"- Edit `{slug}/config/agents.yaml` to change roles, goals and backstories.\n"
        f"- Edit `{slug}/config/tasks.yaml` to change task descriptions and flow.\n\n"
        "## Run\n\n"
        "```bash\n"
        f"python -m {slug}.main\n"
        "```\n\n"
        "## Process types\n\n"
        f"This project uses the `{process}` process. Set `process:` in `agents.yaml` to\n"
        "`sequential` (tasks run in order) or `hierarchical` (a manager delegates).\n\n"
        "## Next steps\n\n"
        "- Add tools, memory or guardrails via the AgentTeam / Agent parameters.\n"
    )


ENV_EXAMPLE = (
    "# Provider credential(s) for the AgentTeam runtime.\n"
    "# Set at least one and load it (e.g. via python-dotenv or your shell).\n"
    "OPENAI_API_KEY=\n"
    "# ANTHROPIC_API_KEY=\n"
    "# GEMINI_API_KEY=\n"
)

GITIGNORE = ".env\n__pycache__/\n*.pyc\n.venv/\n"


def _pyproject(name: str, slug: str) -> str:
    return (
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        f'description = "A PraisonAI multi-agent team project"\n'
        'requires-python = ">=3.10"\n'
        "dependencies = [\n"
        '    "praisonaiagents",\n'
        '    "pyyaml",\n'
        "]\n\n"
        "[build-system]\n"
        'requires = ["setuptools>=61.0"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[tool.setuptools.packages.find]\n"
        f'include = ["{slug}*"]\n'
    )


def _write(path: Path, content: str, force: bool, written: list, skipped: list) -> None:
    if path.exists() and not force:
        skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    written.append(path)


def scaffold_team_project(
    name: str,
    *,
    process: str = "sequential",
    agent_count: int = 2,
    force: bool = False,
    pyproject: bool = True,
) -> Path:
    """Generate the multi-agent team project tree under ``<cwd>/<name>``.

    Returns the project root path. Raises ``typer.Exit`` on invalid input or a
    pre-existing directory without ``force``.
    """
    output = get_output_controller()

    if process not in VALID_PROCESSES:
        output.print_error(
            f"Invalid --process {process!r}.",
            remediation=f"Choose one of: {', '.join(VALID_PROCESSES)}.",
        )
        raise typer.Exit(code=1)
    if agent_count < 1:
        output.print_error("--agents must be at least 1.")
        raise typer.Exit(code=1)

    try:
        slug = slugify(name)
    except ValueError as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=1)

    root = Path.cwd() / name
    if root.exists() and not force:
        output.print_error(
            f"Directory already exists: {root}",
            remediation="Use --force to overwrite existing files.",
        )
        raise typer.Exit(code=1)

    pkg = root / slug
    config = pkg / "config"

    targets = [
        (root / ".env.example", ENV_EXAMPLE),
        (root / ".gitignore", GITIGNORE),
        (root / "README.md", _readme(name, slug, process)),
        (pkg / "__init__.py", '__version__ = "0.1.0"\n'),
        (pkg / "main.py", _main_py(slug)),
        (pkg / "team.py", TEAM_PY),
        (config / "agents.yaml", _agents_yaml(process, agent_count)),
        (config / "tasks.yaml", _tasks_yaml(agent_count)),
    ]
    if pyproject:
        targets.append((root / "pyproject.toml", _pyproject(name, slug)))

    written: list[Path] = []
    skipped: list[Path] = []
    try:
        for path, content in targets:
            _write(path, content, force, written, skipped)
    except OSError as exc:
        output.print_error(
            f"Failed to write {exc.filename or root}: {exc.strerror or exc}",
            remediation="Check write permissions and free disk space.",
        )
        raise typer.Exit(code=1)

    for path in written:
        output.print_info(f"Created {path}")
    for path in skipped:
        output.print_warning(f"Skipped (already exists, use --force): {path}")

    if written:
        output.print_success(f"Initialised team project {root}")
        output.print_info("Next steps:")
        output.print_info(f"  cd {name}")
        output.print_info("  cp .env.example .env   # add your API key")
        output.print_info(f"  python -m {slug}.main")
    return root
