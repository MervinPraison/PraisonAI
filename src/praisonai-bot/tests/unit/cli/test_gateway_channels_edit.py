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


def test_parent_config_option_applies_to_subcommand(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    other = tmp_path / "other.yaml"
    other.write_text(yaml.safe_dump(BASE, sort_keys=False))
    result = _run("--config", str(other), "update", "telegram", "--set", "group_policy=mention_only")
    assert result.exit_code == 0, result.output
    assert _load(other)["channels"]["telegram"]["group_policy"] == "mention_only"
    assert _load(config) == BASE


def test_single_bot_platform_is_converted_not_hidden(tmp_path):
    path = tmp_path / "bot.yaml"
    path.write_text(yaml.safe_dump({"agent": {"instructions": "hi"}, "platform": "telegram", "token": "${T}"}))
    edit_gateway_channel(path, "discord", {"token": "${D}"})
    cfg = _load(path)
    assert "platform" not in cfg and "token" not in cfg
    assert cfg["channels"]["telegram"] == {"platform": "telegram", "token": "${T}"}
    assert cfg["channels"]["discord"]["token"] == "${D}"


def test_botos_platforms_are_converted(tmp_path):
    path = tmp_path / "bot.yaml"
    path.write_text(yaml.safe_dump({"agent": {"instructions": "hi"}, "platforms": {"telegram": {"token": "${T}"}}}))
    result = CliRunner().invoke(app, ["channels", "update", "telegram", "--config", str(path), "--set", "group_policy=mention_only"])
    assert result.exit_code == 0, result.output
    cfg = _load(path)
    assert "platforms" not in cfg
    assert cfg["channels"]["telegram"] == {"platform": "telegram", "token": "${T}", "group_policy": "mention_only"}


def test_env_placeholder_in_typed_field_does_not_block_edit(config, monkeypatch):
    cfg = _load(config)
    cfg["channels"]["telegram"]["max_inbound_media_bytes"] = "${MEDIA_LIMIT}"
    config.write_text(yaml.safe_dump(cfg, sort_keys=False))
    monkeypatch.setenv("MEDIA_LIMIT", "1024")
    edit_gateway_channel(config, "telegram", {"token": "${NEW}"})
    saved = _load(config)["channels"]["telegram"]
    assert saved["max_inbound_media_bytes"] == "${MEDIA_LIMIT}"
    assert saved["token"] == "${NEW}"


def test_removing_last_channel_is_rejected_even_with_env_token(config, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    with pytest.raises(ValueError):
        edit_gateway_channel(config, "telegram", remove=True)
    with pytest.raises(ValueError):
        edit_gateway_channel(config, "telegram", {"enabled": False})
    assert _load(config) == BASE


def test_env_platform_reference_is_resolved_before_conversion(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_PLATFORM", "telegram")
    path = tmp_path / "bot.yaml"
    path.write_text(yaml.safe_dump({"agent": {"instructions": "hi"}, "platform": "${BOT_PLATFORM}", "token": "${T}"}))
    edit_gateway_channel(path, "discord", {"token": "${D}"})
    cfg = _load(path)
    assert cfg["channels"]["telegram"] == {"platform": "telegram", "token": "${T}"}
    assert cfg["channels"]["discord"]["token"] == "${D}"


def test_concurrent_edits_are_not_lost(config):
    from concurrent.futures import ThreadPoolExecutor

    names = [f"ch{i}" for i in range(8)]
    with ThreadPoolExecutor(len(names)) as pool:
        list(pool.map(lambda n: edit_gateway_channel(config, n, {"platform": "telegram", "token": "${X}"}), names))
    assert set(_load(config)["channels"]) == {"telegram", *names}


def test_missing_config_raises_without_lock_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        edit_gateway_channel(tmp_path / "nope.yaml", "discord", {})
    assert not list(tmp_path.iterdir())
