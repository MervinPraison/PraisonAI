"""Tests for fail-loud, schema-validated project config resolution."""

import warnings
from pathlib import Path

import pytest

from praisonai.cli.configuration.resolver import (
    ConfigResolver,
    ResolvedConfig,
    validate_config_data,
)


def test_top_level_typo_produces_suggestion():
    msgs = validate_config_data({"modle": "gpt-4o"}, source="cfg.yaml")
    assert len(msgs) == 1
    assert "modle" in msgs[0]
    assert "cfg.yaml" in msgs[0]
    assert "Did you mean 'model'" in msgs[0]


def test_agent_section_typo_produces_suggestion():
    msgs = validate_config_data({"agent": {"temprature": 0.5}}, source="cfg.yaml")
    assert len(msgs) == 1
    assert "temprature" in msgs[0]
    assert "Did you mean 'temperature'" in msgs[0]


def test_clean_nested_config_has_no_warnings():
    data = {"agent": {"model": "gpt-4o-mini"}, "output": {"format": "text"}}
    assert validate_config_data(data) == []


def test_strict_mode_raises_on_typo():
    with pytest.raises(ValueError):
        validate_config_data({"modle": "x"}, strict=True)


def test_nested_scaffold_shape_applies_model():
    """The nested shape `init` scaffolds must be consumed by the resolver."""
    data = {"agent": {"model": "gpt-4o-mini"}, "output": {"format": "text"}}
    rc = ResolvedConfig.from_dict(data)
    assert rc.agent.model == "gpt-4o-mini"
    assert rc.output_format == "text"


def test_resolver_warns_on_typo_but_still_applies_valid_keys(tmp_path):
    cfg_dir = tmp_path / ".praisonai"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        "agent:\n  model: gpt-4o-mini\n  temprature: 0.5\noutput:\n  format: text\n"
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolver = ConfigResolver(cwd=tmp_path)
        cfg = resolver.resolve(force_refresh=True)

    assert cfg.agent.model == "gpt-4o-mini"
    assert any("temprature" in str(w.message) for w in caught)


def test_resolver_strict_mode_raises(tmp_path):
    cfg_dir = tmp_path / ".praisonai"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("agent:\n  temprature: 0.5\n")

    resolver = ConfigResolver(cwd=tmp_path, strict=True)
    with pytest.raises(ValueError):
        resolver.resolve(force_refresh=True)


def test_strict_mode_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_STRICT_CONFIG", "1")
    cfg_dir = tmp_path / ".praisonai"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("modle: gpt-4o\n")

    resolver = ConfigResolver(cwd=tmp_path)
    with pytest.raises(ValueError):
        resolver.resolve(force_refresh=True)


def test_schema_asset_exists_and_is_valid_json():
    import json

    import praisonai.cli.configuration as configuration

    schema_path = Path(configuration.__file__).parent / "config.schema.json"
    assert schema_path.exists()
    schema = json.loads(schema_path.read_text())
    assert schema["type"] == "object"
    assert "agent" in schema["properties"]
    assert "output" in schema["properties"]
