"""Tests for platform JWT secret resolution (GHSA-cwj8, GHSA-f38v)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Direct import to avoid pulling auth_service deps at collection time
_jwt_path = Path(__file__).resolve().parents[2] / "praisonai_platform" / "services" / "jwt_secret.py"
_spec = importlib.util.spec_from_file_location("jwt_secret", _jwt_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
resolve_jwt_secret = _mod.resolve_jwt_secret


def test_jwt_secret_rejects_dev_default_in_prod():
    with pytest.raises(RuntimeError):
        resolve_jwt_secret(env={
            "PLATFORM_ENV": "production",
            "PLATFORM_JWT_SECRET": "dev-secret-change-me",
        })


def test_jwt_secret_allows_dev_default_when_dev_env():
    secret = resolve_jwt_secret(env={
        "PLATFORM_ENV": "dev",
        "PLATFORM_JWT_SECRET": "dev-secret-change-me",
    })
    assert secret == "dev-secret-change-me"


def test_jwt_secret_rejects_explicit_dev_secret_without_dev_env():
    with pytest.raises(RuntimeError):
        resolve_jwt_secret(env={"PLATFORM_JWT_SECRET": "dev-secret-change-me"})


def test_jwt_secret_ephemeral_when_unset():
    secret = resolve_jwt_secret(env={})
    assert secret != "dev-secret-change-me"
    assert len(secret) > 20
