"""
Tests for onboard wizard security / key-persistence features.

Covers the competitor-parity additions (see #1454):
- Allowlist (TELEGRAM_ALLOWED_USERS & siblings) is prompted and persisted
- Tokens + allowlist are written atomically to ``~/.praisonai/.env``
  with chmod 600
- ``.env`` merging preserves unrelated pre-existing keys

Note: the ``home_channel_env`` field and its matching prompt were removed
(#1487): no gateway code path consumed the value, and the prompt
confused non-developer users during bot onboarding. If a proactive
delivery feature ships later it can reintroduce this on an opt-in basis.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from praisonai.cli.features.onboard import (
    PLATFORMS,
    _generate_bot_yaml,
    _praison_home,
    _save_env_vars,
)


def test_all_platforms_declare_security_fields():
    for plat, info in PLATFORMS.items():
        assert "allowed_users_env" in info, f"{plat} missing allowed_users_env"
        assert "user_id_help" in info, f"{plat} missing user_id_help"
        assert info["allowed_users_env"].endswith("_ALLOWED_USERS")
        # ``home_channel_env`` intentionally absent — see module docstring.
        assert "home_channel_env" not in info, (
            f"{plat}: home_channel_env should not be re-added without a "
            f"consumer in the gateway/scheduler path."
        )


def test_praison_home_respects_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    assert _praison_home() == tmp_path


def test_praison_home_defaults(monkeypatch):
    monkeypatch.delenv("PRAISONAI_HOME", raising=False)
    assert _praison_home() == Path.home() / ".praisonai"


def test_save_env_vars_creates_file_with_chmod_600(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    out = _save_env_vars({"TELEGRAM_BOT_TOKEN": "abc:123", "TELEGRAM_ALLOWED_USERS": "42"})
    assert out == tmp_path / ".env"
    assert out.exists()
    body = out.read_text()
    assert "TELEGRAM_BOT_TOKEN=abc:123" in body
    assert "TELEGRAM_ALLOWED_USERS=42" in body
    # chmod 600 on POSIX; skipped check on Windows which uses different model
    if os.name != "nt":
        mode = stat.S_IMODE(out.stat().st_mode)
        assert mode == 0o600, f"expected 600 got {oct(mode)}"


def test_save_env_vars_merges_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-existing\nPRAISONAI_THEME=dark\n")
    _save_env_vars({"TELEGRAM_BOT_TOKEN": "new"})
    body = env_file.read_text()
    assert "OPENAI_API_KEY=sk-existing" in body
    assert "PRAISONAI_THEME=dark" in body
    assert "TELEGRAM_BOT_TOKEN=new" in body


def test_save_env_vars_drops_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    # Pure empty input → returns None, no file created
    assert _save_env_vars({}) is None
    assert _save_env_vars({"EMPTY": ""}) is None
    assert not (tmp_path / ".env").exists()


def test_save_env_vars_overwrites_same_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    _save_env_vars({"TELEGRAM_BOT_TOKEN": "old"})
    _save_env_vars({"TELEGRAM_BOT_TOKEN": "new"})
    body = (tmp_path / ".env").read_text()
    # Single occurrence, new value
    assert body.count("TELEGRAM_BOT_TOKEN=") == 1
    assert "TELEGRAM_BOT_TOKEN=new" in body


def test_generated_bot_yaml_references_allowlist():
    y = _generate_bot_yaml(["telegram"], agent_name="assistant")
    assert "token: ${TELEGRAM_BOT_TOKEN}" in y
    assert "allowed_users: ${TELEGRAM_ALLOWED_USERS}" in y
    # home_channel intentionally NOT emitted — no consumer in gateway today.
    assert "home_channel" not in y
    assert "HOME_CHANNEL" not in y


def test_generated_bot_yaml_for_all_platforms():
    y = _generate_bot_yaml(["telegram", "discord", "slack", "whatsapp"])
    for env in (
        "TELEGRAM_ALLOWED_USERS",
        "DISCORD_ALLOWED_USERS",
        "SLACK_ALLOWED_USERS",
        "WHATSAPP_ALLOWED_USERS",
    ):
        assert f"${{{env}}}" in y
    assert "phone_number_id: ${WHATSAPP_PHONE_NUMBER_ID}" in y
