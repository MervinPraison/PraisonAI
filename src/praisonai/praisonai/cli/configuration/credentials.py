"""
Secure credential storage for PraisonAI CLI.

Provides a centralized, secure way to store and retrieve API keys and
provider credentials with proper file permissions and JSON format.
"""

import json
import os
import stat
import time
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict, field
import tempfile


@dataclass
class ProviderCredential:
    """A single provider's credential information.

    Supports two authentication methods:
    - ``apikey`` (default): a static ``api_key`` is stored.
    - ``oauth``: short-lived ``access_token``/``refresh_token`` with an
      ``expires_at`` epoch timestamp are stored and refreshed on demand.
    """
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    auth_method: str = "apikey"
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[float] = None
    token_url: Optional[str] = None
    client_id: Optional[str] = None
    scope: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_oauth(self) -> bool:
        """Return True if this credential uses the OAuth/device-code method."""
        return self.auth_method == "oauth"

    def is_expired(self, leeway: float = 60.0) -> bool:
        """Return True if an OAuth access token is expired (or about to be).

        Args:
            leeway: Seconds before the actual expiry to treat as expired so a
                refresh happens before the token stops working mid-request.
        """
        if not self.is_oauth() or not self.expires_at:
            return False
        return self.expires_at <= (time.time() + leeway)


class CredentialStore:
    """
    Secure credential storage with atomic writes and proper permissions.
    
    Stores credentials in ~/.praison/credentials.json with 0o600 permissions
    for security. All write operations are atomic to prevent corruption.
    """
    
    def __init__(self, credentials_path: Optional[Path] = None):
        """
        Initialize credential store.
        
        Args:
            credentials_path: Optional custom path for credentials file.
                             Defaults to ~/.praison/credentials.json
        """
        if credentials_path:
            self.credentials_path = credentials_path
        else:
            home = Path.home()
            self.credentials_path = home / ".praison" / "credentials.json"
    
    def _ensure_directory_exists(self) -> None:
        """Ensure parent directory exists, creating it if necessary."""
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _read_credentials(self) -> Dict[str, Dict[str, Any]]:
        """Read and parse credentials file."""
        try:
            if not self.credentials_path.exists():
                return {}
            
            # Check file permissions for security
            file_stat = self.credentials_path.stat()
            if file_stat.st_mode & 0o077:  # Check if group/other have any permissions
                # Fix permissions automatically
                os.chmod(self.credentials_path, 0o600)
            
            with open(self.credentials_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):
            # Return empty dict on any read error
            return {}
    
    def _write_credentials(self, credentials: Dict[str, Dict[str, Any]]) -> None:
        """Write credentials to file atomically with proper permissions."""
        # Ensure parent directory exists before writing
        self._ensure_directory_exists()
        
        # Use atomic write: write to temp file, then rename
        temp_fd = None
        temp_path = None
        
        try:
            # Create temporary file in same directory for atomic rename
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.credentials_path.parent,
                prefix='.credentials_tmp_'
            )
            
            # Set proper permissions before writing (user read/write only)
            os.chmod(temp_path, 0o600)
            
            # Write JSON data
            # Transfer ownership to the file object; clear fd so the except
            # handler won't attempt a double-close if json.dump raises.
            f = os.fdopen(temp_fd, 'w')
            temp_fd = None
            with f:
                json.dump(credentials, f, indent=2)
            
            # Atomic rename (os.replace handles existing dest on Windows)
            os.replace(temp_path, self.credentials_path)
            temp_path = None  # Successfully moved
            
        except Exception:
            # Clean up on error
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            if temp_path is not None and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            raise
    
    def store_credential(self, provider: str, api_key: str, 
                        base_url: Optional[str] = None,
                        model: Optional[str] = None,
                        **metadata) -> None:
        """
        Store a credential for a provider.
        
        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
            api_key: API key to store
            base_url: Optional base URL for the provider
            model: Optional default model for the provider
            **metadata: Additional metadata to store
        """
        credentials = self._read_credentials()
        
        credentials[provider] = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "auth_method": "apikey",
            **metadata
        }
        
        self._write_credentials(credentials)

    def store_oauth_credential(
        self,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[float] = None,
        token_url: Optional[str] = None,
        client_id: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **metadata,
    ) -> None:
        """
        Store OAuth/device-code credentials for a provider.

        The ``access_token`` is also mirrored into ``api_key`` so existing
        readers that only know about ``api_key`` keep working transparently.

        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
            access_token: Short-lived OAuth access token
            refresh_token: Optional refresh token for renewing the access token
            expires_at: Optional epoch timestamp when the access token expires
            token_url: Optional token endpoint used for refresh
            client_id: Optional OAuth client id used for refresh
            scope: Optional granted scope string
            base_url: Optional base URL for the provider
            model: Optional default model for the provider
            **metadata: Additional metadata to store
        """
        credentials = self._read_credentials()

        credentials[provider] = {
            "api_key": access_token,
            "base_url": base_url,
            "model": model,
            "auth_method": "oauth",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "token_url": token_url,
            "client_id": client_id,
            "scope": scope,
            **metadata,
        }

        self._write_credentials(credentials)
    
    def get_credential(self, provider: str) -> Optional[ProviderCredential]:
        """
        Retrieve a credential for a provider.
        
        Args:
            provider: Provider name
            
        Returns:
            ProviderCredential if found, None otherwise
        """
        credentials = self._read_credentials()
        
        if provider not in credentials:
            return None
        
        cred_data = credentials[provider]
        
        # Extract known fields
        api_key = cred_data.get("api_key")
        if not api_key:
            return None
        
        base_url = cred_data.get("base_url")
        model = cred_data.get("model")
        auth_method = cred_data.get("auth_method", "apikey")
        access_token = cred_data.get("access_token")
        refresh_token = cred_data.get("refresh_token")
        expires_at = cred_data.get("expires_at")
        token_url = cred_data.get("token_url")
        client_id = cred_data.get("client_id")
        scope = cred_data.get("scope")
        
        # Known fields are extracted explicitly; the rest is metadata.
        _known = (
            "api_key", "base_url", "model", "auth_method", "access_token",
            "refresh_token", "expires_at", "token_url", "client_id", "scope",
        )
        metadata = {
            k: v for k, v in cred_data.items() 
            if k not in _known
        }
        
        return ProviderCredential(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            auth_method=auth_method,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_url=token_url,
            client_id=client_id,
            scope=scope,
            metadata=metadata
        )
    
    def remove_credential(self, provider: str) -> bool:
        """
        Remove a credential for a provider.
        
        Args:
            provider: Provider name
            
        Returns:
            True if credential was removed, False if not found
        """
        credentials = self._read_credentials()
        
        if provider not in credentials:
            return False
        
        del credentials[provider]
        self._write_credentials(credentials)
        return True
    
    def list_providers(self) -> list[str]:
        """List all stored provider names."""
        credentials = self._read_credentials()
        return list(credentials.keys())
    
    def has_credential(self, provider: str) -> bool:
        """Check if a credential exists for a provider."""
        credentials = self._read_credentials()
        return provider in credentials and credentials[provider].get("api_key")
    
    def clear_all(self) -> None:
        """Remove all stored credentials."""
        self._write_credentials({})

    def get_valid_token(self, provider: str) -> Optional[str]:
        """
        Return a currently-valid secret for a provider, refreshing if needed.

        For ``apikey`` credentials this is simply the stored key. For ``oauth``
        credentials, an expired access token is transparently refreshed (when a
        refresh token + token endpoint are available) and the refreshed token is
        persisted before being returned.

        Returns:
            A usable token/key string, or None if nothing is available.
        """
        cred = self.get_credential(provider)
        if not cred:
            return None

        if not cred.is_oauth():
            return cred.api_key

        if not cred.is_expired():
            return cred.access_token or cred.api_key

        # Token is expired: attempt a refresh.
        refreshed = self._refresh_oauth_token(cred)
        if refreshed:
            return refreshed
        # Refresh failed; return the (possibly stale) token as a last resort.
        return cred.access_token or cred.api_key

    def _refresh_oauth_token(self, cred: ProviderCredential) -> Optional[str]:
        """
        Refresh an OAuth access token using the stored refresh token.

        Persists the new token set on success. Returns the new access token, or
        None if a refresh could not be performed.
        """
        if not (cred.refresh_token and cred.token_url):
            return None

        try:
            import requests  # lazy, optional dependency
        except ImportError:
            return None

        data = {
            "grant_type": "refresh_token",
            "refresh_token": cred.refresh_token,
        }
        if cred.client_id:
            data["client_id"] = cred.client_id

        try:
            resp = requests.post(cred.token_url, data=data, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            return None

        access_token = payload.get("access_token")
        if not access_token:
            return None

        expires_in = payload.get("expires_in")
        expires_at = (time.time() + float(expires_in)) if expires_in else None

        self.store_oauth_credential(
            provider=cred.provider,
            access_token=access_token,
            # Providers may rotate refresh tokens; keep the old one otherwise.
            refresh_token=payload.get("refresh_token") or cred.refresh_token,
            expires_at=expires_at,
            token_url=cred.token_url,
            client_id=cred.client_id,
            scope=payload.get("scope") or cred.scope,
            base_url=cred.base_url,
            model=cred.model,
            **(cred.metadata or {}),
        )
        return access_token


def redact_key(api_key: str, show_chars: int = 4) -> str:
    """
    Redact an API key for safe display.
    
    Args:
        api_key: The API key to redact
        show_chars: Number of characters to show at start and end
        
    Returns:
        Redacted key like "sk-12***34"
    """
    if len(api_key) <= show_chars * 2:
        return "*" * len(api_key)
    
    return (
        api_key[:show_chars] + 
        "*" * (len(api_key) - show_chars * 2) + 
        api_key[-show_chars:]
    )


def validate_api_key(provider: str, api_key: str) -> tuple[bool, str]:
    """
    Validate API key format for known providers.
    
    Args:
        provider: Provider name
        api_key: API key to validate
        
    Returns:
        Tuple of (is_valid, message)
    """
    # Known API key patterns
    patterns = {
        "openai": {"prefix": "sk-", "min_length": 20},
        "anthropic": {"prefix": "sk-ant-", "min_length": 20},
        "google": {"prefix": "AI", "min_length": 20},
        "gemini": {"prefix": "AI", "min_length": 20},
        "tavily": {"prefix": "tvly-", "min_length": 20},
        "groq": {"prefix": "gsk_", "min_length": 20},
    }
    
    pattern = patterns.get(provider.lower())
    if not pattern:
        # Unknown provider - basic length check only
        return len(api_key) >= 10, "Unknown provider format"
    
    if len(api_key) < pattern["min_length"]:
        return False, f"Too short (expected >= {pattern['min_length']} chars)"
    
    if pattern.get("prefix") and not api_key.startswith(pattern["prefix"]):
        return False, f"Invalid prefix (expected {pattern['prefix']}...)"
    
    return True, "Valid format"