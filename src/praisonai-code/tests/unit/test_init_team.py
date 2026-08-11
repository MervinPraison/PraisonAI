"""Tests for `praisonai init team <name>` multi-agent scaffold.

Covers the generator added alongside the single-agent `.praisonai/` init:

- Slugification of project names into valid Python packages.
- The full file tree is created and importable/parseable.
- `--force` overwrite guard.
- `--process hierarchical` and `--agents N` reflected in generated YAML.
- Templates are ASCII-only (Windows cp1252 safe).
"""

import ast
import os

import pytest
import typer
import yaml

from praisonai_code.cli.commands import init_team as it


def _run(tmp_path, name, **kwargs):
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return it.scaffold_team_project(name, **kwargs)
    finally:
        os.chdir(cwd)


class TestSlugify:
    def test_dashes_to_underscores(self):
        assert it.slugify("my-research-crew") == "my_research_crew"

    def test_mixed_and_spaces(self):
        assert it.slugify("My Cool Crew!") == "my_cool_crew"

    def test_leading_digit_prefixed(self):
        assert it.slugify("123crew") == "_123crew"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            it.slugify("---")

    def test_reserved_keyword_suffixed(self):
        # A name that slugifies to a Python keyword must not produce an
        # invalid `from class.team import ...` import.
        assert it.slugify("class") == "class_team"
        assert it.slugify("import") == "import_team"


class TestScaffold:
    def test_creates_expected_files(self, tmp_path):
        root = _run(tmp_path, "demo-crew")
        pkg = root / "demo_crew"
        assert (root / ".env.example").exists()
        assert (root / ".gitignore").exists()
        assert (root / "README.md").exists()
        assert (root / "pyproject.toml").exists()
        assert (pkg / "__init__.py").exists()
        assert (pkg / "main.py").exists()
        assert (pkg / "team.py").exists()
        assert (pkg / "config" / "agents.yaml").exists()
        assert (pkg / "config" / "tasks.yaml").exists()

    def test_generated_python_parses(self, tmp_path):
        root = _run(tmp_path, "demo-crew")
        pkg = root / "demo_crew"
        ast.parse((pkg / "main.py").read_text())
        ast.parse((pkg / "team.py").read_text())

    def test_documented_run_path_importable(self, tmp_path):
        # Flat layout: `python -m <slug>.main` must resolve from the project
        # root, so `<slug>/main.py` (not `src/<slug>/main.py`) must exist and
        # import the package by its top-level name.
        root = _run(tmp_path, "demo-crew")
        main = (root / "demo_crew" / "main.py").read_text()
        assert "from demo_crew.team import build_team" in main
        assert not (root / "src").exists()

    def test_topic_uses_double_brace_and_variables(self, tmp_path):
        # The SDK substitutes {{key}} from AgentTeam(variables=...); single
        # braces and start(inputs=...) would silently drop the topic.
        root = _run(tmp_path, "demo-crew")
        pkg = root / "demo_crew"
        tasks = (pkg / "config" / "tasks.yaml").read_text()
        assert "{{topic}}" in tasks
        assert "{topic}" not in tasks.replace("{{topic}}", "")
        team = (pkg / "team.py").read_text()
        assert "variables=variables" in team
        main = (pkg / "main.py").read_text()
        assert 'build_team(variables={"topic"' in main
        assert "inputs=" not in main

    def test_yaml_loads(self, tmp_path):
        root = _run(tmp_path, "demo-crew")
        cfg = root / "demo_crew" / "config"
        agents = yaml.safe_load((cfg / "agents.yaml").read_text())
        tasks = yaml.safe_load((cfg / "tasks.yaml").read_text())
        assert agents["process"] == "sequential"
        assert "researcher" in agents["agents"]
        assert len(tasks["tasks"]) >= 1

    def test_no_pyproject_flag(self, tmp_path):
        root = _run(tmp_path, "demo-crew", pyproject=False)
        assert not (root / "pyproject.toml").exists()

    def test_process_hierarchical(self, tmp_path):
        root = _run(tmp_path, "demo-crew", process="hierarchical")
        agents = yaml.safe_load(
            (root / "demo_crew" / "config" / "agents.yaml").read_text()
        )
        assert agents["process"] == "hierarchical"

    def test_invalid_process_exits(self, tmp_path):
        with pytest.raises(typer.Exit):
            _run(tmp_path, "demo-crew", process="bogus")

    def test_agents_count(self, tmp_path):
        root = _run(tmp_path, "demo-crew", agent_count=3)
        agents = yaml.safe_load(
            (root / "demo_crew" / "config" / "agents.yaml").read_text()
        )
        assert len(agents["agents"]) == 3

    def test_force_guard(self, tmp_path):
        _run(tmp_path, "demo-crew")
        with pytest.raises(typer.Exit):
            _run(tmp_path, "demo-crew")

    def test_force_overwrites(self, tmp_path):
        _run(tmp_path, "demo-crew")
        root = _run(tmp_path, "demo-crew", force=True)
        assert (root / "README.md").exists()

    def test_ascii_only_templates(self, tmp_path):
        root = _run(tmp_path, "demo-crew")
        for path in root.rglob("*"):
            if path.is_file():
                data = path.read_text(encoding="utf-8")
                data.encode("ascii")  # raises if any non-ASCII slips in
