"""Unit tests for deep-merged config resolution across global + project files.

Covers the fix for first-file-wins: a project config must selectively override
the user-global config instead of shadowing it entirely.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from praisonaiagents.config import loader


@pytest.fixture(autouse=True)
def _clear_cache():
    loader.clear_config_cache()
    yield
    loader.clear_config_cache()


def _write_yaml(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_deep_merge_recurses_dicts_and_replaces_scalars():
    base = {"defaults": {"model": "global", "memory": {"backend": "sqlite"}}}
    override = {"defaults": {"model": "project", "memory": {"provider": "x"}}}
    merged = loader._deep_merge(base, override)
    assert merged == {
        "defaults": {
            "model": "project",
            "memory": {"backend": "sqlite", "provider": "x"},
        }
    }
    # Inputs untouched.
    assert base["defaults"]["model"] == "global"


def test_deep_merge_lists_replace():
    base = {"plugins": {"enabled": ["a", "b"]}}
    override = {"plugins": {"enabled": ["c"]}}
    assert loader._deep_merge(base, override) == {"plugins": {"enabled": ["c"]}}


def _run_with_dirs(tmp_path, monkeypatch, home_dir, cwd_dir):
    monkeypatch.setenv("PRAISONAI_HOME", str(home_dir))
    monkeypatch.chdir(cwd_dir)
    loader.clear_config_cache()
    from praisonaiagents import paths
    paths._clear_cache()


def test_global_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _write_yaml(home / "config.yaml", "defaults:\n  model: global-model\n")
    project = tmp_path / "project"
    project.mkdir()
    _run_with_dirs(tmp_path, monkeypatch, home, project)

    raw = loader._load_config()
    assert raw["defaults"]["model"] == "global-model"


def test_project_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    _write_yaml(project / ".praisonai" / "config.yaml", "defaults:\n  model: proj-model\n")
    _run_with_dirs(tmp_path, monkeypatch, home, project)

    raw = loader._load_config()
    assert raw["defaults"]["model"] == "proj-model"


def test_both_present_project_overrides_with_global_fallthrough(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _write_yaml(
        home / "config.yaml",
        "defaults:\n  model: global-model\n  base_url: https://global\n",
    )
    project = tmp_path / "project"
    _write_yaml(
        project / ".praisonai" / "config.yaml",
        "defaults:\n  model: project-model\n",
    )
    _run_with_dirs(tmp_path, monkeypatch, home, project)

    raw = loader._load_config()
    # Project overrides model; global base_url falls through.
    assert raw["defaults"]["model"] == "project-model"
    assert raw["defaults"]["base_url"] == "https://global"


def test_ancestor_directory_discovery_nearest_wins(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "workspace"
    _write_yaml(
        root / ".praisonai" / "config.yaml",
        "defaults:\n  model: root-model\n  base_url: https://root\n",
    )
    nested = root / "sub" / "deep"
    _write_yaml(
        nested / ".praisonai" / "config.yaml",
        "defaults:\n  model: nested-model\n",
    )
    _run_with_dirs(tmp_path, monkeypatch, home, nested)

    raw = loader._load_config()
    # Nearest (nested) wins for model; ancestor base_url falls through.
    assert raw["defaults"]["model"] == "nested-model"
    assert raw["defaults"]["base_url"] == "https://root"


def test_single_file_fast_path_matches_direct_parse(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    cfg = project / ".praisonai" / "config.yaml"
    _write_yaml(cfg, "defaults:\n  model: only-model\n")
    _run_with_dirs(tmp_path, monkeypatch, home, project)

    files = loader._discover_config_files()
    assert files == [cfg]
    assert loader._load_config() == loader._parse_config_file(cfg)
