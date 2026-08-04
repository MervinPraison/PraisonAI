"""Tests for the repo-committed environment definition loader.

Covers the minimal, lightweight joint added for the
``.praisonai/environment.yaml`` concept: a loader that maps the file onto the
existing ``ComputeConfig`` schema, plus the new ``setup`` field.
"""

import os

import pytest

from praisonaiagents.managed.protocols import (
    ComputeConfig,
    find_environment_definition,
    load_environment_definition,
)


def _write_env(dir_path, body):
    env_dir = os.path.join(dir_path, ".praisonai")
    os.makedirs(env_dir, exist_ok=True)
    path = os.path.join(env_dir, "environment.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


class TestComputeConfigSetupField:
    def test_setup_defaults_empty(self):
        assert ComputeConfig().setup == []

    def test_setup_assignable(self):
        cfg = ComputeConfig(setup=["pip install -e ."])
        assert cfg.setup == ["pip install -e ."]


class TestLoadEnvironmentDefinition:
    def test_full_yaml_round_trips(self, tmp_path):
        path = _write_env(
            str(tmp_path),
            """
image: python:3.12-slim
packages:
  pip: [pytest, requests]
  apt: [git, curl]
setup:
  - pip install -e .
env:
  PYTHONPATH: src
resources: {cpu: 2, memory_mb: 2048}
network: allowlist
backend: docker
""",
        )
        cfg = load_environment_definition(path)
        assert cfg.image == "python:3.12-slim"
        assert cfg.packages == {"pip": ["pytest", "requests"], "apt": ["git", "curl"]}
        assert cfg.setup == ["pip install -e ."]
        assert cfg.env == {"PYTHONPATH": "src"}
        assert cfg.cpu == 2
        assert cfg.memory_mb == 2048
        assert cfg.networking == {"type": "allowlist"}
        assert cfg.metadata["backend"] == "docker"

    def test_setup_scalar_normalised_to_list(self, tmp_path):
        path = _write_env(str(tmp_path), "setup: make install\n")
        cfg = load_environment_definition(path)
        assert cfg.setup == ["make install"]

    def test_unknown_key_errors_with_path(self, tmp_path):
        path = _write_env(str(tmp_path), "imagz: python:3.12\n")
        with pytest.raises(ValueError) as exc:
            load_environment_definition(path)
        assert "imagz" in str(exc.value)
        assert path in str(exc.value)

    def test_non_mapping_errors(self, tmp_path):
        path = _write_env(str(tmp_path), "- just\n- a\n- list\n")
        with pytest.raises(ValueError):
            load_environment_definition(path)

    def test_empty_file_yields_defaults(self, tmp_path):
        path = _write_env(str(tmp_path), "")
        cfg = load_environment_definition(path)
        assert cfg.image == ComputeConfig().image
        assert cfg.setup == []


class TestDiscovery:
    def test_no_file_returns_none(self, tmp_path):
        assert find_environment_definition(str(tmp_path)) is None

    def test_discovery_walks_up(self, tmp_path):
        _write_env(str(tmp_path), "image: python:3.11\n")
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        found = find_environment_definition(str(nested))
        assert found is not None
        cfg = load_environment_definition(found)
        assert cfg.image == "python:3.11"

    def test_load_with_none_and_no_file_is_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert load_environment_definition() is None
