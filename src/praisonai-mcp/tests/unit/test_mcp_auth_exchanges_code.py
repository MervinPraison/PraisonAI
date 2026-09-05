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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
