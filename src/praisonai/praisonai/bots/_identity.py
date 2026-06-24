"""
Store-backed cross-platform identity resolver (wrapper implementation).

The core SDK ships the ``IdentityResolverProtocol`` and lightweight
in-memory / file-backed resolvers (``praisonaiagents.session.identity``).
This module provides a *heavy* implementation that reuses the wrapper's
persistence and **pairing** data so a linked/paired user shares one
session, history and memory across channels **by default**.

``StoreBackedIdentityResolver``:

1. Keeps an explicit, persisted ``(platform, user_id) -> canonical_id``
   link map (inherited from the core ``FileIdentityResolver``).
2. Falls back to the gateway pairing store: when two channels were paired
   under the same label/canonical id, they resolve to that id.
3. Otherwise returns the per-platform id ``f"{platform}:{user_id}"`` — a
   safe, non-merging default identical to the core resolver.

Construction::

    from praisonai.bots import StoreBackedIdentityResolver

    resolver = StoreBackedIdentityResolver.from_env()
    botos = BotOS(agent=agent, platforms=[...], identity_resolver=resolver)

    # Link two channels to one canonical id
    resolver.link("telegram", "12345", "alice")
    resolver.link("whatsapp", "+44...", "alice")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from praisonaiagents.session.identity import FileIdentityResolver

logger = logging.getLogger(__name__)


class StoreBackedIdentityResolver(FileIdentityResolver):
    """File-backed identity resolver augmented with pairing data.

    Inherits the thread-safe, atomically-persisted link map from
    :class:`praisonaiagents.session.identity.FileIdentityResolver` and adds
    an optional read-through to a gateway :class:`PairingStore` so that
    already-paired channels are recognised without an explicit ``link()``.

    Resolution order for ``resolve(platform, user_id)``:

    1. An explicit link registered via :meth:`link` (highest priority).
    2. The pairing store's label for ``(user_id, platform)`` when that
       channel is paired and carries a non-empty label (treated as the
       canonical id) — lets paired users share a session out of the box.
    3. ``f"{platform}:{user_id}"`` — the safe per-platform fallback.

    Args:
        path: JSON file for the explicit link map. Defaults to the core
            resolver default (``$PRAISONAI_IDENTITY_PATH`` or
            ``~/.praisonai/identity.json``).
        pairing_store: Optional object exposing ``is_paired`` /
            ``list_paired`` (e.g. ``praisonai.gateway.pairing.PairingStore``).
            When ``None``, behaviour matches the plain file resolver.
        use_pairing_label: When ``True`` (default) a paired channel's
            ``label`` is used as its canonical id. Set ``False`` to ignore
            labels and rely solely on explicit links.
    """

    def __init__(
        self,
        path: Optional[Path | str] = None,
        pairing_store: Optional[Any] = None,
        use_pairing_label: bool = True,
    ) -> None:
        super().__init__(path=path)
        self._pairing_store = pairing_store
        self._use_pairing_label = use_pairing_label

    @classmethod
    def from_env(
        cls,
        path: Optional[Path | str] = None,
        store_dir: Optional[str] = None,
        use_pairing_label: bool = True,
    ) -> "StoreBackedIdentityResolver":
        """Build a resolver wired to the default gateway pairing store.

        The pairing store is loaded lazily and any failure (e.g. optional
        deps unavailable) degrades gracefully to a plain file resolver.

        Args:
            path: Override for the explicit link-map JSON path.
            store_dir: Override for the pairing store directory.
            use_pairing_label: Forwarded to ``__init__``.
        """
        pairing_store = None
        try:
            from praisonai.gateway.pairing import PairingStore

            pairing_store = PairingStore(store_dir=store_dir)
        except Exception as e:  # pragma: no cover — optional/degraded path
            logger.warning(
                "StoreBackedIdentityResolver: pairing store unavailable, "
                "falling back to link-map only: %s",
                e,
            )
        return cls(
            path=path,
            pairing_store=pairing_store,
            use_pairing_label=use_pairing_label,
        )

    def resolve(self, platform: str, platform_user_id: str) -> str:
        # 1. Explicit links take precedence. The parent returns the
        #    per-platform fallback when no explicit link exists; detect
        #    that so we can consult the pairing store before giving up.
        fallback = f"{platform}:{platform_user_id}"
        with self._lock:
            explicit = self._links.get((platform, platform_user_id))
        if explicit is not None:
            return explicit

        # 2. Pairing-store read-through: a paired channel's label is the
        #    canonical id shared across channels paired under it.
        if self._pairing_store is not None and self._use_pairing_label:
            try:
                canonical = self._canonical_from_pairing(platform, platform_user_id)
                if canonical:
                    return canonical
            except Exception as e:  # pragma: no cover — defensive
                logger.warning("identity pairing lookup failed: %s", e)

        # 3. Safe per-platform fallback.
        return fallback

    def link_paired(self) -> int:
        """Materialise pairing-store labels as explicit links.

        Scans the pairing store and registers an explicit link for every
        paired channel whose label is non-empty, so paired users keep a
        stable canonical id even if the pairing store later changes.

        Returns the number of links created/updated.
        """
        if self._pairing_store is None:
            return 0
        count = 0
        try:
            paired = self._pairing_store.list_paired()
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("identity link_paired failed to list pairings: %s", e)
            return 0
        for ch in paired:
            label = getattr(ch, "label", "") or ""
            channel_type = getattr(ch, "channel_type", "")
            channel_id = getattr(ch, "channel_id", "")
            if label and channel_type and channel_id:
                # Write in-memory only; flush once after the loop to avoid
                # N atomic disk writes when materialising many pairings.
                with self._lock:
                    self._links[(channel_type, channel_id)] = label
                count += 1
        if count:
            self._flush()
        return count

    def all_links(self) -> list[tuple[str, str, str]]:
        """Return every explicit link as ``(platform, user_id, canonical)``."""
        with self._lock:
            return [
                (platform, user_id, canonical)
                for (platform, user_id), canonical in self._links.items()
            ]

    def _canonical_from_pairing(
        self, platform: str, platform_user_id: str
    ) -> Optional[str]:
        """Return the pairing label (canonical id) for a paired channel."""
        store = self._pairing_store
        # Fast path: most messages come from unpaired users. ``is_paired`` is
        # an O(1) dict lookup, so short-circuit before the O(n) scan below.
        is_paired = getattr(store, "is_paired", None)
        if callable(is_paired) and not is_paired(platform_user_id, platform):
            return None
        list_paired = getattr(store, "list_paired", None)
        if not callable(list_paired):
            return None
        for ch in list_paired():
            if (
                getattr(ch, "channel_id", None) == platform_user_id
                and getattr(ch, "channel_type", None) == platform
            ):
                label = getattr(ch, "label", "") or ""
                return label or None
        return None


__all__ = ["StoreBackedIdentityResolver"]
