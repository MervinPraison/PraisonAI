"""``praisonai ship`` (S-6): off switch via PRAISONAI_DISABLE_SHIP and config key."""

import pytest
from typer.testing import CliRunner

from praisonai_code.cli.commands import ship as ship_cmd
from praisonai_code.cli.configuration.loader import ConfigLoader
from praisonai_code.cli.configuration.schema import ConfigSchema, ShipConfig
from praisonai_code.ship import is_ship_disabled
from praisonai_code.ship import flow


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PRAISONAI_DISABLE_SHIP", raising=False)
    monkeypatch.delenv("PRAISONAI_SHIP_ENABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))
    monkeypatch.chdir(tmp_path)


def test_enabled_by_default_when_unset():
    assert is_ship_disabled() is None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes", "on", " ON "])
def test_env_var_truthy_values_disable_ship(monkeypatch, value):
    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", value)
    reason = is_ship_disabled()
    assert reason and "PRAISONAI_DISABLE_SHIP" in reason


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", ""])
def test_env_var_falsy_values_keep_ship_enabled(monkeypatch, value):
    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", value)
    assert is_ship_disabled() is None


def test_config_key_disables_ship_via_schema_and_dict():
    reason = is_ship_disabled(config=ConfigSchema(ship=ShipConfig(enabled=False)))
    assert reason and "ship.enabled" in reason
    assert is_ship_disabled(config=ConfigSchema(ship=ShipConfig(enabled=True))) is None
    assert is_ship_disabled(config={"ship": {"enabled": False}}) is not None
    assert is_ship_disabled(config={"ship": {"enabled": True}}) is None


def test_config_file_ship_enabled_false_disables_ship(tmp_path):
    ConfigLoader(project_root=tmp_path).set("ship.enabled", False, scope="user")
    reason = is_ship_disabled()
    assert reason and "ship.enabled" in reason


def test_env_var_overrides_config(monkeypatch):
    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", "1")
    reason = is_ship_disabled(config=ConfigSchema(ship=ShipConfig(enabled=True)))
    assert reason and "PRAISONAI_DISABLE_SHIP" in reason

    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", "0")
    assert is_ship_disabled(config=ConfigSchema(ship=ShipConfig(enabled=False))) is None


def test_config_load_error_defaults_to_enabled(monkeypatch):
    def boom(self, force_reload=False):
        raise RuntimeError("corrupt config")

    monkeypatch.setattr(ConfigLoader, "load", boom)
    assert is_ship_disabled() is None


def test_cli_exits_1_without_calling_flow_when_disabled_by_env(monkeypatch):
    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", "1")
    monkeypatch.setattr(flow, "ship_to_draft_pr", lambda **kw: (_ for _ in ()).throw(AssertionError("must not run")))
    result = CliRunner().invoke(ship_cmd.app, ["--dry-run"])
    assert result.exit_code == 1
    assert "disabled" in result.output.lower()


def test_cli_exits_1_without_calling_flow_when_disabled_by_config(monkeypatch, tmp_path):
    ConfigLoader(project_root=tmp_path).set("ship.enabled", False, scope="user")
    monkeypatch.setattr(flow, "ship_to_draft_pr", lambda **kw: (_ for _ in ()).throw(AssertionError("must not run")))
    result = CliRunner().invoke(ship_cmd.app, ["--dry-run"])
    assert result.exit_code == 1
    assert "disabled" in result.output.lower()
