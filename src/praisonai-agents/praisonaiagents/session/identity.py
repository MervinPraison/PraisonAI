"""Cross-platform identity resolution for agents.

W1 — Optional, opt-in mapping from ``(platform, platform_user_id)``
to a single ``unified_user_id`` so the same human is recognised across
Telegram, Discord, Slack, etc.

By default (no links registered) ``resolve()`` returns the
platform-prefixed string unchanged — no surprises, no privacy leak.

Linking is performed explicitly, typically after a DM-based pairing
flow has cryptographically verified ownership of both accounts.

Usage::

    from praisonaiagents.session.identity import InMemoryIdentityResolver

    resolver = InMemoryIdentityResolver()
    resolver.link("telegram", "12345", "alice")
    resolver.link("discord", "snowflake-1", "alice")
    assert resolver.resolve("telegram", "12345") == "alice"
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import List, Protocol, runtime_checkable


@dataclass(frozen=True)
class IdentityLink:
    """Immutable mapping from a platform-scoped user ID to a unified ID."""

    platform: str
    platform_user_id: str
    unified_user_id: str


@runtime_checkable
class IdentityResolverProtocol(Protocol):
    """Maps platform-scoped user IDs to a unified identity.

    Implementations MUST be thread-safe. Implementations SHOULD return
    ``f"{platform}:{platform_user_id}"`` for unlinked users so callers
    never need to special-case the unlinked path.
    """

    def resolve(self, platform: str, platform_user_id: str) -> str:
        """Return ``unified_user_id`` for the given platform user.

        If no link is registered, return ``f"{platform}:{platform_user_id}"``.
        """
        ...

    def link(
        self, platform: str, platform_user_id: str, unified_user_id: str
    ) -> None:
        """Register a mapping. Overwrites any existing mapping for the same
        ``(platform, platform_user_id)`` pair.
        """
        ...

    def unlink(self, platform: str, platform_user_id: str) -> None:
        """Remove a mapping. No-op when no link exists."""
        ...

    def links_for(self, unified_user_id: str) -> List[IdentityLink]:
        """Return all links pointing to the given unified ID."""
        ...


class InMemoryIdentityResolver:
    """Thread-safe in-memory ``IdentityResolverProtocol`` implementation.

    Suitable for tests and single-process deployments. Production
    deployments with multiple processes should use a persistent
    implementation backed by SQLite, Redis, or a database.
    """

    def __init__(self) -> None:
        self._links: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    def resolve(self, platform: str, platform_user_id: str) -> str:
        with self._lock:
            return self._links.get(
                (platform, platform_user_id),
                f"{platform}:{platform_user_id}",
            )

    def link(
        self, platform: str, platform_user_id: str, unified_user_id: str
    ) -> None:
        with self._lock:
            self._links[(platform, platform_user_id)] = unified_user_id

    def unlink(self, platform: str, platform_user_id: str) -> None:
        with self._lock:
            self._links.pop((platform, platform_user_id), None)

    def links_for(self, unified_user_id: str) -> List[IdentityLink]:
        with self._lock:
            return [
                IdentityLink(p, u, unified_user_id)
                for (p, u), uid in self._links.items()
                if uid == unified_user_id
            ]


__all__ = [
    "IdentityLink",
    "IdentityResolverProtocol",
    "InMemoryIdentityResolver",
]
