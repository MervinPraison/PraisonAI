"""
Unit tests for MCP Auth Module

Tests for OAuth 2.1, OIDC Discovery, API Key Auth, and Scopes.
"""


class TestAPIKeyAuth:
    """Tests for APIKeyAuth class."""
    
    def test_generate_key(self):
        """Test API key generation."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        raw_key, api_key = auth.generate_key(name="test-key")
        
        assert raw_key.startswith("mcp_")
        assert api_key.key_id is not None
        assert api_key.name == "test-key"
    
    def test_generate_key_with_scopes(self):
        """Test API key generation with scopes."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        raw_key, api_key = auth.generate_key(
            name="scoped-key",
            scopes=["tools:read", "tools:call"],
        )
        
        assert api_key.scopes == ["tools:read", "tools:call"]
        assert api_key.has_scope("tools:read") is True
        assert api_key.has_scope("admin") is False
    
    def test_validate_key(self):
        """Test API key validation."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        raw_key, api_key = auth.generate_key()
        
        is_valid, retrieved = auth.validate(raw_key)
        
        assert is_valid is True
        assert retrieved.key_id == api_key.key_id
    
    def test_validate_invalid_key(self):
        """Test invalid key validation."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        
        is_valid, retrieved = auth.validate("invalid_key")
        
        assert is_valid is False
        assert retrieved is None
    
    def test_validate_header_bearer(self):
        """Test Bearer token validation."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        raw_key, _ = auth.generate_key()
        
        is_valid, _ = auth.validate_header(f"Bearer {raw_key}")
        
        assert is_valid is True
    
    def test_validate_header_apikey(self):
        """Test ApiKey header validation."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        raw_key, _ = auth.generate_key()
        
        is_valid, _ = auth.validate_header(f"ApiKey {raw_key}")
        
        assert is_valid is True
    
    def test_revoke_key(self):
        """Test key revocation."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        raw_key, api_key = auth.generate_key()
        
        result = auth.revoke(api_key.key_id)
        
        assert result is True
        is_valid, _ = auth.validate(raw_key)
        assert is_valid is False
    
    def test_list_keys(self):
        """Test listing keys."""
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        
        auth = APIKeyAuth(allow_env_key=False)
        auth.generate_key(name="key1")
        auth.generate_key(name="key2")
        
        keys = auth.list_keys()
        
        assert len(keys) == 2
    
    def test_key_expiration(self, monkeypatch):
        """Test key expiration.
        
        Note: We mock time.time to simulate expiration instead of using
        time.sleep which is patched by fast_sleep fixture.
        """
        from praisonai.mcp_server.auth.api_key import APIKeyAuth
        import time
        
        # Track the current time for mocking
        current_time = [time.time()]
        
        auth = APIKeyAuth(allow_env_key=False)
        raw_key, api_key = auth.generate_key(expires_in=1)
        
        # Key should be valid initially
        is_valid, _ = auth.validate(raw_key)
        assert is_valid is True
        
        # Mock time.time to return a time after expiration
        def mock_time():
            return current_time[0] + 2  # 2 seconds later
        
        # Patch time.time in the api_key module
        import praisonai.mcp_server.auth.api_key as api_key_module
        monkeypatch.setattr(api_key_module.time, 'time', mock_time)
        
        # Key should be expired now
        is_valid, _ = auth.validate(raw_key)
        assert is_valid is False


class TestScopeManager:
    """Tests for ScopeManager class."""
    
    def test_validate_scopes_success(self):
        """Test successful scope validation."""
        from praisonai.mcp_server.auth.scopes import ScopeManager
        
        manager = ScopeManager()
        
        is_valid, challenge = manager.validate_scopes(
            required=["tools:read"],
            granted=["tools:read", "tools:call"],
        )
        
        assert is_valid is True
        assert challenge is None
    
    def test_validate_scopes_failure(self):
        """Test failed scope validation."""
        from praisonai.mcp_server.auth.scopes import ScopeManager
        
        manager = ScopeManager()
        
        is_valid, challenge = manager.validate_scopes(
            required=["admin"],
            granted=["tools:read"],
        )
        
        assert is_valid is False
        assert challenge is not None
        assert "admin" in challenge.missing_scopes
    
    def test_expand_scopes(self):
        """Test scope expansion."""
        from praisonai.mcp_server.auth.scopes import ScopeManager
        
        manager = ScopeManager()
        
        expanded = manager.expand_scopes(["tools:call"])
        
        assert "tools:call" in expanded
        assert "tools:read" in expanded  # tools:call implies tools:read
    
    def test_admin_scope_expansion(self):
        """Test admin scope expands to all scopes."""
        from praisonai.mcp_server.auth.scopes import ScopeManager
        
        manager = ScopeManager()
        
        expanded = manager.expand_scopes(["admin"])
        
        assert "admin" in expanded
        assert "tools:read" in expanded
        assert "tools:call" in expanded
        assert "resources:read" in expanded
    
    def test_check_scope(self):
        """Test single scope check."""
        from praisonai.mcp_server.auth.scopes import ScopeManager
        
        manager = ScopeManager()
        
        assert manager.check_scope("tools:read", ["tools:read"]) is True
        assert manager.check_scope("admin", ["tools:read"]) is False
    
    def test_scope_challenge_to_www_authenticate(self):
        """Test WWW-Authenticate header generation."""
        from praisonai.mcp_server.auth.scopes import ScopeChallenge
        
        challenge = ScopeChallenge(
            required_scopes=["admin"],
            granted_scopes=["tools:read"],
            missing_scopes=["admin"],
            error_description="Admin access required",
        )
        
        header = challenge.to_www_authenticate(realm="mcp-server")
        
        assert "Bearer" in header
        assert 'realm="mcp-server"' in header
        assert 'scope="admin"' in header


class TestScopeRequirement:
    """Tests for ScopeRequirement dataclass."""
    
    def test_all_scopes_required(self):
        """Test all scopes required."""
        from praisonai.mcp_server.auth.scopes import ScopeRequirement, ScopeManager
        
        manager = ScopeManager()
        requirement = ScopeRequirement(scopes=["tools:read", "resources:read"])
        
        is_valid, _ = requirement.check(["tools:read", "resources:read"], manager)
        
        assert is_valid is True
    
    def test_any_scope_sufficient(self):
        """Test any scope is sufficient."""
        from praisonai.mcp_server.auth.scopes import ScopeRequirement, ScopeManager
        
        manager = ScopeManager()
        requirement = ScopeRequirement(
            scopes=["tools:read", "resources:read"],
            any_of=True,
        )
        
        is_valid, _ = requirement.check(["tools:read"], manager)
        
        assert is_valid is True


class TestOAuthConfig:
    """Tests for OAuthConfig dataclass."""
    
    def test_oauth_config_creation(self):
        """Test OAuth config creation."""
        from praisonai.mcp_server.auth.oauth import OAuthConfig
        
        config = OAuthConfig(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="my-client",
        )
        
        assert config.authorization_endpoint == "https://auth.example.com/authorize"
        assert config.token_endpoint == "https://auth.example.com/token"
        assert config.client_id == "my-client"
        assert config.use_pkce is True  # Default
    
    def test_oauth_config_to_dict(self):
        """Test OAuth config serialization."""
        from praisonai.mcp_server.auth.oauth import OAuthConfig
        
        config = OAuthConfig(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="my-client",
            scopes=["openid", "profile"],
        )
        
        result = config.to_dict()
        
        assert result["client_id"] == "my-client"
        assert result["scopes"] == ["openid", "profile"]


class TestTokenResponse:
    """Tests for TokenResponse dataclass."""
    
    def test_token_response(self):
        """Test token response creation."""
        from praisonai.mcp_server.auth.oauth import TokenResponse
        
        token = TokenResponse(
            access_token="access123",
            token_type="Bearer",
            expires_in=3600,
        )
        
        assert token.access_token == "access123"
        assert token.token_type == "Bearer"
        assert token.expires_at is not None
    
    def test_token_not_expired(self):
        """Test token not expired."""
        from praisonai.mcp_server.auth.oauth import TokenResponse
        
        token = TokenResponse(
            access_token="access123",
            expires_in=3600,
        )
        
        assert token.is_expired() is False
    
    def test_token_expired(self):
        """Test token expired."""
        from praisonai.mcp_server.auth.oauth import TokenResponse
        import time
        
        token = TokenResponse(
            access_token="access123",
            expires_in=0,
        )
        token.expires_at = time.time() - 1  # Set to past
        
        assert token.is_expired() is True


class TestOAuthManager:
    """Tests for OAuthManager class."""
    
    def test_create_authorization_url(self):
        """Test authorization URL creation."""
        from praisonai.mcp_server.auth.oauth import OAuthConfig, OAuthManager
        
        config = OAuthConfig(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="my-client",
            default_scopes=["openid"],
        )
        manager = OAuthManager(config)
        
        url, request = manager.create_authorization_url()
        
        assert "https://auth.example.com/authorize" in url
        assert "client_id=my-client" in url
        assert "response_type=code" in url
        assert request.state is not None
    
    def test_create_authorization_url_with_pkce(self):
        """Test authorization URL with PKCE."""
        from praisonai.mcp_server.auth.oauth import OAuthConfig, OAuthManager
        
        config = OAuthConfig(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="my-client",
            use_pkce=True,
        )
        manager = OAuthManager(config)
        
        url, request = manager.create_authorization_url()
        
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert request.code_verifier is not None
    
    def test_www_authenticate_challenge(self):
        """Test WWW-Authenticate challenge creation."""
        from praisonai.mcp_server.auth.oauth import OAuthConfig, OAuthManager
        
        config = OAuthConfig(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="my-client",
            issuer="https://auth.example.com",
        )
        manager = OAuthManager(config)
        
        header = manager.create_www_authenticate_challenge(
            required_scopes=["admin"],
            error="insufficient_scope",
        )
        
        assert "Bearer" in header
        assert 'scope="admin"' in header
        assert 'error="insufficient_scope"' in header


class TestOIDCConfig:
    """Tests for OIDCConfig dataclass."""
    
    def test_oidc_config_creation(self):
        """Test OIDC config creation."""
        from praisonai.mcp_server.auth.oidc import OIDCConfig
        
        config = OIDCConfig(
            issuer="https://auth.example.com",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
        )
        
        assert config.issuer == "https://auth.example.com"
    
    def test_oidc_config_from_dict(self):
        """Test OIDC config from dictionary."""
        from praisonai.mcp_server.auth.oidc import OIDCConfig
        
        data = {
            "issuer": "https://auth.example.com",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "scopes_supported": ["openid", "profile"],
        }
        
        config = OIDCConfig.from_dict(data)
        
        assert config.issuer == "https://auth.example.com"
        assert config.scopes_supported == ["openid", "profile"]


class TestClientMetadata:
    """Tests for ClientMetadata dataclass."""
    
    def test_client_metadata_creation(self):
        """Test client metadata creation."""
        from praisonai.mcp_server.auth.oidc import ClientMetadata
        
        metadata = ClientMetadata(
            client_id="my-client",
            client_name="My Application",
            redirect_uris=["http://localhost:8080/callback"],
        )
        
        assert metadata.client_id == "my-client"
        assert metadata.client_name == "My Application"
    
    def test_client_metadata_to_dict(self):
        """Test client metadata serialization."""
        from praisonai.mcp_server.auth.oidc import ClientMetadata
        
        metadata = ClientMetadata(
            client_id="my-client",
            client_name="My App",
        )
        
        result = metadata.to_dict()
        
        assert result["client_id"] == "my-client"
        assert result["client_name"] == "My App"
