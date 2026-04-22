"""
Auth enforcement for PraisonAI Gateway.

Implements bind-aware authentication posture - permissive on loopback,
strict on external interfaces.
"""

import os
import logging
from typing import Optional

from praisonaiagents.gateway.protocols import AuthMode, is_loopback, resolve_auth_mode
from praisonaiagents.gateway.config import GatewayConfig

logger = logging.getLogger(__name__)


class GatewayStartupError(Exception):
    """Raised when gateway cannot start due to security configuration."""
    pass


def assert_external_bind_safe(config: GatewayConfig) -> None:
    """Assert that external bind configuration is secure.
    
    Raises GatewayStartupError with fix instructions if unsafe.
    
    Args:
        config: Gateway configuration to validate
        
    Raises:
        GatewayStartupError: If binding to external interface without auth token
    """
    auth_mode = resolve_auth_mode(config.bind_host)
    
    if auth_mode == "local":
        # Loopback bind is always safe
        if not config.auth_token:
            logger.warning(
                f"Gateway binding to loopback interface {config.bind_host} without auth token. "
                f"This is permissive mode - only safe for local development."
            )
        return
    
    # External bind - require auth token
    if not config.auth_token:
        raise GatewayStartupError(
            f"Cannot bind to {config.bind_host} without an auth token.\n"
            f"Fix:  praisonai onboard         (30 seconds, 3 prompts)\n"
            f"Or:   export GATEWAY_AUTH_TOKEN=$(openssl rand -hex 16)"
        )
    
    logger.info(f"Gateway binding to external interface {config.bind_host} with authentication")


def get_auth_token_fingerprint(token: str) -> str:
    """Get a safe fingerprint of the auth token for logging.
    
    Args:
        token: The full auth token
        
    Returns:
        Fingerprint in format "gw_****XXXX" (last 4 chars only)
    """
    if not token:
        return "gw_****<none>"
    
    if len(token) < 4:
        return "gw_****<short>"
    
    return f"gw_****{token[-4:]}"


def save_auth_token_to_env(token: str, env_file: Optional[str] = None) -> None:
    """Save auth token to .env file with secure permissions.
    
    Args:
        token: Auth token to save
        env_file: Path to .env file (defaults to ~/.praisonai/.env)
    """
    import stat
    from pathlib import Path
    
    if env_file is None:
        # Default to ~/.praisonai/.env
        home = Path.home()
        praisonai_dir = home / ".praisonai"
        praisonai_dir.mkdir(exist_ok=True)
        env_file = praisonai_dir / ".env"
    
    env_path = Path(env_file)
    
    # Read existing content
    existing_content = ""
    if env_path.exists():
        existing_content = env_path.read_text()
    
    # Add or update GATEWAY_AUTH_TOKEN
    lines = existing_content.split('\n')
    updated = False
    for i, line in enumerate(lines):
        if line.startswith('GATEWAY_AUTH_TOKEN='):
            lines[i] = f'GATEWAY_AUTH_TOKEN={token}'
            updated = True
            break
    
    if not updated:
        if existing_content and not existing_content.endswith('\n'):
            lines.append('')
        lines.append(f'GATEWAY_AUTH_TOKEN={token}')
    
    # Write with secure permissions
    env_path.write_text('\n'.join(lines))
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    
    logger.info(f"Auth token saved to {env_path} with secure permissions (mode 0600)")