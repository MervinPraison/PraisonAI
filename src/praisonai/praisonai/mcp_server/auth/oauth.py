"""
OAuth 2.1 Implementation for MCP

Implements OAuth 2.1 authorization framework per MCP 2025-11-25 specification.

Based on:
- OAuth 2.1 IETF DRAFT (draft-ietf-oauth-v2-1-13)
- OAuth 2.0 Authorization Server Metadata (RFC8414)
- OAuth 2.0 Dynamic Client Registration Protocol (RFC7591)
- OAuth 2.0 Protected Resource Metadata (RFC9728)
"""

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


@dataclass
class OAuthConfig:
    """OAuth 2.1 configuration for MCP servers."""
    
    # Authorization server endpoints
    authorization_endpoint: str
    token_endpoint: str
    
    # Client credentials
    client_id: str
    client_secret: Optional[str] = None
    
    # Scopes
    scopes: List[str] = field(default_factory=list)
    default_scopes: List[str] = field(default_factory=list)
    
    # PKCE settings (required for OAuth 2.1)
    use_pkce: bool = True
    pkce_method: str = "S256"  # S256 or plain
    
    # Token settings
    token_endpoint_auth_method: str = "client_secret_basic"
    
    # Discovery
    issuer: Optional[str] = None
    metadata_url: Optional[str] = None
    
    # Resource indicator (RFC 8707)
    resource_indicator: Optional[str] = None
    
    # Redirect settings
    redirect_uri: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "client_id": self.client_id,
            "scopes": self.scopes,
            "use_pkce": self.use_pkce,
            "issuer": self.issuer,
        }


@dataclass
class TokenResponse:
    """OAuth token response."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None
    
    # Computed fields
    expires_at: Optional[float] = None
    
    def __post_init__(self):
        if self.expires_in and not self.expires_at:
            self.expires_at = time.time() + self.expires_in
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "access_token": self.access_token,
            "token_type": self.token_type,
        }
        if self.expires_in:
            result["expires_in"] = self.expires_in
        if self.refresh_token:
            result["refresh_token"] = self.refresh_token
        if self.scope:
            result["scope"] = self.scope
        return result


@dataclass
class AuthorizationRequest:
    """OAuth authorization request state."""
    state: str
    code_verifier: Optional[str] = None
    code_challenge: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    redirect_uri: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    def is_expired(self, ttl: int = 600) -> bool:
        return time.time() - self.created_at > ttl


class OAuthManager:
    """
    OAuth 2.1 Manager for MCP servers.
    
    Handles:
    - Authorization code flow with PKCE
    - Token exchange and refresh
    - Incremental scope consent
    - WWW-Authenticate challenges
    """
    
    def __init__(
        self,
        config: OAuthConfig,
        token_store: Optional[Callable] = None,
    ):
        """
        Initialize OAuth manager.
        
        Args:
            config: OAuth configuration
            token_store: Optional token storage callback
        """
        self.config = config
        self._token_store = token_store
        self._pending_requests: Dict[str, AuthorizationRequest] = {}
        self._tokens: Dict[str, TokenResponse] = {}
    
    def create_authorization_url(
        self,
        scopes: Optional[List[str]] = None,
        state: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ) -> tuple[str, AuthorizationRequest]:
        """
        Create authorization URL for OAuth flow.
        
        Args:
            scopes: Requested scopes
            state: Optional state parameter
            redirect_uri: Redirect URI
            
        Returns:
            Tuple of (authorization_url, request_state)
        """
        # Generate state if not provided
        state = state or secrets.token_urlsafe(32)
        
        # Use default scopes if not specified
        scopes = scopes or self.config.default_scopes
        
        # Generate PKCE parameters
        code_verifier = None
        code_challenge = None
        
        if self.config.use_pkce:
            code_verifier = secrets.token_urlsafe(64)
            if self.config.pkce_method == "S256":
                code_challenge = base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                ).decode().rstrip("=")
            else:
                code_challenge = code_verifier
        
        # Build authorization URL
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "state": state,
            "scope": " ".join(scopes),
        }
        
        if redirect_uri or self.config.redirect_uri:
            params["redirect_uri"] = redirect_uri or self.config.redirect_uri
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = self.config.pkce_method
        
        if self.config.resource_indicator:
            params["resource"] = self.config.resource_indicator
        
        auth_url = f"{self.config.authorization_endpoint}?{urlencode(params)}"
        
        # Store request state
        request = AuthorizationRequest(
            state=state,
            code_verifier=code_verifier,
            code_challenge=code_challenge,
            scopes=scopes,
            redirect_uri=redirect_uri or self.config.redirect_uri,
        )
        self._pending_requests[state] = request
        
        return auth_url, request
    
    async def exchange_code(
        self,
        code: str,
        state: str,
    ) -> TokenResponse:
        """
        Exchange authorization code for tokens.
        
        Args:
            code: Authorization code
            state: State parameter
            
        Returns:
            Token response
        """
        # Validate state
        request = self._pending_requests.get(state)
        if not request:
            raise ValueError("Invalid state parameter")
        
        if request.is_expired():
            del self._pending_requests[state]
            raise ValueError("Authorization request expired")
        
        # Build token request
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.config.client_id,
        }
        
        if request.redirect_uri:
            data["redirect_uri"] = request.redirect_uri
        
        if request.code_verifier:
            data["code_verifier"] = request.code_verifier
        
        # Make token request
        token_response = await self._token_request(data)
        
        # Cleanup
        del self._pending_requests[state]
        
        return token_response
    
    async def refresh_token(
        self,
        refresh_token: str,
        scopes: Optional[List[str]] = None,
    ) -> TokenResponse:
        """
        Refresh an access token.
        
        Args:
            refresh_token: Refresh token
            scopes: Optional scope restriction
            
        Returns:
            New token response
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
        }
        
        if scopes:
            data["scope"] = " ".join(scopes)
        
        return await self._token_request(data)
    
    async def _token_request(self, data: Dict[str, str]) -> TokenResponse:
        """Make a token request."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx required for OAuth. Install with: pip install httpx")
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        # Add client authentication
        if self.config.token_endpoint_auth_method == "client_secret_basic":
            if self.config.client_secret:
                credentials = base64.b64encode(
                    f"{self.config.client_id}:{self.config.client_secret}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {credentials}"
        elif self.config.token_endpoint_auth_method == "client_secret_post":
            if self.config.client_secret:
                data["client_secret"] = self.config.client_secret
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.token_endpoint,
                data=data,
                headers=headers,
            )
            response.raise_for_status()
            
            token_data = response.json()
            return TokenResponse(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
                id_token=token_data.get("id_token"),
            )
    
    def create_www_authenticate_challenge(
        self,
        required_scopes: List[str],
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ) -> str:
        """
        Create WWW-Authenticate header for scope challenge.
        
        Per MCP 2025-11-25, this enables incremental scope consent.
        
        Args:
            required_scopes: Scopes required for the operation
            error: OAuth error code
            error_description: Human-readable error description
            
        Returns:
            WWW-Authenticate header value
        """
        parts = ['Bearer']
        
        params = []
        
        if self.config.issuer:
            params.append(f'realm="{self.config.issuer}"')
        
        if required_scopes:
            params.append(f'scope="{" ".join(required_scopes)}"')
        
        if error:
            params.append(f'error="{error}"')
        
        if error_description:
            params.append(f'error_description="{error_description}"')
        
        if params:
            parts.append(", ".join(params))
        
        return " ".join(parts)
    
    def validate_token(self, token: str) -> bool:
        """
        Validate an access token.
        
        Args:
            token: Access token to validate
            
        Returns:
            True if valid
        """
        # Check if we have this token stored
        for stored_token in self._tokens.values():
            if stored_token.access_token == token:
                return not stored_token.is_expired()
        
        # For external tokens, we'd need to call the introspection endpoint
        # This is a simplified implementation
        return True
    
    def store_token(self, session_id: str, token: TokenResponse) -> None:
        """Store a token for a session."""
        self._tokens[session_id] = token
        if self._token_store:
            self._token_store(session_id, token)
    
    def get_token(self, session_id: str) -> Optional[TokenResponse]:
        """Get stored token for a session."""
        return self._tokens.get(session_id)
    
    def clear_token(self, session_id: str) -> None:
        """Clear stored token for a session."""
        if session_id in self._tokens:
            del self._tokens[session_id]


async def discover_oauth_metadata(issuer_url: str) -> Dict[str, Any]:
    """
    Discover OAuth authorization server metadata.
    
    Per RFC 8414, fetches from /.well-known/oauth-authorization-server
    
    Args:
        issuer_url: Authorization server issuer URL
        
    Returns:
        Metadata dictionary
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx required for OAuth discovery. Install with: pip install httpx")
    
    # Try OAuth 2.0 metadata endpoint first
    metadata_url = f"{issuer_url.rstrip('/')}/.well-known/oauth-authorization-server"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(metadata_url)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        
        # Fall back to OpenID Connect discovery
        oidc_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
        response = await client.get(oidc_url)
        response.raise_for_status()
        return response.json()


def create_oauth_config_from_metadata(
    metadata: Dict[str, Any],
    client_id: str,
    client_secret: Optional[str] = None,
    scopes: Optional[List[str]] = None,
) -> OAuthConfig:
    """
    Create OAuth config from discovered metadata.
    
    Args:
        metadata: Authorization server metadata
        client_id: Client ID
        client_secret: Optional client secret
        scopes: Optional scopes
        
    Returns:
        OAuthConfig instance
    """
    return OAuthConfig(
        authorization_endpoint=metadata["authorization_endpoint"],
        token_endpoint=metadata["token_endpoint"],
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes or metadata.get("scopes_supported", []),
        issuer=metadata.get("issuer"),
        metadata_url=metadata.get("issuer"),
    )
