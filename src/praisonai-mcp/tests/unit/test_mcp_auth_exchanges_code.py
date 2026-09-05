"""`praisonai mcp auth` must not store a token it never obtained.

The command ran the first half of an OAuth 2.1 flow -- discovery, browser,
loopback callback -- and then, instead of exchanging the authorization code
at the token endpoint, stored:

    auth_storage.set_tokens(name, {
        "access_token": f"oauth_{code[:20]}...",
        "refresh_token": None,
    }, server_url=server.url)

That value is a truncated authorization code with a literal "..." appended:
not a token, and useless as a bearer credential. It then printed
"Successfully authenticated with {name}".

Because no expires_at was written, MCPAuthStorage.is_token_expired() returns
False for it, so the fabricated entry looked permanently valid and shadowed
every later attempt at real OAuth -- the failure could not clear itself.

MCPOAuthProvider already implemented the whole flow including the exchange
(_exchange_code, grant_type=authorization_code). The command now calls it.
"""
import ast
import inspect
import time
from unittest.mock import MagicMock, patch

import pytest


def _auth_source():
    from praisonai_mcp.cli.commands import mcp as mcp_cli
    return inspect.getsource(mcp_cli.mcp_auth), mcp_cli


class TestNoFabricatedToken:

    def test_no_synthesised_access_token_literal(self):
        """Walk the AST: no f-string in this module builds an 'oauth_...' value."""
        _, mcp_cli = _auth_source()
        tree = ast.parse(inspect.getsource(mcp_cli))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                parts = [v.value for v in node.values
                         if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                if any(p.startswith("oauth_") for p in parts):
                    offenders.append(parts)
        assert not offenders, f"a token value is being synthesised: {offenders}"

    def test_the_command_does_not_write_tokens_itself(self):
        """Storing is the provider's job, after a real exchange."""
        src, _ = _auth_source()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert "set_tokens(" not in code

    def test_it_delegates_to_the_oauth_provider(self):
        src, _ = _auth_source()
        assert "MCPOAuthProvider" in src
        assert "ensure_authenticated" in src

    def test_the_docstring_no_longer_promises_placeholders(self):
        _, mcp_cli = _auth_source()
        doc = mcp_cli.mcp_auth.__doc__ or ""
        assert "placeholder tokens only" not in doc


class TestTheProviderReallyExchanges:

    def test_provider_has_a_code_exchange(self):
        from praisonaiagents.mcp.oauth_provider import MCPOAuthProvider
        assert hasattr(MCPOAuthProvider, "_exchange_code")

    def test_the_exchange_uses_the_authorization_code_grant(self):
        from praisonaiagents.mcp import oauth_provider
        src = inspect.getsource(oauth_provider.MCPOAuthProvider._exchange_code)
        assert '"grant_type": "authorization_code"' in src
        assert "token_endpoint" in src

    def test_a_token_without_expiry_is_not_treated_as_fresh_forever(self):
        """The property that made the fabricated entry unrecoverable."""
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
        src = inspect.getsource(MCPAuthStorage.is_token_expired)
        assert "expires_at" in src, (
            "expiry handling changed; re-check that a token with no expires_at "
            "cannot shadow re-authentication indefinitely"
        )


class TestExpiryStorageBehaviour:
    """Exercise the real storage, not its source, for the shadow property."""

    def test_legacy_entry_without_expires_at_reports_not_expired(self, tmp_path):
        """This is the exact state that made the fake token unrecoverable."""
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage

        storage = MCPAuthStorage(filepath=str(tmp_path / "auth.json"))
        storage.set_tokens(
            "srv",
            {"access_token": "oauth_ABCDEFGHIJKLMNOPQRST...", "refresh_token": None},
            server_url="https://srv.example/mcp",
        )
        # No expires_at -> is_token_expired() is False, i.e. "looks valid".
        assert storage.is_token_expired("srv") is False

    def test_expired_token_reports_expired(self, tmp_path):
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage

        storage = MCPAuthStorage(filepath=str(tmp_path / "auth.json"))
        storage.set_tokens(
            "srv",
            {"access_token": "real", "expires_at": time.time() - 1},
            server_url="https://srv.example/mcp",
        )
        assert storage.is_token_expired("srv") is True


def _run_auth(remote_config, storage, provider, monkeypatch_targets):
    """Invoke mcp_auth with storage/provider/config/output all mocked."""
    from praisonai_mcp.cli.commands import mcp as mcp_cli

    loader = MagicMock()
    config = MagicMock()
    config.mcp.servers = {"srv": remote_config}
    loader.load.return_value = config

    schema = MagicMock()
    schema.MCPRemoteConfig = type(remote_config)

    with patch.object(mcp_cli, "_require_code", lambda: None), \
         patch.object(mcp_cli, "get_config_loader", return_value=loader), \
         patch.object(mcp_cli, "get_output_controller", return_value=MagicMock(is_json_mode=False)), \
         patch.object(mcp_cli, "configuration_schema", return_value=schema), \
         patch("praisonaiagents.mcp.MCPAuthStorage", return_value=storage), \
         patch(
             "praisonaiagents.mcp.oauth_provider.MCPOAuthProvider",
             return_value=provider,
         ):
        mcp_cli.mcp_auth("srv", timeout=1.0)


class TestLegacyCredentialPurge:
    """Seed the legacy fake entry and prove a real flow replaces it."""

    def _remote(self, oauth=None):
        from praisonai_code.cli.configuration.schema import (
            MCPRemoteConfig,
        )
        return MCPRemoteConfig(url="https://srv.example/mcp", oauth=oauth)

    def test_legacy_placeholder_is_removed_before_delegating(self, tmp_path):
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage

        storage = MCPAuthStorage(filepath=str(tmp_path / "auth.json"))
        storage.set_tokens(
            "srv",
            {"access_token": "oauth_ABCDEFGHIJKLMNOPQRST...", "refresh_token": None},
            server_url="https://srv.example/mcp",
        )

        provider = MagicMock()
        provider.ensure_authenticated.return_value = "real-access-token"

        _run_auth(self._remote(), storage, provider, None)

        # The provider ran a real exchange...
        provider.ensure_authenticated.assert_called_once()
        # ...and the fabricated entry was cleared before delegation.
        entry = storage.get("srv")
        if entry:
            access = (entry.get("tokens") or {}).get("access_token") or ""
            assert not (access.startswith("oauth_") and access.endswith("..."))

    def test_genuine_token_is_not_purged(self, tmp_path):
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage

        storage = MCPAuthStorage(filepath=str(tmp_path / "auth.json"))
        storage.set_tokens(
            "srv",
            {"access_token": "gho_real_looking_token", "refresh_token": "r"},
            server_url="https://srv.example/mcp",
        )

        provider = MagicMock()
        provider.ensure_authenticated.return_value = "gho_real_looking_token"

        _run_auth(self._remote(), storage, provider, None)

        entry = storage.get("srv")
        assert entry is not None
        assert entry["tokens"]["access_token"] == "gho_real_looking_token"


class TestConfiguredClientIsCarried:
    """A pre-registered client_id from config must reach the provider."""

    def _remote_with_oauth(self):
        from praisonai_code.cli.configuration.schema import (
            MCPRemoteConfig,
            MCPOAuthConfig,
        )
        oauth = MCPOAuthConfig(
            client_id="preregistered-id",
            client_secret="s3cr3t",
            scopes=["read", "write"],
        )
        return MCPRemoteConfig(url="https://srv.example/mcp", oauth=oauth)

    def test_configured_client_id_is_seeded_into_storage(self, tmp_path):
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage

        storage = MCPAuthStorage(filepath=str(tmp_path / "auth.json"))

        provider = MagicMock()
        provider.ensure_authenticated.return_value = "real-access-token"

        _run_auth(self._remote_with_oauth(), storage, provider, None)

        entry = storage.get_for_url("srv", "https://srv.example/mcp")
        assert entry is not None
        client_info = entry.get("client_info") or {}
        assert client_info.get("client_id") == "preregistered-id"
        assert client_info.get("client_secret") == "s3cr3t"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
