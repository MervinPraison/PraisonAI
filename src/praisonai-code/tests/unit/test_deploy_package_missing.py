"""Deploy command hidden when ``praisonai-deploy`` is not installed."""

from unittest.mock import patch

from praisonai_code.cli import app as app_mod


def test_deploy_hidden_from_help_when_package_missing(monkeypatch):
    monkeypatch.setattr(app_mod, "deploy_package_available", lambda: False)
    group = app_mod.LazyCommandGroup()
    names = group.list_commands(None)
    assert "deploy" not in names


def test_deploy_command_none_when_package_missing(monkeypatch):
    monkeypatch.setattr(app_mod, "deploy_package_available", lambda: False)
    group = app_mod.LazyCommandGroup()
    assert group.get_command(None, "deploy") is None
