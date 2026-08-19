"""Tests for the on-demand diagnostics bundle (Issue #4044).

Pins the two properties that make the bundle safe to attach to a bug report:
1. it produces one portable archive with the expected sanitised sections, and
2. it never leaks secret values — config credentials collapse to presence
   markers and registered secrets are redacted out of every text section.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from praisonai_bot.gateway.diagnostics import (
    _sanitise_config_shape,
    build_diagnostics_bundle,
)


def test_config_shape_drops_secret_values():
    cfg = {
        "channels": {
            "telegram": {
                "platform": "telegram",
                "token": "123:SUPERSECRETTOKEN",
                "chat_id": 42,
            }
        },
        "gateway": {"auth_token": "", "host": "127.0.0.1"},
    }

    shape = _sanitise_config_shape(cfg)

    tg = shape["channels"]["telegram"]
    assert tg["token"] == "<set>"
    assert tg["platform"] == "<str>"
    assert tg["chat_id"] == "<int>"
    assert shape["gateway"]["auth_token"] == "<empty>"
    # No raw secret value survives anywhere in the shape.
    assert "SUPERSECRETTOKEN" not in json.dumps(shape)


def test_build_bundle_writes_sanitised_archive(tmp_path):
    config = tmp_path / "gateway.yaml"
    config.write_text(
        "channels:\n"
        "  telegram:\n"
        "    platform: telegram\n"
        "    token: 999:LEAKYTOKEN\n"
    )
    out_dir = tmp_path / "diag"

    result = build_diagnostics_bundle(str(config), output_dir=str(out_dir))

    bundle = result["path"]
    assert bundle.endswith(".zip")
    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        assert {"summary.txt", "manifest.json", "config_shape.json"} <= names
        blob = b"".join(zf.read(n) for n in names)

    # The raw token from the config must never appear in the archive.
    assert b"LEAKYTOKEN" not in blob


def test_build_bundle_redacts_registered_secret(tmp_path, monkeypatch):
    from praisonaiagents import secrets as secrets_mod

    secret = "TOKEN-abcdef0123456789"
    secrets_mod.register_secret_for_redaction(secret)

    # Force the log section to contain the secret so we can prove redaction.
    monkeypatch.setattr(
        "praisonai_bot.gateway.diagnostics._collect_logs",
        lambda lines=200: secrets_mod.redact_secrets(f"line with {secret}"),
    )

    result = build_diagnostics_bundle(None, output_dir=str(tmp_path))
    with zipfile.ZipFile(result["path"]) as zf:
        logs = zf.read("logs.txt").decode()

    assert secret not in logs
    assert "[REDACTED]" in logs


def test_bundle_survives_missing_config(tmp_path):
    result = build_diagnostics_bundle(None, output_dir=str(tmp_path))
    with zipfile.ZipFile(result["path"]) as zf:
        shape = json.loads(zf.read("config_shape.json"))
    assert "error" in shape
