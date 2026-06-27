"""Tests for upward (working-directory inheritance) project config discovery."""

import json
from pathlib import Path

from praisonai.cli.features.config_hierarchy import (
    HierarchicalConfig,
    _MAX_WALK_UP_DEPTH,
)


def _write_project_config(directory: Path, data: dict) -> Path:
    path = directory / ".praison.json"
    path.write_text(json.dumps(data))
    return path


def test_walk_up_finds_config_in_parent_dir(tmp_path: Path):
    """Config in the project root is discovered from a nested subdirectory."""
    _write_project_config(tmp_path, {"model": "gpt-4o-mini"})
    nested = tmp_path / "src" / "deep" / "pkg"
    nested.mkdir(parents=True)

    config = HierarchicalConfig(
        project_dir=str(nested),
        user_config=str(tmp_path / "no-user.json"),
        global_config=str(tmp_path / "no-global.json"),
    )
    merged = config.load()

    assert merged.get("model") == "gpt-4o-mini"


def test_walk_up_disabled_only_checks_cwd(tmp_path: Path):
    """With walk_up=False the legacy cwd-only behaviour is preserved."""
    _write_project_config(tmp_path, {"model": "gpt-4o-mini"})
    nested = tmp_path / "src"
    nested.mkdir()

    config = HierarchicalConfig(
        project_dir=str(nested),
        user_config=str(tmp_path / "no-user.json"),
        global_config=str(tmp_path / "no-global.json"),
        walk_up=False,
    )
    merged = config.load()

    assert "model" not in merged


def test_walk_up_stops_at_git_root(tmp_path: Path):
    """The walk stops at the git root and does not leak parent-project config."""
    outer = tmp_path
    _write_project_config(outer, {"model": "outer-model"})

    project = outer / "project"
    project.mkdir()
    (project / ".git").mkdir()  # git-root boundary marker
    nested = project / "src"
    nested.mkdir()

    config = HierarchicalConfig(
        project_dir=str(nested),
        user_config=str(tmp_path / "no-user.json"),
        global_config=str(tmp_path / "no-global.json"),
    )
    merged = config.load()

    # No config exists at/under the git root, and the outer config must not leak.
    assert "model" not in merged


def test_walk_up_finds_config_at_git_root(tmp_path: Path):
    """A config file living at the git root is still discovered."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    _write_project_config(project, {"model": "root-model"})
    nested = project / "src" / "deep"
    nested.mkdir(parents=True)

    config = HierarchicalConfig(
        project_dir=str(nested),
        user_config=str(tmp_path / "no-user.json"),
        global_config=str(tmp_path / "no-global.json"),
    )
    merged = config.load()

    assert merged.get("model") == "root-model"


def test_walk_up_capped_without_git_boundary(tmp_path: Path):
    """Without a .git boundary the walk is capped and distant ancestors don't leak."""
    _write_project_config(tmp_path, {"model": "distant-ancestor"})

    # Build a chain deeper than the cap so the ancestor config is out of reach.
    nested = tmp_path
    for i in range(_MAX_WALK_UP_DEPTH + 2):
        nested = nested / f"d{i}"
    nested.mkdir(parents=True)

    config = HierarchicalConfig(
        project_dir=str(nested),
        user_config=str(tmp_path / "no-user.json"),
        global_config=str(tmp_path / "no-global.json"),
    )
    merged = config.load()

    assert "model" not in merged


def test_nearest_config_wins_over_ancestor(tmp_path: Path):
    """The closest config to the working directory takes precedence."""
    _write_project_config(tmp_path, {"model": "ancestor"})
    nested = tmp_path / "src"
    nested.mkdir()
    _write_project_config(nested, {"model": "nearest"})

    config = HierarchicalConfig(
        project_dir=str(nested),
        user_config=str(tmp_path / "no-user.json"),
        global_config=str(tmp_path / "no-global.json"),
    )
    merged = config.load()

    assert merged.get("model") == "nearest"
