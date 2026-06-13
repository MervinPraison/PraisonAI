"""
Secure credential storage for PraisonAI CLI.

Provides a centralized, secure way to store and retrieve API keys and
provider credentials with proper file permissions and JSON format.
"""

import json
import os
import stat
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict, field
import tempfile


@dataclass
class ProviderCredential:
    """A single provider's credential information."""
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


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
            
            # Atomic rename
            os.rename(temp_path, self.credentials_path)
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
            **metadata
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
        
        # Everything else goes into metadata
        metadata = {
            k: v for k, v in cred_data.items() 
            if k not in ("api_key", "base_url", "model")
        }
        
        return ProviderCredential(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
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