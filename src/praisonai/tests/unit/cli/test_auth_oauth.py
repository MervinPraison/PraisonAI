#!/usr/bin/env python3
"""
Unit tests for browser-based (OAuth / device-code) provider sign-in.

Covers:
- OAuth credential storage + retrieval with token fields
- Expiry detection and transparent refresh via the credential store
- Provider OAuth-config resolution (registry + ad-hoc overrides)
- Auto method selection falling back to API-key for non-OAuth providers
"""

import time
import tempfile
from pathlib import Path

import pytest


def _store(tmp: str):
    from praisonai.cli.configuration.credentials import CredentialStore
    return CredentialStore(Path(tmp) / "creds.json")


def test_store_and_get_oauth_credential():
    from praisonai.cli.configuration.credentials import CredentialStore

    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        expires = time.time() + 3600
        store.store_oauth_credential(
            provider="acme",
            access_token="at-123",
            refresh_token="rt-456",
            expires_at=expires,
            token_url="https://acme.test/token",
            client_id="cid",
            scope="read",
            model="acme-large",
        )

        cred = store.get_credential("acme")
        assert cred is not None
        assert cred.is_oauth()
        assert cred.auth_method == "oauth"
        assert cred.access_token == "at-123"
        assert cred.refresh_token == "rt-456"
        assert cred.expires_at == expires
        # Mirrored into api_key for backward-compatible readers.
        assert cred.api_key == "at-123"
        assert not cred.is_expired()


def test_apikey_credential_is_not_oauth():
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.store_credential(provider="openai", api_key="sk-abc1234567890")
        cred = store.get_credential("openai")
        assert cred is not None
        assert not cred.is_oauth()
        assert cred.auth_method == "apikey"
        assert not cred.is_expired()


def test_expired_token_detection():
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.store_oauth_credential(
            provider="acme",
            access_token="at-old",
            expires_at=time.time() - 10,
        )
        cred = store.get_credential("acme")
        assert cred.is_expired()


def test_get_valid_token_apikey_passthrough():
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.store_credential(provider="openai", api_key="sk-key")
        assert store.get_valid_token("openai") == "sk-key"


def test_get_valid_token_refreshes_expired(monkeypatch):
    from praisonai.cli.configuration import credentials as cred_mod

    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.store_oauth_credential(
            provider="acme",
            access_token="at-old",
            refresh_token="rt-old",
            expires_at=time.time() - 10,
            token_url="https://acme.test/token",
            client_id="cid",
        )

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "access_token": "at-new",
                    "refresh_token": "rt-new",
                    "expires_in": 3600,
                }

        class _FakeRequests:
            @staticmethod
            def post(url, data=None, timeout=None):
                assert data["grant_type"] == "refresh_token"
                assert data["refresh_token"] == "rt-old"
                return _Resp()

        monkeypatch.setitem(__import__("sys").modules, "requests", _FakeRequests)

        token = store.get_valid_token("acme")
        assert token == "at-new"

        # Persisted with new token + rotated refresh token.
        refreshed = store.get_credential("acme")
        assert refreshed.access_token == "at-new"
        assert refreshed.refresh_token == "rt-new"
        assert not refreshed.is_expired()


def test_provider_config_overrides_enable_oauth():
    from praisonai.cli.configuration.oauth import (
        get_provider_config,
        provider_supports_oauth,
    )

    # Unknown provider with no override -> not OAuth-capable.
    assert not provider_supports_oauth("nope")

    cfg = get_provider_config(
        "selfhosted",
        overrides={
            "client_id": "cid",
            "token_url": "https://h/token",
            "device_authorization_url": "https://h/device",
        },
    )
    assert cfg is not None
    assert cfg.flow == "device"
    assert cfg.client_id == "cid"


def test_run_oauth_login_rejects_unconfigured_provider():
    from praisonai.cli.configuration.oauth import run_oauth_login

    with pytest.raises(ValueError):
        run_oauth_login("totally-unknown-provider")


def test_credential_lookup_uses_fresh_oauth_token(monkeypatch):
    """The LLM credential lookup should surface a valid OAuth token as api_key."""
    from praisonai.cli.configuration.credentials import CredentialStore
    import praisonai.llm.credentials as llm_creds

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "creds.json"
        store = CredentialStore(path)
        store.store_oauth_credential(
            provider="openai",
            access_token="at-live",
            expires_at=time.time() + 3600,
        )

        monkeypatch.setattr(
            llm_creds, "CredentialStore", lambda: CredentialStore(path)
        )

        data = llm_creds._credential_lookup("openai")
        assert data is not None
        assert data["api_key"] == "at-live"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
