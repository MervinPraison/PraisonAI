"""Per-channel config lifecycle: add / update / disable / remove (Issue #6079)."""

import pytest
import yaml
from typer.testing import CliRunner

from praisonai_bot.cli.commands.gateway import app
from praisonai_bot.gateway.admin import edit_gateway_channel

BASE = {
    "agents": {"assistant": {"instructions": "hi"}},
    "channels": {
        "telegram": {"platform": "telegram", "token": "${TELEGRAM_BOT_TOKEN}"},
    },
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "gateway.yaml"
    path.write_text(yaml.safe_dump(BASE, sort_keys=False))
    return path


def _load(path):
    return yaml.safe_load(path.read_text())


def _run(*args):
    return CliRunner().invoke(app, ["channels", *args])


def test_add_channel_keeps_others_and_defaults_env_token(config):
    result = _run("add", "discord", "--config", str(config), "--set", "group_policy=mention_only")
    assert result.exit_code == 0, result.output
    channels = _load(config)["channels"]
    assert channels["telegram"] == BASE["channels"]["telegram"]
    assert channels["discord"] == {
        "platform": "discord",
        "token": "${DISCORD_BOT_TOKEN}",
        "group_policy": "mention_only",
    }
    assert _load(config)["agents"] == BASE["agents"]


def test_add_existing_channel_is_rejected(config):
    result = _run("add", "telegram", "--config", str(config))
    assert result.exit_code == 1
    assert _load(config) == BASE


def test_update_and_disable_channel(config):
    assert _run("update", "telegram", "--config", str(config), "--token", "${NEW_TOKEN}").exit_code == 0
    assert _run("add", "discord", "--config", str(config)).exit_code == 0
    assert _run("disable", "telegram", "--config", str(config)).exit_code == 0
    telegram = _load(config)["channels"]["telegram"]
    assert telegram["token"] == "${NEW_TOKEN}"
    assert telegram["enabled"] is False


def test_invalid_update_is_not_persisted(config):
    result = _run("update", "telegram", "--config", str(config), "--set", "allowed_users=[1, 2]")
    assert result.exit_code == 1
    assert _load(config) == BASE


def test_unknown_platform_is_rejected(config):
    assert _run("add", "bogus", "--config", str(config)).exit_code == 1
    assert _load(config) == BASE


def test_remove_channel(config):
    assert _run("add", "discord", "--config", str(config)).exit_code == 0
    assert _run("remove", "discord", "--config", str(config)).exit_code == 0
    assert "discord" not in _load(config)["channels"]
    assert _run("remove", "discord", "--config", str(config)).exit_code == 1


def test_python_helper_matches_cli(config):
    block = edit_gateway_channel(config, "discord", {"token": "${D}"})
    assert block == {"platform": "discord", "token": "${D}"}
    with pytest.raises(KeyError):
        edit_gateway_channel(config, "nope", remove=True)
    with pytest.raises(ValueError):
        edit_gateway_channel(config, "bogus", {})
    assert "bogus" not in _load(config)["channels"]


def test_list_still_works_without_subcommand(config):
    result = _run("--config", str(config), "--json")
    assert result.exit_code == 0
    assert '"telegram"' in result.output
