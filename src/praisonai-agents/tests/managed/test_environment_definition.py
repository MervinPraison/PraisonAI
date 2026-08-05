"""Tests for the repo-committed environment definition loader.

Covers the minimal, lightweight joint added for the
``.praisonai/environment.yaml`` concept: a loader that maps the file onto the
existing ``ComputeConfig`` schema, plus the new ``setup`` field.
"""

import os

import pytest

from praisonaiagents.managed.protocols import (
    ComputeConfig,
    definition_hash,
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

    @pytest.mark.parametrize(
        "body, needle",
        [
            ("packages:\n  - just-a-list\n", "packages"),
            ("env: not-a-mapping\n", "env"),
            ("setup:\n  nested: 1\n", "setup"),
            ("image:\n  a: b\n", "image"),
            ("resources: 42\n", "resources"),
        ],
    )
    def test_malformed_nested_shapes_raise_valueerror(self, tmp_path, body, needle):
        path = _write_env(str(tmp_path), body)
        with pytest.raises(ValueError) as exc:
            load_environment_definition(path)
        assert needle in str(exc.value)
        assert path in str(exc.value)


class TestDefinitionHash:
    def test_stable_across_key_and_list_reordering(self):
        a = ComputeConfig(
            image="python:3.12-slim",
            packages={"pip": ["requests", "pytest"], "apt": ["git"]},
            setup=["pip install -e ."],
        )
        b = ComputeConfig(
            image="python:3.12-slim",
            packages={"apt": ["git"], "pip": ["pytest", "requests"]},
            setup=["pip install -e ."],
        )
        assert definition_hash(a) == definition_hash(b)

    def test_changing_a_package_changes_hash(self):
        a = ComputeConfig(packages={"pip": ["requests"]})
        b = ComputeConfig(packages={"pip": ["requests", "numpy"]})
        assert definition_hash(a) != definition_hash(b)

    def test_changing_setup_changes_hash(self):
        a = ComputeConfig(setup=["make install"])
        b = ComputeConfig(setup=["make build"])
        assert definition_hash(a) != definition_hash(b)

    def test_env_values_excluded_from_hash(self):
        a = ComputeConfig(env={"TOKEN": "secret-1"})
        b = ComputeConfig(env={"TOKEN": "secret-2"})
        assert definition_hash(a) == definition_hash(b)

    def test_env_names_included_in_hash(self):
        a = ComputeConfig(env={"TOKEN": "x"})
        b = ComputeConfig(env={"OTHER": "x"})
        assert definition_hash(a) != definition_hash(b)

    def test_hash_is_short_hex(self):
        h = definition_hash(ComputeConfig())
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)


class TestRefreshAndCaptureKeys:
    def test_refresh_carried_in_metadata(self, tmp_path):
        path = _write_env(str(tmp_path), "refresh: pip install -e .\n")
        cfg = load_environment_definition(path)
        assert cfg.metadata["refresh"] == ["pip install -e ."]

    def test_capture_flag_carried_in_metadata(self, tmp_path):
        path = _write_env(str(tmp_path), "capture: true\n")
        cfg = load_environment_definition(path)
        assert cfg.metadata["capture"] is True

    def test_refresh_bad_shape_raises(self, tmp_path):
        path = _write_env(str(tmp_path), "refresh:\n  nested: 1\n")
        with pytest.raises(ValueError) as exc:
            load_environment_definition(path)
        assert "refresh" in str(exc.value)


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
