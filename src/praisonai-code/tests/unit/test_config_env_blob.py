"""Tests for issue #3982 — zero-disk config injection via env.

Sibling of the ``PRAISONAI_AUTH_CONTENT`` credential blob. The resolver's
user-config layer can be supplied entirely from the environment:

- ``PRAISONAI_CONFIG_CONTENT`` — an inline JSON/YAML blob parsed in memory as the
  user-config layer; no global/project file is read for that layer.
- ``PRAISONAI_CONFIG`` — an explicit config file path loaded in place of the
  discovered global/project files.

Higher-precedence layers (per-key env vars, CLI flags) and managed policy still
win. Unset → today's file-discovery behaviour is unchanged.
"""

import json

import pytest

from praisonai_code.cli.configuration.resolver import (
    CONFIG_CONTENT_ENV,
    CONFIG_PATH_ENV,
    ConfigResolver,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    # Isolate HOME so no real global config leaks in, and clear the sibling env
    # keys so each test starts from a clean slate.
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    for var in (
        CONFIG_CONTENT_ENV,
        CONFIG_PATH_ENV,
        # Every per-key var consumed by _load_env_config(): a host value would
        # change resolution and could hide a precedence defect or fail a test.
        "MODEL_NAME",
        "OPENAI_MODEL_NAME",
        "PRAISONAI_MODEL",
        "PRAISONAI_PROVIDER",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "PRAISONAI_BASE_URL",
        "PRAISONAI_OUTPUT_FORMAT",
        "PRAISONAI_COLOR",
        "PRAISONAI_VERBOSE",
        "PRAISONAI_QUIET",
        "PRAISONAI_TELEMETRY",
        "PRAISONAI_MANAGED_CONFIG_URL",
        "PRAISONAI_MANAGED_CONFIG_DIR",
    ):
        monkeypatch.delenv(var, raising=False)


def test_unset_is_backward_compatible(tmp_path):
    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()
    assert config.sources == ["defaults"]


def test_inline_yaml_content_supplies_user_config(tmp_path, monkeypatch):
    blob = "agent:\n  model: env-model\npermissions:\n  deny:\n    - 'rm -rf /'\n"
    monkeypatch.setenv(CONFIG_CONTENT_ENV, blob)

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()

    assert config.agent.model == "env-model"
    assert config.permissions == {"deny": ["rm -rf /"]}
    assert any(s.startswith("env-config:") for s in config.sources)


def test_inline_json_content_supplies_user_config(tmp_path, monkeypatch):
    blob = json.dumps({"agent": {"model": "json-model"}, "mcp": {"srv": {"url": "x"}}})
    monkeypatch.setenv(CONFIG_CONTENT_ENV, blob)

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()

    assert config.agent.model == "json-model"
    assert config.mcp == {"srv": {"url": "x"}}


def test_inline_content_replaces_disk_files(tmp_path, monkeypatch):
    # A project config on disk must be ignored when the env blob is set.
    (tmp_path / "praisonai.yaml").write_text("agent:\n  model: disk-model\n")
    monkeypatch.setenv(CONFIG_CONTENT_ENV, "agent:\n  model: env-model\n")

    config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model == "env-model"
    assert not any(s.startswith("project:") for s in config.sources)


def test_explicit_path_loads_user_config(tmp_path, monkeypatch):
    cfg = tmp_path / "custom.yaml"
    cfg.write_text("agent:\n  model: path-model\n")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(cfg))

    config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model == "path-model"
    assert any(str(cfg) in s for s in config.sources)


def test_inline_content_wins_over_explicit_path(tmp_path, monkeypatch):
    cfg = tmp_path / "custom.yaml"
    cfg.write_text("agent:\n  model: path-model\n")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(cfg))
    monkeypatch.setenv(CONFIG_CONTENT_ENV, "agent:\n  model: inline-model\n")

    config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model == "inline-model"


def test_per_key_env_var_still_wins_over_blob(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIG_CONTENT_ENV, "agent:\n  model: blob-model\n")
    monkeypatch.setenv("PRAISONAI_MODEL", "scalar-env-model")

    config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model == "scalar-env-model"


def test_cli_flag_still_wins_over_blob(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIG_CONTENT_ENV, "agent:\n  model: blob-model\n")

    config = ConfigResolver(cwd=tmp_path).resolve(cli_args={"model": "cli-model"})

    assert config.agent.model == "cli-model"


def test_provenance_labels_env_config(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIG_CONTENT_ENV, "agent:\n  model: env-model\n")

    prov = ConfigResolver(cwd=tmp_path).resolve_with_provenance()

    assert prov["agent.model"]["layer"] == "env-config"


def test_invalid_blob_falls_back_gracefully(tmp_path, monkeypatch):
    # A non-mapping / unparseable blob is ignored (with a warning) rather than
    # crashing; discovery then applies as usual.
    (tmp_path / "praisonai.yaml").write_text("agent:\n  model: disk-model\n")
    monkeypatch.setenv(CONFIG_CONTENT_ENV, "]not: [valid")

    with pytest.warns(UserWarning):
        config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model == "disk-model"


def test_missing_explicit_path_falls_back_to_discovery(tmp_path, monkeypatch):
    (tmp_path / "praisonai.yaml").write_text("agent:\n  model: disk-model\n")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "does-not-exist.yaml"))

    with pytest.warns(UserWarning):
        config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model == "disk-model"


def test_empty_inline_mapping_suppresses_discovery(tmp_path, monkeypatch):
    # A valid empty mapping is authoritative: it stands in for the user-config
    # layer, so a disk file must NOT be re-discovered.
    (tmp_path / "praisonai.yaml").write_text("agent:\n  model: disk-model\n")
    monkeypatch.setenv(CONFIG_CONTENT_ENV, "{}")

    config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model is None
    assert not any(s.startswith("project:") for s in config.sources)
    assert any(s.startswith("env-config:") for s in config.sources)


def test_empty_explicit_file_suppresses_discovery(tmp_path, monkeypatch):
    (tmp_path / "praisonai.yaml").write_text("agent:\n  model: disk-model\n")
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(empty))

    config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model is None
    assert not any(s.startswith("project:") for s in config.sources)


def test_non_mapping_explicit_file_falls_back_to_discovery(tmp_path, monkeypatch):
    # A YAML list/scalar body is rejected (would break _source assignment) and
    # discovery applies as usual, with a warning.
    (tmp_path / "praisonai.yaml").write_text("agent:\n  model: disk-model\n")
    bad = tmp_path / "list.yaml"
    bad.write_text("- one\n- two\n")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(bad))

    with pytest.warns(UserWarning):
        config = ConfigResolver(cwd=tmp_path).resolve()

    assert config.agent.model == "disk-model"
