#!/usr/bin/env python3
"""
MCP Auth Example

Demonstrates the OAuth 2.1 and OIDC Discovery per MCP 2025-11-25 specification.

Features:
- OAuth 2.1 with PKCE
- OpenID Connect Discovery
- API Key authentication
- Scope management

Usage:
    python mcp_auth_example.py
"""

import asyncio
from praisonai.mcp_server.auth.oauth import OAuthConfig, OAuthManager
from praisonai.mcp_server.auth.oidc import OIDCDiscovery
from praisonai.mcp_server.auth.api_key import APIKeyAuth
from praisonai.mcp_server.auth.scopes import ScopeManager


async def main():
    print("=" * 60)
    print("MCP Auth Example (2025-11-25 Specification)")
    print("=" * 60)
    
    # 1. OIDC Discovery
    print("\n1. OpenID Connect Discovery")
    print("-" * 40)
    
    discovery = OIDCDiscovery()
    
    # Discover Google's OIDC configuration
    issuer = "https://accounts.google.com"
    print(f"   Discovering OIDC config from: {issuer}")
    
    config = await discovery.discover(issuer)
    if config:
        print(f"   ✓ Issuer: {config.issuer}")
        print(f"   ✓ Authorization endpoint: {config.authorization_endpoint}")
        print(f"   ✓ Token endpoint: {config.token_endpoint}")
        print(f"   ✓ JWKS URI: {config.jwks_uri}")
    else:
        print("   ✗ Discovery failed")
    
    # 2. OAuth 2.1 Configuration
    print("\n2. OAuth 2.1 Configuration")
    print("-" * 40)
    
    oauth_config = OAuthConfig(
        authorization_endpoint="https://auth.example.com/authorize",
        token_endpoint="https://auth.example.com/token",
        client_id="my-mcp-client",
        default_scopes=["openid", "profile", "tools:read"],
        use_pkce=True,  # PKCE is required for OAuth 2.1
    )
    
    oauth = OAuthManager(oauth_config)
    
    # Create authorization URL with PKCE
    auth_url, auth_request = oauth.create_authorization_url(
        scopes=["openid", "profile", "tools:read", "tools:call"],
    )
    
    print(f"   Authorization URL: {auth_url[:80]}...")
    print(f"   State: {auth_request.state}")
    print(f"   PKCE code verifier: {auth_request.code_verifier[:20]}...")
    print(f"   PKCE code challenge: {auth_request.code_challenge[:20]}...")
    
    # 3. API Key Authentication
    print("\n3. API Key Authentication")
    print("-" * 40)
    
    api_key_auth = APIKeyAuth(allow_env_key=False)
    
    # Generate a new API key
    raw_key, api_key = api_key_auth.generate_key(
        name="demo-key",
        scopes=["tools:read", "tools:call", "resources:read"],
    )
    
    print(f"   Generated key: {raw_key[:20]}...")
    print(f"   Key ID: {api_key.key_id}")
    print(f"   Key name: {api_key.name}")
    print(f"   Scopes: {api_key.scopes}")
    
    # Validate the key
    is_valid, validated_key = api_key_auth.validate(raw_key)
    print(f"\n   Validation result: {'✓ Valid' if is_valid else '✗ Invalid'}")
    
    # Validate via header
    is_valid_header, _ = api_key_auth.validate_header(f"Bearer {raw_key}")
    print(f"   Header validation: {'✓ Valid' if is_valid_header else '✗ Invalid'}")
    
    # 4. Scope Management
    print("\n4. Scope Management")
    print("-" * 40)
    
    scope_manager = ScopeManager()
    
    # Check if required scopes are granted
    required = ["tools:read"]
    granted = ["tools:call"]  # tools:call implies tools:read
    
    is_valid, challenge = scope_manager.validate_scopes(required, granted)
    print(f"   Required: {required}")
    print(f"   Granted: {granted}")
    print(f"   Valid: {'✓' if is_valid else '✗'}")
    
    # Expand scopes (show implied scopes)
    expanded = scope_manager.expand_scopes(["tools:call"])
    print(f"\n   Expanded 'tools:call': {expanded}")
    
    # Admin scope expands to all
    admin_expanded = scope_manager.expand_scopes(["admin"])
    print(f"   Expanded 'admin': {list(admin_expanded)[:5]}...")
    
    # 5. WWW-Authenticate Challenge
    print("\n5. WWW-Authenticate Challenge")
    print("-" * 40)
    
    challenge_header = oauth.create_www_authenticate_challenge(
        required_scopes=["admin"],
        error="insufficient_scope",
        error_description="Admin access required",
    )
    print(f"   Header: {challenge_header}")
    
    print("\n" + "=" * 60)
    print("Auth Example Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
