"""
Gateway authentication enforcement for PraisonAI.

This module provides concrete implementations of authentication protocols
for bind-aware authentication posture. Heavy implementations live in the
wrapper package following the protocol-driven design.
"""

import logging
import os
import secrets
from typing import Optional

# Import protocols from core SDK
from praisonaiagents.gateway.protocols import (
    AuthMode,
    GatewayAuthProtocol,
    is_loopback,
    resolve_auth_mode,
)

logger = logging.getLogger(__name__)


class GatewayStartupError(Exception):
    """Raised when gateway startup configuration is unsafe."""
    pass


class GatewayAuthEnforcer:
    """Concrete implementation of GatewayAuthProtocol.
    
    Enforces bind-aware authentication posture:
    - Loopback interfaces: permissive (local mode)
    - External interfaces: strict (token mode required)
    """
    
    def validate_auth_config(
        self,
        auth_mode: AuthMode,
        bind_host: str,
        auth_token: Optional[str] = None,
        **kwargs
    ) -> None:
        """Validate that authentication configuration is safe for the bind host.
        
        Args:
            auth_mode: The authentication mode to validate
            bind_host: The host the server will bind to
            auth_token: The configured auth token (if any)
            **kwargs: Additional auth configuration
            
        Raises:
            GatewayStartupError: If configuration is unsafe for external binding
        """
        # Local mode on loopback is always safe
        if auth_mode == "local" and is_loopback(bind_host):
            logger.info(f"Gateway auth: local mode on loopback interface {bind_host}")
            return
        
        # External binding requires authentication
        if not is_loopback(bind_host):
            if auth_mode == "local":
                raise GatewayStartupError(
                    f"Cannot use local mode on external interface {bind_host}. "
                    f"Set GATEWAY_AUTH_TOKEN or run 'praisonai onboard' for secure auth."
                )
            
            if auth_mode == "token" and not auth_token:
                raise GatewayStartupError(
                    f"Cannot bind to {bind_host} without an auth token.\n"
                    f"  Fix:  praisonai onboard         (30 seconds, 3 prompts)\n"
                    f"  Or:   export GATEWAY_AUTH_TOKEN=$(openssl rand -hex 16)"
                )
        
        logger.info(f"Gateway auth: {auth_mode} mode on {bind_host}")
    
    def check_request_auth(
        self,
        auth_mode: AuthMode,
        request_token: Optional[str] = None,
        expected_token: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Check if a request satisfies authentication requirements.
        
        Args:
            auth_mode: The current authentication mode
            request_token: Token provided in the request
            expected_token: Expected token value
            **kwargs: Additional request context
            
        Returns:
            True if authentication is satisfied, False otherwise
        """
        if auth_mode == "local":
            # Local mode is permissive - no auth required
            return True
        
        if auth_mode == "token":
            if not expected_token:
                # Fail closed: token mode with no expected token is a misconfiguration
                logger.error("Token mode requested but no expected token configured; denying request")
                return False
            
            if not request_token:
                return False
            
            # Use constant-time comparison to prevent timing attacks
            return secrets.compare_digest(request_token, expected_token)
        
        # Other modes not implemented yet
        logger.warning(f"Unknown auth mode: {auth_mode}")
        return False


def assert_external_bind_safe(config) -> None:
    """Assert that a gateway configuration is safe for external binding.
    
    This is the main entry point for gateway startup validation.
    
    Args:
        config: GatewayConfig instance with host, bind_host, auth_token, etc.
        
    Raises:
        GatewayStartupError: If configuration is unsafe
    """
    # Use bind_host if available, otherwise fall back to host
    bind_host = getattr(config, 'bind_host', None) or config.host
    auth_token = getattr(config, 'auth_token', None)
    configured_mode = getattr(config, 'auth_mode', None)
    
    # Resolve authentication mode based on bind interface
    auth_mode = resolve_auth_mode(bind_host, configured=configured_mode)
    
    # Create enforcer and validate
    enforcer = GatewayAuthEnforcer()
    enforcer.validate_auth_config(
        auth_mode=auth_mode,
        bind_host=bind_host,
        auth_token=auth_token,
    )


def log_token_fingerprint(token: str) -> None:
    """Log a token fingerprint instead of the raw token for security.
    
    Logs only the first 4 and last 4 characters with asterisks in between.
    
    Args:
        token: The auth token to fingerprint
    """
    if not token:
        return
    
    if len(token) <= 8:
        # Short token, just mask most of it
        fingerprint = f"gw_{token[:2]}{'*' * (len(token) - 2)}"
    else:
        # Standard fingerprint: gw_<first4>****<last4>
        fingerprint = f"gw_{token[:4]}{'*' * 4}{token[-4:]}"
    
    logger.info(f"Gateway auth token fingerprint: {fingerprint}")


def ensure_token_env_file(token: str, env_file_path: Optional[str] = None) -> None:
    """Ensure the auth token is persisted to environment file.
    
    This allows the dashboard URL to remain stable across restarts.
    
    Args:
        token: The auth token to persist
        env_file_path: Path to .env file (defaults to ~/.praisonai/.env)
    """
    if not token:
        return
    
    if not env_file_path:
        # Default to ~/.praisonai/.env
        home_dir = os.path.expanduser("~")
        praisonai_dir = os.path.join(home_dir, ".praisonai")
        env_file_path = os.path.join(praisonai_dir, ".env")
    
    try:
        # Ensure directory exists (skip when env_file_path has no directory component)
        parent = os.path.dirname(env_file_path)
        if parent:
            os.makedirs(parent, mode=0o700, exist_ok=True)
        
        # Read existing content
        existing_lines = []
        if os.path.exists(env_file_path):
            with open(env_file_path, 'r', encoding='utf-8') as f:
                existing_lines = f.readlines()
        
        # Check if GATEWAY_AUTH_TOKEN already exists
        token_line_found = False
        for i, line in enumerate(existing_lines):
            if line.strip().startswith("GATEWAY_AUTH_TOKEN="):
                existing_lines[i] = f"GATEWAY_AUTH_TOKEN={token}\n"
                token_line_found = True
                break
        
        # Add token if not found
        if not token_line_found:
            existing_lines.append(f"GATEWAY_AUTH_TOKEN={token}\n")
        
        # Write atomically with secure permissions from the start
        fd = os.open(env_file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.writelines(existing_lines)
        # Defensive chmod in case the file pre-existed with looser perms
        os.chmod(env_file_path, 0o600)
        
        logger.debug(f"Gateway auth token persisted to {env_file_path}")
        
    except Exception as e:
        logger.warning(f"Could not persist auth token to {env_file_path}: {e}")