"""Tests for the OAuth provider registry (issue #2826).

The ``auth login --method oauth`` flow was fully implemented but shipped with an
empty ``OAUTH_PROVIDERS`` registry, so no built-in provider could sign in via
OAuth. These tests assert the registry is populated with standards-compliant
device-code endpoints and that provider resolution + client-id handling behave
correctly. No network calls are made.
"""

from praisonai_code.cli.configuration.oauth import (
    OAUTH_PROVIDERS,
    OAuthProviderConfig,
    get_provider_config,
    provider_requires_client_id,
    provider_supports_oauth,
)


def test_registry_is_populated():
    assert OAUTH_PROVIDERS, "OAUTH_PROVIDERS must not be empty"
    for name, cfg in OAUTH_PROVIDERS.items():
        assert isinstance(cfg, OAuthProviderConfig)
        assert cfg.token_url, f"{name} missing token_url"
        assert cfg.flow in {"device", "authcode"}
        if cfg.flow == "device":
            assert cfg.device_authorization_url, f"{name} missing device endpoint"
        else:
            assert cfg.authorization_url, f"{name} missing authorization endpoint"


def test_known_providers_present():
    for provider in ("github", "google", "gemini", "azure"):
        assert provider in OAUTH_PROVIDERS


def test_registry_keys_are_lowercase():
    for name in OAUTH_PROVIDERS:
        assert name == name.lower()


def test_known_provider_is_oauth_capable():
    assert provider_supports_oauth("github") is True
    assert provider_supports_oauth("GitHub") is True  # case-insensitive


def test_unknown_provider_not_oauth_capable():
    assert provider_supports_oauth("some-random-provider") is False


def test_registry_provider_requires_client_id_when_not_baked_in():
    # Built-in entries ship without a baked-in client id (registration-specific).
    assert provider_requires_client_id("github") is True


def test_client_id_override_resolves_config():
    cfg = get_provider_config("github", {"client_id": "abc123"})
    assert cfg is not None
    assert cfg.client_id == "abc123"
    assert cfg.flow == "device"
    assert cfg.device_authorization_url == "https://github.com/login/device/code"
    assert cfg.token_url == "https://github.com/login/oauth/access_token"


def test_client_id_override_clears_requirement():
    assert provider_requires_client_id("github", {"client_id": "abc123"}) is False


def test_missing_client_id_yields_no_config():
    # Endpoints are known but without a client id the config cannot be built.
    assert get_provider_config("github") is None
    # ...yet the provider is still considered OAuth-capable.
    assert provider_supports_oauth("github") is True


def test_adhoc_provider_via_overrides():
    cfg = get_provider_config(
        "selfhosted",
        {
            "client_id": "cli",
            "token_url": "https://example.com/token",
            "device_authorization_url": "https://example.com/device",
        },
    )
    assert cfg is not None
    assert cfg.flow == "device"


def test_run_oauth_login_missing_client_id_message():
    from praisonai_code.cli.configuration.oauth import run_oauth_login
    import pytest

    with pytest.raises(ValueError) as exc:
        run_oauth_login("github")
    assert "client id" in str(exc.value).lower()
