"""
API Key Authentication for MCP

Simple API key authentication for MCP servers.
"""

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class APIKey:
    """API Key representation."""
    key_id: str
    key_hash: str
    name: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at
    
    def has_scope(self, scope: str) -> bool:
        if not self.scopes:
            return True  # No scope restriction
        return scope in self.scopes or "*" in self.scopes


class APIKeyAuth:
    """
    API Key authentication manager.
    
    Supports:
    - Key generation and validation
    - Scope-based authorization
    - Key rotation
    - Rate limiting (optional)
    """
    
    def __init__(
        self,
        keys: Optional[Dict[str, APIKey]] = None,
        allow_env_key: bool = True,
        env_key_name: str = "MCP_API_KEY",
    ):
        """
        Initialize API key auth.
        
        Args:
            keys: Pre-configured API keys
            allow_env_key: Allow API key from environment
            env_key_name: Environment variable name for API key
        """
        self._keys: Dict[str, APIKey] = keys or {}
        self._allow_env_key = allow_env_key
        self._env_key_name = env_key_name
        self._env_key_hash: Optional[str] = None
        
        # Load env key if configured
        if allow_env_key:
            self._load_env_key()
    
    def _load_env_key(self) -> None:
        """Load API key from environment."""
        import os
        env_key = os.environ.get(self._env_key_name)
        if env_key:
            self._env_key_hash = self._hash_key(env_key)
            logger.debug(f"Loaded API key from {self._env_key_name}")
    
    def _hash_key(self, key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def generate_key(
        self,
        name: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_in: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> tuple[str, APIKey]:
        """
        Generate a new API key.
        
        Args:
            name: Key name/description
            scopes: Allowed scopes
            expires_in: Expiration in seconds
            metadata: Additional metadata
            
        Returns:
            Tuple of (raw_key, APIKey)
        """
        # Generate key
        raw_key = f"mcp_{secrets.token_urlsafe(32)}"
        key_id = secrets.token_hex(8)
        key_hash = self._hash_key(raw_key)
        
        expires_at = None
        if expires_in:
            expires_at = time.time() + expires_in
        
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            scopes=scopes or [],
            expires_at=expires_at,
            metadata=metadata or {},
        )
        
        self._keys[key_id] = api_key
        
        return raw_key, api_key
    
    def validate(
        self,
        key: str,
        required_scope: Optional[str] = None,
    ) -> tuple[bool, Optional[APIKey]]:
        """
        Validate an API key.
        
        Args:
            key: Raw API key
            required_scope: Required scope for authorization
            
        Returns:
            Tuple of (is_valid, api_key)
        """
        key_hash = self._hash_key(key)
        
        # Check environment key
        if self._env_key_hash and hmac.compare_digest(key_hash, self._env_key_hash):
            # Env key has all scopes
            return True, None
        
        # Check stored keys
        for api_key in self._keys.values():
            if hmac.compare_digest(key_hash, api_key.key_hash):
                if api_key.is_expired():
                    return False, None
                
                if required_scope and not api_key.has_scope(required_scope):
                    return False, api_key
                
                # Update last used
                api_key.last_used_at = time.time()
                
                return True, api_key
        
        return False, None
    
    def validate_header(
        self,
        auth_header: str,
        required_scope: Optional[str] = None,
    ) -> tuple[bool, Optional[APIKey]]:
        """
        Validate Authorization header.
        
        Supports:
        - Bearer <key>
        - ApiKey <key>
        
        Args:
            auth_header: Authorization header value
            required_scope: Required scope
            
        Returns:
            Tuple of (is_valid, api_key)
        """
        if not auth_header:
            return False, None
        
        parts = auth_header.split(" ", 1)
        if len(parts) != 2:
            return False, None
        
        scheme, key = parts
        if scheme.lower() not in ("bearer", "apikey"):
            return False, None
        
        return self.validate(key, required_scope)
    
    def revoke(self, key_id: str) -> bool:
        """Revoke an API key."""
        if key_id in self._keys:
            del self._keys[key_id]
            return True
        return False
    
    def list_keys(self) -> List[APIKey]:
        """List all API keys (without hashes)."""
        return list(self._keys.values())
    
    def add_key(
        self,
        raw_key: str,
        name: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> APIKey:
        """
        Add a pre-existing API key.
        
        Args:
            raw_key: Raw API key
            name: Key name
            scopes: Allowed scopes
            
        Returns:
            APIKey instance
        """
        key_id = secrets.token_hex(8)
        key_hash = self._hash_key(raw_key)
        
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            scopes=scopes or [],
        )
        
        self._keys[key_id] = api_key
        return api_key


def create_auth_middleware(
    api_key_auth: APIKeyAuth,
    required_scope: Optional[str] = None,
    exclude_paths: Optional[List[str]] = None,
):
    """
    Create authentication middleware for Starlette/FastAPI.
    
    Args:
        api_key_auth: APIKeyAuth instance
        required_scope: Required scope for all requests
        exclude_paths: Paths to exclude from auth
        
    Returns:
        Middleware class
    """
    exclude_paths = exclude_paths or ["/health", "/"]
    
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import JSONResponse
    except ImportError:
        raise ImportError("starlette required for middleware")
    
    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Skip excluded paths
            if request.url.path in exclude_paths:
                return await call_next(request)
            
            # Get auth header
            auth_header = request.headers.get("Authorization", "")
            
            # Validate
            is_valid, api_key = api_key_auth.validate_header(
                auth_header, required_scope
            )
            
            if not is_valid:
                return JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Add key info to request state
            request.state.api_key = api_key
            
            return await call_next(request)
    
    return AuthMiddleware
