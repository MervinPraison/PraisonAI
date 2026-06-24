"""
Suggestion Engine — proposes automation blueprints as consent-first suggestions.

This module provides the heavy implementation side of the suggestion
system.  It wraps :class:`~praisonaiagents.scheduler.suggestion_store.SuggestionStore`
to provide a higher-level API for proposing, listing, accepting, and
dismissing automation suggestions.

"Nothing is ever auto-created" — the engine only writes to the
SuggestionStore; only explicit user acceptance materializes a job.

Usage::

    from praisonai.scheduler.suggestion_engine import SuggestionEngine

    engine = SuggestionEngine()
    sug_id = engine.propose(
        "morning-brief",
        slots={"hour": 8, "weekdays": "mon-fri"},
        deliver="telegram",
        reason="Detected daily morning request pattern",
    )
    if sug_id:
        print(f"Suggestion created: {sug_id}")
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from praisonaiagents.scheduler.suggestion_store import (
    SuggestionStore,
    Suggestion,
    DEFAULT_TTL_SEC,
)

logger = logging.getLogger(__name__)


class SuggestionEngine:
    """Heuristic engine for proposing blueprint-based automations.

    For v1, suggestions are triggered by direct calls to :meth:`propose`
    (from CLI, dashboard, or programmatic API).  Future versions may
    add pattern-detection heuristics for automatic proposal generation.

    The engine enforces the consent-first rule: nothing is ever
    auto-created.  Every proposal must be explicitly accepted before
    it becomes a real scheduled job.
    """

    def __init__(self, store_path: Optional[str] = None):
        self._store = SuggestionStore(path=store_path)

    # -- public API ------------------------------------------------------------

    def propose(
        self,
        blueprint_name: str,
        slots: Optional[Dict[str, Any]] = None,
        deliver: str = "",
        reason: str = "",
        ttl_seconds: float = DEFAULT_TTL_SEC,
    ) -> Optional[str]:
        """Propose a blueprint-based automation to the user.

        The proposal is added to the suggestion store, where it waits
        for the user to accept or dismiss.  This method does **not**
        create a schedule job — it only writes a suggestion.

        Args:
            blueprint_name: Name of the blueprint to suggest.
            slots: Pre-filled slot values.
            deliver: Suggested delivery target.
            reason: Human-readable explanation of why this is proposed.
            ttl_seconds: How long before the suggestion auto-expires
                (default: 3 days).  Use ``0`` for no expiry.

        Returns:
            The suggestion ID if the proposal was accepted by the store,
            ``None`` if rejected (cap full or duplicate).

        Raises:
            ValueError: If ``ttl_seconds`` is negative (use ``0`` for no
                expiry).
        """
        if ttl_seconds < 0:
            raise ValueError(
                "ttl_seconds must be >= 0; use 0 for no expiry"
            )
        sug = Suggestion(
            id=f"sug_{uuid.uuid4().hex[:12]}",
            blueprint_name=blueprint_name,
            # Copy caller-provided slots to avoid external mutation
            # side effects on the stored suggestion.
            slots=dict(slots) if slots is not None else {},
            deliver=deliver,
            reason=reason,
            created_at=time.time(),
            expires_at=(time.time() + ttl_seconds) if ttl_seconds > 0 else 0.0,
        )
        ok = self._store.add(sug)
        if ok:
            return sug.id
        logger.debug(
            "Suggestion for blueprint '%s' rejected (cap or dup)",
            blueprint_name,
        )
        return None

    def pending(self) -> List[Suggestion]:
        """Return the list of pending (undismissed, unaccepted) suggestions."""
        return self._store.list_pending()

    def accept(self, suggestion_id: str) -> bool:
        """Mark a suggestion as accepted.

        Note:
            This only updates the suggestion's status.  The caller is
            responsible for materializing the corresponding schedule job.
        """
        return self._store.accept(suggestion_id)

    def dismiss(self, suggestion_id: str) -> bool:
        """Mark a suggestion as dismissed (user declined)."""
        return self._store.dismiss(suggestion_id)

    def get_suggestion(self, suggestion_id: str) -> Optional[Suggestion]:
        """Return a single suggestion by ID, or ``None``."""
        return self._store.get(suggestion_id)
