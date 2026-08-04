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


class TestScaffold:
    def test_creates_expected_files(self, tmp_path):
        root = _run(tmp_path, "demo-crew")
        pkg = root / "src" / "demo_crew"
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
        pkg = root / "src" / "demo_crew"
        ast.parse((pkg / "main.py").read_text())
        ast.parse((pkg / "team.py").read_text())

    def test_yaml_loads(self, tmp_path):
        root = _run(tmp_path, "demo-crew")
        cfg = root / "src" / "demo_crew" / "config"
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
            (root / "src" / "demo_crew" / "config" / "agents.yaml").read_text()
        )
        assert agents["process"] == "hierarchical"

    def test_invalid_process_exits(self, tmp_path):
        with pytest.raises(typer.Exit):
            _run(tmp_path, "demo-crew", process="bogus")

    def test_agents_count(self, tmp_path):
        root = _run(tmp_path, "demo-crew", agent_count=3)
        agents = yaml.safe_load(
            (root / "src" / "demo_crew" / "config" / "agents.yaml").read_text()
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
