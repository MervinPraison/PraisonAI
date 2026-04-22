"""
UI authentication helper for PraisonAI.

This module provides a shared authentication helper that consolidates
the duplicated password auth callbacks across all UI files and enforces
bind-aware authentication posture.
"""

import logging
import os
from typing import Optional

# Import protocols from core SDK
from praisonaiagents.gateway.protocols import (
    UIAuthProtocol,
    is_loopback,
)

logger = logging.getLogger(__name__)


class UIStartupError(Exception):
    """Raised when UI startup configuration is unsafe."""
    pass


class UIAuthEnforcer:
    """Concrete implementation of UIAuthProtocol.
    
    Enforces bind-aware authentication for UI components:
    - Loopback interfaces: allow default admin/admin credentials with warning
    - External interfaces: refuse default credentials unless escape hatch is set
    """
    
    def validate_credentials_config(
        self,
        bind_host: str,
        username: str,
        password: str,
        allow_defaults: bool = False
    ) -> None:
        """Validate that UI credentials are safe for the bind host.
        
        Args:
            bind_host: The host the UI server will bind to
            username: Configured username
            password: Configured password
            allow_defaults: Whether to allow default credentials (escape hatch)
            
        Raises:
            UIStartupError: If credentials are unsafe for external binding
        """
        is_default_creds = (username == "admin" and password == "admin")
        is_external = not is_loopback(bind_host)
        
        if is_default_creds and is_external and not allow_defaults:
            raise UIStartupError(
                f"Cannot use default admin/admin credentials on external interface {bind_host}.\n"
                f"  Fix: Set CHAINLIT_USERNAME and CHAINLIT_PASSWORD environment variables\n"
                f"  Or:  Set PRAISONAI_ALLOW_DEFAULT_CREDS=1 (unsafe, for demo only)"
            )
        
        if is_default_creds:
            if is_external:
                logger.warning(
                    f"⚠️  Using default admin/admin credentials on external interface {bind_host}. "
                    f"This is unsafe for production."
                )
            else:
                logger.warning(
                    f"⚠️  Using default admin/admin credentials on localhost. "
                    f"Set CHAINLIT_USERNAME and CHAINLIT_PASSWORD for production."
                )
    
    def check_auth_callback(
        self,
        bind_host: str,
        provided_username: str,
        provided_password: str,
        expected_username: str,
        expected_password: str
    ) -> bool:
        """Check if provided credentials are valid for the bind host.
        
        Args:
            bind_host: The host the UI server is bound to
            provided_username: Username from login attempt
            provided_password: Password from login attempt
            expected_username: Expected username
            expected_password: Expected password
            
        Returns:
            True if credentials are valid, False otherwise
        """
        return (provided_username, provided_password) == (expected_username, expected_password)


def register_password_auth(app, *, bind_host: str) -> None:
    """Register password authentication for a Chainlit app with bind-aware validation.
    
    This replaces the duplicated @cl.password_auth_callback decorators across
    all UI files with a single shared implementation that enforces secure
    authentication posture.
    
    Args:
        app: The Chainlit app instance (unused, for signature compatibility)
        bind_host: The host the UI server is bound to
    """
    import chainlit as cl
    
    # Get credentials from environment
    expected_username = os.getenv("CHAINLIT_USERNAME", "admin")
    expected_password = os.getenv("CHAINLIT_PASSWORD", "admin")
    
    # Check for escape hatch
    allow_defaults = os.getenv("PRAISONAI_ALLOW_DEFAULT_CREDS", "").lower() in ("1", "true", "yes")
    
    # Validate configuration at startup
    enforcer = UIAuthEnforcer()
    try:
        enforcer.validate_credentials_config(
            bind_host=bind_host,
            username=expected_username,
            password=expected_password,
            allow_defaults=allow_defaults
        )
    except UIStartupError as e:
        # Convert to runtime error to prevent startup
        raise RuntimeError(str(e))
    
    @cl.password_auth_callback
    def auth_callback(username: str, password: str):
        """Shared password authentication callback."""
        logger.debug(f"Auth attempt: username='{username}', expected='{expected_username}'")
        
        # Use enforcer to check credentials
        is_valid = enforcer.check_auth_callback(
            bind_host=bind_host,
            provided_username=username,
            provided_password=password,
            expected_username=expected_username,
            expected_password=expected_password
        )
        
        if is_valid:
            logger.info(f"Login successful for user: {username}")
            return cl.User(identifier=username, metadata={"role": "admin", "provider": "credentials"})
        else:
            logger.warning(f"Login failed for user: {username}")
            return None
    
    return auth_callback


# Backward compatibility: export the old pattern for existing code
def create_auth_callback(bind_host: str):
    """Create an auth callback for the given bind host.
    
    This provides backward compatibility for existing code that creates
    auth callbacks manually.
    
    Args:
        bind_host: The host the UI server is bound to
        
    Returns:
        A configured auth callback function
    """
    # This will register the callback globally, but also return it
    return register_password_auth(None, bind_host=bind_host)