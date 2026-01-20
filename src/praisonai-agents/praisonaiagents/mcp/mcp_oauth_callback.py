"""
MCP OAuth Callback Handler.

This module provides utilities for handling OAuth 2.1 callback flow for MCP servers.
It includes:
- Local callback server for receiving authorization codes
- PKCE code verifier/challenge generation
- OAuth state generation for CSRF protection

The callback server listens on localhost for the OAuth redirect after
browser-based authorization.
"""

import asyncio
import base64
import hashlib
import secrets
import threading
from typing import Dict, Optional


# Default callback configuration (same as OpenCode for consistency)
OAUTH_CALLBACK_PORT = 19876
OAUTH_CALLBACK_PATH = "/mcp/oauth/callback"


def get_redirect_url(port: int = OAUTH_CALLBACK_PORT) -> str:
    """
    Get the OAuth redirect URL.
    
    Args:
        port: Port for the callback server (default: 19876)
        
    Returns:
        Full redirect URL for OAuth providers to whitelist
    """
    return f"http://127.0.0.1:{port}{OAUTH_CALLBACK_PATH}"


def generate_state() -> str:
    """
    Generate a random OAuth state parameter for CSRF protection.
    
    Returns:
        URL-safe random string
    """
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    """
    Generate a PKCE code verifier.
    
    Per RFC 7636, the code verifier is a high-entropy cryptographic
    random string between 43 and 128 characters.
    
    Returns:
        URL-safe random string (43-128 chars)
    """
    # Generate 32 bytes = 43 base64url characters (without padding)
    return secrets.token_urlsafe(32)


def generate_code_challenge(code_verifier: str) -> str:
    """
    Generate a PKCE code challenge from a code verifier.
    
    Uses S256 method: BASE64URL(SHA256(code_verifier))
    
    Args:
        code_verifier: The code verifier string
        
    Returns:
        Base64url-encoded SHA256 hash (no padding)
    """
    # SHA256 hash of the verifier
    digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
    
    # Base64url encode without padding
    challenge = base64.urlsafe_b64encode(digest).decode('ascii')
    
    # Remove padding (= characters)
    return challenge.rstrip('=')


class OAuthCallbackHandler:
    """
    Handler for OAuth callback flow.
    
    This class manages the state of OAuth callbacks, allowing
    the application to wait for authorization codes after
    redirecting the user to the authorization URL.
    
    Example:
        ```python
        from praisonaiagents.mcp.mcp_oauth_callback import (
            OAuthCallbackHandler, generate_state, get_redirect_url
        )
        
        handler = OAuthCallbackHandler()
        state = generate_state()
        
        # Build authorization URL with state and redirect_uri
        auth_url = f"{auth_endpoint}?state={state}&redirect_uri={get_redirect_url()}"
        
        # Open browser for user authorization
        webbrowser.open(auth_url)
        
        # Wait for callback (blocks until callback received or timeout)
        code = handler.wait_for_callback(state, timeout=300)
        
        # Exchange code for tokens
        tokens = exchange_code_for_tokens(code)
        ```
    """
    
    def __init__(self):
        """Initialize the callback handler."""
        self._callbacks: Dict[str, str] = {}  # state -> code
        self._events: Dict[str, threading.Event] = {}  # state -> event
        self._lock = threading.Lock()
    
    def receive_callback(self, state: str, code: str) -> None:
        """
        Receive an OAuth callback with authorization code.
        
        Called by the callback server when it receives a redirect.
        
        Args:
            state: OAuth state parameter
            code: Authorization code from the OAuth provider
        """
        with self._lock:
            self._callbacks[state] = code
            if state in self._events:
                self._events[state].set()
    
    def get_code(self, state: str) -> Optional[str]:
        """
        Get the authorization code for a state.
        
        Args:
            state: OAuth state parameter
            
        Returns:
            Authorization code or None if not received
        """
        with self._lock:
            return self._callbacks.get(state)
    
    def wait_for_callback(self, state: str, timeout: float = 300.0) -> str:
        """
        Wait for an OAuth callback with the given state.
        
        Blocks until the callback is received or timeout.
        
        Args:
            state: OAuth state parameter to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            Authorization code
            
        Raises:
            TimeoutError: If callback not received within timeout
            ValueError: If state doesn't match
        """
        # Check if already received
        code = self.get_code(state)
        if code:
            return code
        
        # Create event for this state
        with self._lock:
            if state not in self._events:
                self._events[state] = threading.Event()
            event = self._events[state]
        
        # Wait for callback
        if not event.wait(timeout=timeout):
            raise TimeoutError(f"OAuth callback not received within {timeout} seconds")
        
        # Get the code
        code = self.get_code(state)
        if not code:
            # Check if a different state was received
            with self._lock:
                if self._callbacks:
                    received_states = list(self._callbacks.keys())
                    raise ValueError(
                        f"OAuth state mismatch. Expected '{state}', "
                        f"received: {received_states}"
                    )
            raise ValueError(f"OAuth callback received but no code for state '{state}'")
        
        return code
    
    async def async_wait_for_callback(self, state: str, timeout: float = 300.0) -> str:
        """
        Async version of wait_for_callback.
        
        Args:
            state: OAuth state parameter to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            Authorization code
            
        Raises:
            asyncio.TimeoutError: If callback not received within timeout
            ValueError: If state doesn't match
        """
        # Check if already received
        code = self.get_code(state)
        if code:
            return code
        
        # Create event for this state
        with self._lock:
            if state not in self._events:
                self._events[state] = threading.Event()
            event = self._events[state]
        
        # Poll for callback with async sleep
        start_time = asyncio.get_event_loop().time()
        while True:
            if event.is_set():
                break
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise asyncio.TimeoutError(
                    f"OAuth callback not received within {timeout} seconds"
                )
            
            await asyncio.sleep(0.05)  # 50ms poll interval
        
        # Get the code
        code = self.get_code(state)
        if not code:
            raise ValueError(f"OAuth callback received but no code for state '{state}'")
        
        return code
    
    def clear_state(self, state: str) -> None:
        """
        Clear callback data for a state.
        
        Should be called after successfully processing a callback.
        
        Args:
            state: OAuth state parameter to clear
        """
        with self._lock:
            self._callbacks.pop(state, None)
            self._events.pop(state, None)
