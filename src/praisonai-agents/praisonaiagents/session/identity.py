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

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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


_DEFAULT_IDENTITY_PATH = Path(
    os.environ.get(
        "PRAISONAI_IDENTITY_PATH",
        os.path.expanduser("~/.praisonai/identity.json"),
    )
)


class FileIdentityResolver(InMemoryIdentityResolver):
    """JSON-file-backed ``IdentityResolverProtocol`` implementation.

    Loads links from disk on construction; persists on every mutation
    via atomic temp-file + ``os.replace``. Thread-safe.

    Default path: ``$PRAISONAI_IDENTITY_PATH`` or ``~/.praisonai/identity.json``.

    Storage format::

        {
          "links": {
            "telegram::12345": "alice",
            "discord::snowflake-1": "alice"
          }
        }
    """

    def __init__(self, path: Optional[Path | str] = None) -> None:
        super().__init__()
        self._path: Path = Path(path) if path else _DEFAULT_IDENTITY_PATH
        # Serialises concurrent disk writes so that two simultaneous
        # link()/unlink() calls cannot interleave their os.replace() and
        # lose the second writer's data.
        self._flush_lock = threading.Lock()
        self._load()

    @staticmethod
    def _encode_key(platform: str, platform_user_id: str) -> str:
        return f"{platform}::{platform_user_id}"

    @staticmethod
    def _decode_key(encoded: str) -> tuple[str, str]:
        platform, _, user = encoded.partition("::")
        return platform, user

    def _load(self) -> None:
        try:
            if not self._path.exists():
                return
            data = json.loads(self._path.read_text(encoding="utf-8"))
            links = data.get("links", {}) if isinstance(data, dict) else {}
            with self._lock:
                self._links = {
                    self._decode_key(k): v
                    for k, v in links.items()
                    if isinstance(v, str)
                }
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("FileIdentityResolver: failed to load %s: %s", self._path, e)

    def _flush(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Hold _flush_lock for the entire write (snapshot + disk I/O) so
            # that concurrent calls always write the latest in-memory state and
            # the last os.replace() wins rather than an older snapshot.
            with self._flush_lock:
                with self._lock:
                    payload = {
                        "links": {
                            self._encode_key(p, u): uid
                            for (p, u), uid in self._links.items()
                        }
                    }
                fd, tmp = tempfile.mkstemp(
                    dir=str(self._path.parent), prefix=".identity-", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, self._path)
                    try:
                        os.chmod(self._path, 0o600)
                    except OSError:
                        pass
                except BaseException:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
        except OSError as e:
            logger.warning("FileIdentityResolver: failed to flush %s: %s", self._path, e)

    def link(
        self, platform: str, platform_user_id: str, unified_user_id: str
    ) -> None:
        super().link(platform, platform_user_id, unified_user_id)
        self._flush()

    def unlink(self, platform: str, platform_user_id: str) -> None:
        super().unlink(platform, platform_user_id)
        self._flush()


__all__ = [
    "IdentityLink",
    "IdentityResolverProtocol",
    "InMemoryIdentityResolver",
    "FileIdentityResolver",
]
