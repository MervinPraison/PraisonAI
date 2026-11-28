"""`config provenance` reports the model a run actually dispatches (#5906)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from praisonai_code.cli.configuration import model_resolver
from praisonai_code.cli.configuration.model_resolver import (
    explain_default_model,
    resolve_default_model,
)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(model_resolver, "_model_state_path", lambda: tmp_path / "model.json")
    monkeypatch.setattr(model_resolver, "_state_dir", lambda: tmp_path)
    for var in ("MODEL_NAME", "OPENAI_MODEL_NAME"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_explicit_wins():
    assert explain_default_model("gpt-x") == ("gpt-x", "explicit")


def test_recent_state_reports_path(_isolated_state):
    model_resolver.set_recent_model("claude-recent")
    model, source = explain_default_model()
    assert model == "claude-recent"
    assert source == f"state:{_isolated_state / 'model.json'}"


def test_env_reports_var(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_NAME", "gpt-env")
    assert explain_default_model() == ("gpt-env", "env:OPENAI_MODEL_NAME")


def test_explain_matches_resolve_and_has_no_side_effects(monkeypatch, _isolated_state):
    monkeypatch.setenv("MODEL_NAME", "gpt-env")
    explain_default_model()
    assert not (_isolated_state / "model.json").exists()
    assert resolve_default_model(notify=False) == explain_default_model()[0]


def _run_provenance(monkeypatch, tmp_path):
    from praisonai_code.cli.commands import config
    from praisonai_code.cli.configuration.resolver import ConfigResolver
    from praisonai_code.cli.output.console import OutputController, OutputMode

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(config, "get_resolver", lambda: ConfigResolver(cwd=tmp_path))
    monkeypatch.setattr(config, "get_output_controller", lambda: OutputController(OutputMode.JSON))
    result = CliRunner().invoke(config.app, ["provenance", "run.model"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_config_provenance_includes_run_model(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISONAI_CONFIG_CONTENT", "{}")
    monkeypatch.setenv("MODEL_NAME", "gpt-env")

    resolved = _run_provenance(monkeypatch, tmp_path)
    # MODEL_NAME feeds agent.model via the config env layer, as `run` sees it.
    assert resolved["key"] == "run.model"
    assert resolved["value"] == "gpt-env"
    assert resolved["layer"] == "environment"


def test_config_provenance_prefers_configured_agent_model(monkeypatch, tmp_path):
    model_resolver.set_recent_model("claude-recent")
    monkeypatch.setenv("PRAISONAI_CONFIG_CONTENT", '{"agent": {"model": "gpt-configured"}}')
    resolved = _run_provenance(monkeypatch, tmp_path)
    assert resolved["key"] == "run.model"
    assert resolved["value"] == "gpt-configured"
    assert resolved["layer"] == "env-config"
