"""Tests for the importable gateway admin API (Issue #3985)."""

import os

import pytest

import praisonai_bot
from praisonai_bot import (
    GatewayRepairResult,
    provision_gateway_config,
    repair_gateway_config,
)


def test_public_exports_present():
    assert "repair_gateway_config" in praisonai_bot.__all__
    assert "provision_gateway_config" in praisonai_bot.__all__
    assert "GatewayRepairResult" in praisonai_bot.__all__


def test_repair_result_default_shape():
    result = GatewayRepairResult()
    assert result.auth_token_minted is False
    assert result.config_version_migrated is False
    assert result.changes == []
    assert result.remaining_degraded_owners == []
    assert result.to_dict() == {
        "auth_token_minted": False,
        "config_version_migrated": False,
        "changes": [],
        "remaining_degraded_owners": [],
    }


def test_repair_missing_config_is_clean(tmp_path):
    result = repair_gateway_config(tmp_path / "nope.yaml")
    assert isinstance(result, GatewayRepairResult)
    assert not result.remaining_degraded_owners
    assert result.auth_token_minted is False
    assert result.config_version_migrated is False


def test_repair_detect_only_leaves_weak_token_degraded(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    config = tmp_path / "bot.yaml"
    config.write_text(
        "gateway:\n  host: 0.0.0.0\n  port: 8765\n  auth_token: changeme\n"
        "agents:\n  assistant:\n    instructions: hi\n"
    )

    result = repair_gateway_config(config, fix=False)

    owners = result.remaining_degraded_owners
    assert any(o["owner_id"] == "core/gateway/auth-token" for o in owners)
    for owner in owners:
        assert owner["owner_kind"] == "gateway"
        assert owner["retry_hint"] == "praisonai gateway doctor --fix"
    assert result.auth_token_minted is False


def test_repair_fix_mints_token_and_clears(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    config = tmp_path / "bot.yaml"
    config.write_text(
        "gateway:\n  host: 0.0.0.0\n  port: 8765\n  auth_token: changeme\n"
        "agents:\n  assistant:\n    instructions: hi\n"
    )

    result = repair_gateway_config(config, fix=True)

    assert result.auth_token_minted is True
    assert not any(
        o["owner_id"] == "core/gateway/auth-token"
        for o in result.remaining_degraded_owners
    )
    env_file = tmp_path / ".env"
    assert env_file.exists()
    assert "GATEWAY_AUTH_TOKEN=" in env_file.read_text()


def test_provision_writes_config_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    config = tmp_path / "bot.yaml"

    path = provision_gateway_config(
        platform="telegram",
        token="123:abc",
        agents=["assistant"],
        config_path=config,
    )

    assert path == config
    content = config.read_text()
    assert "channels:" in content
    assert "telegram" in content
    assert "${TELEGRAM_BOT_TOKEN}" in content
    env_file = tmp_path / ".env"
    assert "TELEGRAM_BOT_TOKEN=123:abc" in env_file.read_text()


def test_provision_defaults_to_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    path = provision_gateway_config(platform="telegram", token="t")
    assert path == tmp_path / "bot.yaml"
    assert path.exists()


def test_provision_declares_all_requested_agents(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    config = tmp_path / "bot.yaml"

    provision_gateway_config(
        platform="telegram",
        token="123:abc",
        agents=["assistant", "researcher", "writer"],
        config_path=config,
    )

    import yaml

    parsed = yaml.safe_load(config.read_text())
    assert set(parsed["agents"]) == {"assistant", "researcher", "writer"}
    assert parsed["channels"]["telegram"]["routes"]["default"] == "assistant"


def test_provision_rejects_unsupported_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="unsupported platform"):
        provision_gateway_config(platform="myspace", token="123:abc")
    assert not (tmp_path / "bot.yaml").exists()


def test_provision_rejects_empty_token(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="non-empty token"):
        provision_gateway_config(platform="telegram", token="")
    with pytest.raises(ValueError, match="non-empty token"):
        provision_gateway_config(platform="telegram", token="   ")
    assert not (tmp_path / "bot.yaml").exists()
