"""Tests for issue #3774 — zero-disk credential injection via env blob.

When ``PRAISONAI_AUTH_CONTENT`` is set, ``CredentialStore`` must:

1. Load the whole store from the JSON env var in memory.
2. Never read from or write to the on-disk credentials file (writes are
   applied in memory only, nothing is persisted).
3. Take precedence over any on-disk file.
4. Reject invalid JSON / non-object payloads with a clear error.
"""

import json
import time

import pytest

from praisonai_code.cli.configuration.credentials import (
    AUTH_CONTENT_ENV,
    CredentialStore,
)


def test_env_blob_loads_in_memory_without_reading_disk(tmp_path, monkeypatch):
    disk = tmp_path / "credentials.json"
    disk.write_text(json.dumps({"openai": {"api_key": "sk-from-disk"}}))

    blob = {"openai": {"api_key": "sk-from-env", "auth_method": "apikey"}}
    monkeypatch.setenv(AUTH_CONTENT_ENV, json.dumps(blob))

    store = CredentialStore(credentials_path=disk)
    assert store.is_in_memory is True

    # Env blob takes precedence over the on-disk file.
    cred = store.get_credential("openai")
    assert cred is not None
    assert cred.api_key == "sk-from-env"
    assert store.get_valid_token("openai") == "sk-from-env"


def test_env_blob_writes_never_touch_disk(tmp_path, monkeypatch):
    disk = tmp_path / "credentials.json"

    blob = {"openai": {"api_key": "sk-env", "auth_method": "apikey"}}
    monkeypatch.setenv(AUTH_CONTENT_ENV, json.dumps(blob))

    store = CredentialStore(credentials_path=disk)
    store.store_credential("anthropic", "sk-ant-new")

    # In-memory update is visible...
    assert store.get_credential("anthropic").api_key == "sk-ant-new"
    assert set(store.list_providers()) == {"openai", "anthropic"}
    # ...but nothing was persisted to disk.
    assert not disk.exists()


def test_env_blob_oauth_token_available_in_memory(tmp_path, monkeypatch):
    disk = tmp_path / "credentials.json"
    blob = {
        "acme": {
            "api_key": "tok-access",
            "auth_method": "oauth",
            "access_token": "tok-access",
            "refresh_token": "tok-refresh",
            "expires_at": time.time() + 3600,
        }
    }
    monkeypatch.setenv(AUTH_CONTENT_ENV, json.dumps(blob))

    store = CredentialStore(credentials_path=disk)
    cred = store.get_credential("acme")
    assert cred is not None and cred.is_oauth()
    assert store.get_valid_token("acme") == "tok-access"
    assert not disk.exists()


def test_env_blob_invalid_json_raises(monkeypatch):
    monkeypatch.setenv(AUTH_CONTENT_ENV, "{not-json")
    with pytest.raises(ValueError):
        CredentialStore()


def test_env_blob_non_object_raises(monkeypatch):
    monkeypatch.setenv(AUTH_CONTENT_ENV, json.dumps([1, 2, 3]))
    with pytest.raises(ValueError):
        CredentialStore()


def test_env_blob_empty_raises(tmp_path, monkeypatch):
    # A present-but-empty value must be rejected, not silently fall back to
    # disk, so the zero-disk contract cannot be broken by an empty CI secret.
    disk = tmp_path / "credentials.json"
    monkeypatch.setenv(AUTH_CONTENT_ENV, "")
    with pytest.raises(ValueError):
        CredentialStore(credentials_path=disk)

    monkeypatch.setenv(AUTH_CONTENT_ENV, "   ")
    with pytest.raises(ValueError):
        CredentialStore(credentials_path=disk)


def test_env_blob_malformed_provider_entry_raises(monkeypatch):
    # A non-object provider entry (e.g. null) would crash credential lookup
    # later; reject it up-front with a clear error.
    monkeypatch.setenv(AUTH_CONTENT_ENV, json.dumps({"openai": None}))
    with pytest.raises(ValueError):
        CredentialStore()


def test_no_env_blob_uses_disk(tmp_path, monkeypatch):
    monkeypatch.delenv(AUTH_CONTENT_ENV, raising=False)
    disk = tmp_path / "credentials.json"
    store = CredentialStore(credentials_path=disk)
    assert store.is_in_memory is False

    store.store_credential("openai", "sk-disk")
    assert disk.exists()
    assert store.get_credential("openai").api_key == "sk-disk"
