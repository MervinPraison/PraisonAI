"""
OpenID Connect Discovery Implementation

Implements OpenID Connect Discovery 1.0 per MCP 2025-11-25 specification.

Based on:
- OpenID Connect Discovery 1.0
- OAuth 2.0 Authorization Server Metadata (RFC8414)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OIDCConfig:
    """OpenID Connect configuration."""
    
    # Required endpoints
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    
    # Optional endpoints
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    registration_endpoint: Optional[str] = None
    revocation_endpoint: Optional[str] = None
    introspection_endpoint: Optional[str] = None
    end_session_endpoint: Optional[str] = None
    
    # Supported features
    scopes_supported: List[str] = field(default_factory=list)
    response_types_supported: List[str] = field(default_factory=list)
    grant_types_supported: List[str] = field(default_factory=list)
    subject_types_supported: List[str] = field(default_factory=list)
    id_token_signing_alg_values_supported: List[str] = field(default_factory=list)
    token_endpoint_auth_methods_supported: List[str] = field(default_factory=list)
    claims_supported: List[str] = field(default_factory=list)
    code_challenge_methods_supported: List[str] = field(default_factory=list)
    
    # Cache metadata
    _fetched_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "jwks_uri": self.jwks_uri,
            "scopes_supported": self.scopes_supported,
            "response_types_supported": self.response_types_supported,
            "grant_types_supported": self.grant_types_supported,
            "token_endpoint_auth_methods_supported": self.token_endpoint_auth_methods_supported,
            "code_challenge_methods_supported": self.code_challenge_methods_supported,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OIDCConfig":
        return cls(
            issuer=data["issuer"],
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            userinfo_endpoint=data.get("userinfo_endpoint"),
            jwks_uri=data.get("jwks_uri"),
            registration_endpoint=data.get("registration_endpoint"),
            revocation_endpoint=data.get("revocation_endpoint"),
            introspection_endpoint=data.get("introspection_endpoint"),
            end_session_endpoint=data.get("end_session_endpoint"),
            scopes_supported=data.get("scopes_supported", []),
            response_types_supported=data.get("response_types_supported", []),
            grant_types_supported=data.get("grant_types_supported", []),
            subject_types_supported=data.get("subject_types_supported", []),
            id_token_signing_alg_values_supported=data.get("id_token_signing_alg_values_supported", []),
            token_endpoint_auth_methods_supported=data.get("token_endpoint_auth_methods_supported", []),
            claims_supported=data.get("claims_supported", []),
            code_challenge_methods_supported=data.get("code_challenge_methods_supported", []),
            _fetched_at=time.time(),
        )


class OIDCDiscovery:
    """
    OpenID Connect Discovery client.
    
    Fetches and caches OIDC configuration from well-known endpoints.
    """
    
    def __init__(
        self,
        cache_ttl: int = 3600,
    ):
        """
        Initialize OIDC discovery client.
        
        Args:
            cache_ttl: Cache TTL in seconds
        """
        self._cache: Dict[str, OIDCConfig] = {}
        self._cache_ttl = cache_ttl
    
    async def discover(self, issuer: str, force_refresh: bool = False) -> OIDCConfig:
        """
        Discover OIDC configuration for an issuer.
        
        Args:
            issuer: Issuer URL
            force_refresh: Force cache refresh
            
        Returns:
            OIDCConfig instance
        """
        # Check cache
        if not force_refresh and issuer in self._cache:
            config = self._cache[issuer]
            if config._fetched_at and time.time() - config._fetched_at < self._cache_ttl:
                return config
        
        # Fetch configuration
        config = await self._fetch_config(issuer)
        self._cache[issuer] = config
        
        return config
    
    async def _fetch_config(self, issuer: str) -> OIDCConfig:
        """Fetch OIDC configuration from well-known endpoint."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx required for OIDC discovery. Install with: pip install httpx")
        
        # Build well-known URL
        discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url, follow_redirects=True)
            response.raise_for_status()
            
            data = response.json()
            
            # Validate issuer matches
            if data.get("issuer") != issuer and data.get("issuer") != issuer.rstrip("/"):
                logger.warning(f"Issuer mismatch: expected {issuer}, got {data.get('issuer')}")
            
            return OIDCConfig.from_dict(data)
    
    def get_cached(self, issuer: str) -> Optional[OIDCConfig]:
        """Get cached configuration without fetching."""
        return self._cache.get(issuer)
    
    def clear_cache(self, issuer: Optional[str] = None) -> None:
        """Clear cached configurations."""
        if issuer:
            if issuer in self._cache:
                del self._cache[issuer]
        else:
            self._cache.clear()


@dataclass
class ClientMetadata:
    """
    OAuth Client ID Metadata Document.
    
    Per draft-ietf-oauth-client-id-metadata-document-00
    """
    client_id: str
    client_name: Optional[str] = None
    client_uri: Optional[str] = None
    logo_uri: Optional[str] = None
    contacts: List[str] = field(default_factory=list)
    tos_uri: Optional[str] = None
    policy_uri: Optional[str] = None
    
    # Redirect URIs
    redirect_uris: List[str] = field(default_factory=list)
    
    # Grant types
    grant_types: List[str] = field(default_factory=lambda: ["authorization_code"])
    response_types: List[str] = field(default_factory=lambda: ["code"])
    
    # Token endpoint auth
    token_endpoint_auth_method: str = "client_secret_basic"
    
    # Scopes
    scope: Optional[str] = None
    
    # Software statement
    software_id: Optional[str] = None
    software_version: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"client_id": self.client_id}
        
        if self.client_name:
            result["client_name"] = self.client_name
        if self.client_uri:
            result["client_uri"] = self.client_uri
        if self.logo_uri:
            result["logo_uri"] = self.logo_uri
        if self.contacts:
            result["contacts"] = self.contacts
        if self.redirect_uris:
            result["redirect_uris"] = self.redirect_uris
        if self.grant_types:
            result["grant_types"] = self.grant_types
        if self.response_types:
            result["response_types"] = self.response_types
        if self.token_endpoint_auth_method:
            result["token_endpoint_auth_method"] = self.token_endpoint_auth_method
        if self.scope:
            result["scope"] = self.scope
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientMetadata":
        return cls(
            client_id=data["client_id"],
            client_name=data.get("client_name"),
            client_uri=data.get("client_uri"),
            logo_uri=data.get("logo_uri"),
            contacts=data.get("contacts", []),
            tos_uri=data.get("tos_uri"),
            policy_uri=data.get("policy_uri"),
            redirect_uris=data.get("redirect_uris", []),
            grant_types=data.get("grant_types", ["authorization_code"]),
            response_types=data.get("response_types", ["code"]),
            token_endpoint_auth_method=data.get("token_endpoint_auth_method", "client_secret_basic"),
            scope=data.get("scope"),
            software_id=data.get("software_id"),
            software_version=data.get("software_version"),
        )


async def fetch_client_metadata(client_id_url: str) -> ClientMetadata:
    """
    Fetch OAuth Client ID Metadata Document.
    
    Per draft-ietf-oauth-client-id-metadata-document-00
    
    Args:
        client_id_url: URL of the client ID metadata document
        
    Returns:
        ClientMetadata instance
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx required for client metadata. Install with: pip install httpx")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(client_id_url, follow_redirects=True)
        response.raise_for_status()
        
        data = response.json()
        return ClientMetadata.from_dict(data)


async def fetch_protected_resource_metadata(resource_url: str) -> Dict[str, Any]:
    """
    Fetch OAuth 2.0 Protected Resource Metadata.
    
    Per RFC 9728
    
    Args:
        resource_url: URL of the protected resource
        
    Returns:
        Metadata dictionary
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx required for resource metadata. Install with: pip install httpx")
    
    # Build well-known URL
    metadata_url = f"{resource_url.rstrip('/')}/.well-known/oauth-protected-resource"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(metadata_url, follow_redirects=True)
        response.raise_for_status()
        return response.json()
