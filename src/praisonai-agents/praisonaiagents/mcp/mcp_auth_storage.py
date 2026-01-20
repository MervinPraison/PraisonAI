"""
MCP Authentication Storage.

This module provides persistent storage for OAuth tokens and client information
for MCP servers. It handles:
- Access/refresh token storage
- Client registration info (for dynamic registration)
- PKCE code verifiers
- OAuth state for CSRF protection

Storage is file-based with restricted permissions (0600) for security.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


def get_default_auth_filepath() -> str:
    """
    Get the default filepath for MCP auth storage.
    
    Returns:
        Path to mcp-auth.json in user's praison config directory
    """
    # Use ~/.praison/ directory for config
    home = Path.home()
    praison_dir = home / ".praison"
    praison_dir.mkdir(parents=True, exist_ok=True)
    return str(praison_dir / "mcp-auth.json")


class MCPAuthStorage:
    """
    Persistent storage for MCP OAuth credentials.
    
    This class manages storage of OAuth tokens, client information,
    and temporary OAuth flow data (code verifiers, state) for MCP servers.
    
    Example:
        ```python
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
        
        storage = MCPAuthStorage()
        
        # Store tokens after OAuth flow
        storage.set_tokens("github", {
            "access_token": "gho_xxx",
            "refresh_token": "ghr_xxx",
            "expires_at": 1234567890
        }, server_url="https://api.github.com/mcp")
        
        # Check if authenticated
        entry = storage.get("github")
        if entry and entry.get("tokens"):
            print("Authenticated!")
        ```
    """
    
    def __init__(self, filepath: Optional[str] = None):
        """
        Initialize auth storage.
        
        Args:
            filepath: Path to auth storage file. Defaults to ~/.praison/mcp-auth.json
        """
        self.filepath = filepath or get_default_auth_filepath()
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """Ensure the parent directory exists."""
        parent = Path(self.filepath).parent
        parent.mkdir(parents=True, exist_ok=True)
    
    def _read(self) -> Dict[str, Any]:
        """Read all entries from storage file."""
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _write(self, data: Dict[str, Any]) -> None:
        """Write all entries to storage file with secure permissions."""
        # Write to file
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Set file permissions to 0600 (owner read/write only)
        if os.name != 'nt':  # Unix-like systems
            os.chmod(self.filepath, 0o600)
    
    def get(self, mcp_name: str) -> Optional[Dict[str, Any]]:
        """
        Get auth entry for an MCP server.
        
        Args:
            mcp_name: Name of the MCP server
            
        Returns:
            Auth entry dict or None if not found
        """
        data = self._read()
        return data.get(mcp_name)
    
    def get_for_url(self, mcp_name: str, server_url: str) -> Optional[Dict[str, Any]]:
        """
        Get auth entry and validate it's for the correct URL.
        
        Returns None if URL has changed (credentials are invalid).
        
        Args:
            mcp_name: Name of the MCP server
            server_url: Expected server URL
            
        Returns:
            Auth entry if URL matches, None otherwise
        """
        entry = self.get(mcp_name)
        if not entry:
            return None
        
        # If no server_url stored, consider it invalid (old version)
        if not entry.get("server_url"):
            return None
        
        # If URL changed, credentials are invalid
        if entry.get("server_url") != server_url:
            return None
        
        return entry
    
    def all(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all stored auth entries.
        
        Returns:
            Dict mapping MCP server names to their auth entries
        """
        return self._read()
    
    def _set(self, mcp_name: str, entry: Dict[str, Any], server_url: Optional[str] = None) -> None:
        """
        Set an auth entry for an MCP server.
        
        Args:
            mcp_name: Name of the MCP server
            entry: Auth entry dict
            server_url: Optional server URL to track
        """
        data = self._read()
        
        # Update server_url if provided
        if server_url:
            entry["server_url"] = server_url
        
        data[mcp_name] = entry
        self._write(data)
    
    def set_tokens(
        self,
        mcp_name: str,
        tokens: Dict[str, Any],
        server_url: Optional[str] = None
    ) -> None:
        """
        Set OAuth tokens for an MCP server.
        
        Args:
            mcp_name: Name of the MCP server
            tokens: Token dict with access_token, refresh_token, expires_at, scope
            server_url: Server URL these tokens are for
        """
        entry = self.get(mcp_name) or {}
        entry["tokens"] = tokens
        self._set(mcp_name, entry, server_url)
    
    def set_client_info(
        self,
        mcp_name: str,
        client_info: Dict[str, Any],
        server_url: Optional[str] = None
    ) -> None:
        """
        Set client info from dynamic registration.
        
        Args:
            mcp_name: Name of the MCP server
            client_info: Client info dict with client_id, client_secret, etc.
            server_url: Server URL this client is registered with
        """
        entry = self.get(mcp_name) or {}
        entry["client_info"] = client_info
        self._set(mcp_name, entry, server_url)
    
    def remove(self, mcp_name: str) -> None:
        """
        Remove auth entry for an MCP server.
        
        Args:
            mcp_name: Name of the MCP server
        """
        data = self._read()
        if mcp_name in data:
            del data[mcp_name]
            self._write(data)
    
    def set_code_verifier(self, mcp_name: str, code_verifier: str) -> None:
        """
        Set PKCE code verifier for OAuth flow.
        
        Args:
            mcp_name: Name of the MCP server
            code_verifier: PKCE code verifier string
        """
        entry = self.get(mcp_name) or {}
        entry["code_verifier"] = code_verifier
        self._set(mcp_name, entry)
    
    def clear_code_verifier(self, mcp_name: str) -> None:
        """
        Clear PKCE code verifier after use.
        
        Args:
            mcp_name: Name of the MCP server
        """
        entry = self.get(mcp_name)
        if entry and "code_verifier" in entry:
            del entry["code_verifier"]
            self._set(mcp_name, entry)
    
    def set_oauth_state(self, mcp_name: str, state: str) -> None:
        """
        Set OAuth state for CSRF protection.
        
        Args:
            mcp_name: Name of the MCP server
            state: Random state string
        """
        entry = self.get(mcp_name) or {}
        entry["oauth_state"] = state
        self._set(mcp_name, entry)
    
    def get_oauth_state(self, mcp_name: str) -> Optional[str]:
        """
        Get OAuth state for an MCP server.
        
        Args:
            mcp_name: Name of the MCP server
            
        Returns:
            OAuth state string or None
        """
        entry = self.get(mcp_name)
        if entry:
            return entry.get("oauth_state")
        return None
    
    def clear_oauth_state(self, mcp_name: str) -> None:
        """
        Clear OAuth state after use.
        
        Args:
            mcp_name: Name of the MCP server
        """
        entry = self.get(mcp_name)
        if entry and "oauth_state" in entry:
            del entry["oauth_state"]
            self._set(mcp_name, entry)
    
    def is_token_expired(self, mcp_name: str) -> Optional[bool]:
        """
        Check if stored tokens are expired.
        
        Args:
            mcp_name: Name of the MCP server
            
        Returns:
            None if no tokens exist
            False if no expiry or not expired
            True if expired
        """
        entry = self.get(mcp_name)
        if not entry or not entry.get("tokens"):
            return None
        
        tokens = entry["tokens"]
        expires_at = tokens.get("expires_at")
        if not expires_at:
            return False
        
        return expires_at < time.time()
