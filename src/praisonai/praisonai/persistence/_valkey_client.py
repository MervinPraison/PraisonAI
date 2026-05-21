"""
Shared Valkey client factory.

Centralises connection-creation logic so that ValkeyStateStore,
ValkeyVectorKnowledgeStore, and ValkeyStorageAdapter all use exactly the
same code path.

Requires: valkey-glide-sync
Install:  pip install 'praisonai[valkey]'
"""

import os
from typing import Any, Optional


def create_valkey_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    password: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """
    Create a synchronous Valkey/Glide client.

    Connection parameters are resolved in priority order:
        explicit argument → environment variable → built-in default.

    Args:
        host:     Valkey host (env ``VALKEY_HOST``, default ``"localhost"``).
        port:     Valkey port (env ``VALKEY_PORT``, default ``6379``).
        password: Valkey password (env ``VALKEY_PASSWORD``, optional).
        **kwargs: Additional keyword arguments forwarded to
                  ``GlideClientConfiguration``.

    Returns:
        A connected ``GlideClient`` instance.

    Raises:
        ImportError: When *valkey-glide-sync* is not installed.
    """
    try:
        from glide_sync import (  # type: ignore[import]
            GlideClient,
            GlideClientConfiguration,
            NodeAddress,
            ServerCredentials,
        )
    except ImportError as exc:
        raise ImportError(
            "valkey-glide-sync is required for Valkey support. "
            "Install with: pip install 'praisonai[valkey]' "
            "or pip install valkey-glide-sync>=2.3.1"
        ) from exc

    # Resolve connection parameters, preferring explicit args over env vars.
    resolved_host: str = host if host is not None else os.getenv("VALKEY_HOST", "localhost")
    resolved_port: int = (
        port if port is not None else int(os.getenv("VALKEY_PORT", "6379"))
    )
    resolved_password: Optional[str] = (
        password if password is not None else os.getenv("VALKEY_PASSWORD")
    )

    addresses = [NodeAddress(resolved_host, resolved_port)]
    credentials = ServerCredentials(password=resolved_password) if resolved_password else None

    config = GlideClientConfiguration(
        addresses=addresses,
        credentials=credentials,
        **kwargs,
    )

    return GlideClient(config)


def scan_keys(client: Any, pattern: str) -> list:
    """
    Safely iterate all keys matching *pattern* using ``SCAN``.

    ``KEYS`` is a blocking O(N) command unsuitable for production.  This
    helper uses the non-blocking ``SCAN`` cursor loop instead.

    Args:
        client:  A ``GlideClient`` instance.
        pattern: Glob-style key pattern (e.g. ``"praison:*"``).

    Returns:
        A list of key strings matching the pattern.
    """
    matched: list = []
    cursor: bytes = b"0"
    while True:
        result = client.scan(cursor, match=pattern, count=100)
        cursor = result[0]  # next cursor (bytes)
        batch = result[1]   # list of matching keys (bytes)
        for k in batch:
            matched.append(k.decode() if isinstance(k, (bytes, bytearray)) else k)
        # SCAN is finished when the returned cursor is "0"
        if cursor in (b"0", "0", 0):
            break
    return matched
