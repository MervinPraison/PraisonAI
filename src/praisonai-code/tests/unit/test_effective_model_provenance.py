"""`config provenance` reports the model a run actually dispatches (#5906)."""

import json

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


def test_config_provenance_includes_run_model(monkeypatch):
    from praisonai_code.cli.commands.config import app

    monkeypatch.setenv("MODEL_NAME", "gpt-env")
    result = CliRunner().invoke(app, ["provenance", "run.model"])
    assert result.exit_code == 0, result.output
    assert "gpt-env" in result.output
    assert "env:MODEL_NAME" in result.output
