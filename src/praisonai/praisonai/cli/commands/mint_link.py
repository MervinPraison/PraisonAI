"""
CLI command to mint fresh magic links for gateway authentication.

Usage:
    praisonai gateway mint-link
"""

import os
import sys
from pathlib import Path


def get_gateway_base_url() -> str:
    """Get the gateway base URL from environment or default."""
    host = os.environ.get("GATEWAY_HOST", "127.0.0.1")
    port = os.environ.get("GATEWAY_PORT", "8765")
    return f"http://{host}:{port}"


def mint_fresh_link(ttl: int = 600) -> str:
    """Mint a fresh magic link.
    
    Args:
        ttl: Time-to-live in seconds (default 10 minutes)
        
    Returns:
        Complete magic link URL
    """
    try:
        from praisonai.gateway.magic_link import MagicLinkStore
    except ImportError as exc:
        raise RuntimeError("Magic link functionality not available") from exc
    
    store = MagicLinkStore()
    nonce = store.mint(ttl=ttl)
    
    base_url = get_gateway_base_url()
    magic_url = f"{base_url}/?link={nonce}"
    
    # Also save to last-link.txt for convenience
    try:
        praisonai_home = Path(os.environ.get("PRAISONAI_HOME", Path.home() / ".praisonai"))
        praisonai_home.mkdir(parents=True, exist_ok=True)
        
        last_link_file = praisonai_home / "last-link.txt"
        last_link_file.write_text(magic_url)
        os.chmod(last_link_file, 0o600)
    except OSError:
        pass
    
    return magic_url


def run_mint_link(args) -> None:
    """CLI command entry point for minting magic links."""
    ttl = getattr(args, 'ttl', 600)
    
    try:
        magic_url = mint_fresh_link(ttl=ttl)
        print(magic_url)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)