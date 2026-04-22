"""
Chainlit UI authentication helper.

Provides bind-aware auth for Chainlit apps - consolidates duplicated
password auth callbacks across UI modules.
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from praisonaiagents.gateway.protocols import AuthMode, is_loopback, resolve_auth_mode

logger = logging.getLogger(__name__)


class UIStartupError(Exception):
    """Raised when UI cannot start due to security configuration."""
    pass


def register_password_auth(app, *, bind_host: str) -> None:
    """Register password authentication for Chainlit app with bind-aware security.
    
    Args:
        app: Chainlit app instance (unused but kept for consistency)
        bind_host: Host/IP that the UI server is bound to
        
    Raises:
        UIStartupError: If using default credentials on external interface
    """
    import chainlit as cl  # lazy — chainlit is in [ui] extra only
    # Get credentials from environment
    expected_username = os.getenv("CHAINLIT_USERNAME", "admin")
    expected_password = os.getenv("CHAINLIT_PASSWORD", "admin")
    
    # Check if using default credentials
    using_defaults = (expected_username == "admin" and expected_password == "admin")
    
    # Resolve auth mode based on bind interface
    auth_mode = resolve_auth_mode(bind_host)
    
    # Allow default credentials only on loopback
    if using_defaults and auth_mode != "local":
        # Check for escape hatch
        allow_defaults = os.getenv("PRAISONAI_ALLOW_DEFAULT_CREDS", "").lower() in ("1", "true", "yes")
        if not allow_defaults:
            raise UIStartupError(
                f"Cannot bind to {bind_host} with default admin/admin credentials.\n"
                f"Fix:  export CHAINLIT_USERNAME=myuser CHAINLIT_PASSWORD=mypass\n"
                f"Lab:  export PRAISONAI_ALLOW_DEFAULT_CREDS=1  (demo only)"
            )
        else:
            logger.warning(
                f"⚠️  Using default admin/admin credentials on external interface {bind_host}. "
                f"This is UNSAFE for production. Set CHAINLIT_USERNAME and CHAINLIT_PASSWORD."
            )
    elif using_defaults and auth_mode == "local":
        logger.warning(
            f"⚠️  Using default admin/admin credentials on loopback {bind_host}. "
            f"Set CHAINLIT_USERNAME and CHAINLIT_PASSWORD environment variables for production."
        )
    
    # Register the password auth callback
    @cl.password_auth_callback
    def auth_callback(username: str, password: str) -> Optional["cl.User"]:
        """Password authentication callback."""
        logger.debug("Auth attempt received")
        
        if (username, password) == (expected_username, expected_password):
            logger.info("Login successful")
            return cl.User(identifier=username, metadata={"role": "admin", "provider": "credentials"})
        else:
            logger.warning("Login failed")
            return None
    
    # Log the registration
    auth_status = "permissive" if auth_mode == "local" else "strict"
    logger.info(f"Registered password auth for {bind_host} (mode: {auth_status})")