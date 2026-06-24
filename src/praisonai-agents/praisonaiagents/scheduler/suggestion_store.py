"""
Suggestion store — consent-first proposals for proactive automations.

This module provides a thread-safe, atomic JSON-backed store for
pending automation suggestions.  The framework may *propose* an
automation (e.g., after detecting a recurring manual ask), but it
only becomes a real scheduled job when the user explicitly accepts it.

**"Nothing is ever auto-created."**

The store enforces:

* **Max-pending cap** (default 20) — prevents flooding.
* **Dedup window** (24 h) — the same blueprint+slots won't be
  suggested twice within the window.
* **Atomic writes** — write to temp file, then replace.

Storage location: ``~/.praisonai/suggestions.json``

Usage::

    from praisonaiagents.scheduler.suggestion_store import SuggestionStore, Suggestion

    store = SuggestionStore()
    store.add(Suggestion(
        id="sug_abc123",
        blueprint_name="morning-brief",
        slots={"hour": 8, "weekdays": "mon-fri"},
        reason="Daily request pattern detected",
    ))
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

# ── Constants ────────────────────────────────────────────────────────────────

MAX_PENDING_CAP: int = 20
"""Maximum number of pending (undismissed, unaccepted) suggestions."""

DEDUP_WINDOW_SEC: float = 3600 * 24
"""Dedup window: don't suggest the same thing twice within 24 hours."""

DEFAULT_TTL_SEC: float = 3600 * 24 * 3
"""Default TTL for a suggestion (3 days).  Expired suggestions are
pruned from the pending list."""


# ── Suggestion dataclass ─────────────────────────────────────────────────────


@dataclass
class Suggestion:
    """A proposed automation that the user has not yet acted on.

    Only becomes a real schedule job when the user accepts it via
    :meth:`SuggestionStore.accept`.
    """

    id: str
    """Unique suggestion identifier (e.g. ``"sug_<random>"``)."""

    blueprint_name: str
    """Which blueprint triggered this suggestion."""

    slots: Dict[str, Any] = field(default_factory=dict)
    """Filled-in slot values for the blueprint."""

    deliver: str = ""
    """Suggested delivery target."""

    reason: str = ""
    """Human-readable explanation of why this was suggested."""

    created_at: float = field(default_factory=time.time)
    """Unix timestamp when the suggestion was created."""

    expires_at: float = 0.0
    """Unix timestamp after which the suggestion auto-expires.
    ``0`` means no expiry."""

    dismissed: bool = False
    """True if the user explicitly dismissed this suggestion."""

    accepted: bool = False
    """True if the user accepted this suggestion (job has been created)."""


# ── Suggestion store ─────────────────────────────────────────────────────────


class SuggestionStore:
    """Atomic JSON-backed store for pending automation suggestions.

    Thread-safe via :class:`threading.RLock`.  Suggestions are persisted
    to ``~/.praisonai/suggestions.json`` with atomic writes (write to
    ``.tmp``, then ``os.replace``).
    """

    def __init__(self, path: Optional[str] = None):
        if path is None:
            from praisonaiagents.paths import get_data_dir
            path = str(get_data_dir() / "suggestions.json")
        self._path = path
        self._lock = threading.RLock()
        self._suggestions: Dict[str, Suggestion] = {}
        self._load()

    # -- persistence -----------------------------------------------------------

    def _load(self) -> None:
        """Load existing suggestions from disk (best-effort)."""
        if not os.path.exists(self._path):
            self._suggestions = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                new_suggestions = {}
                for sid, d in data.items():
                    if isinstance(d, dict):
                        try:
                            new_suggestions[sid] = Suggestion(**d)
                        except TypeError:
                            pass  # skip malformed entries
                self._suggestions = new_suggestions
        except (json.JSONDecodeError, OSError):
            self._suggestions = {}  # corrupt file → start fresh

    def _save(self) -> None:
        """Atomically persist the current state to disk."""
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        data = {sid: asdict(s) for sid, s in self._suggestions.items()}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    # -- public API ------------------------------------------------------------

    def add(self, suggestion: Suggestion) -> bool:
        """Add a suggestion to the store.

        Returns:
            ``True`` if the suggestion was added, ``False`` if it was
            rejected due to a duplicate ID, the pending cap, or the
            dedup window.
        """
        with self._lock:
            now = time.time()

            # Reject duplicate IDs — overwriting would clobber the
            # existing suggestion's lifecycle state (accepted/dismissed).
            if suggestion.id in self._suggestions:
                return False

            # Only count active (non-dismissed, non-accepted, non-expired)
            # suggestions toward the cap and dedup window.
            active = [
                s for s in self._suggestions.values()
                if not s.dismissed and not s.accepted
                and (s.expires_at == 0 or s.expires_at > now)
            ]
            if len(active) >= MAX_PENDING_CAP:
                return False

            # Dedup check: same blueprint + same slots within the window
            for existing in active:
                if (
                    existing.blueprint_name == suggestion.blueprint_name
                    and existing.slots == suggestion.slots
                    and (now - existing.created_at) < DEDUP_WINDOW_SEC
                ):
                    return False

            self._suggestions[suggestion.id] = suggestion
            self._save()
            return True

    def get(self, suggestion_id: str) -> Optional[Suggestion]:
        """Return a suggestion by ID, or ``None``."""
        with self._lock:
            return self._suggestions.get(suggestion_id)

    def list_pending(self) -> List[Suggestion]:
        """Return all undismissed, unaccepted, non-expired suggestions."""
        now = time.time()
        with self._lock:
            return [
                s for s in self._suggestions.values()
                if not s.dismissed and not s.accepted
                and (s.expires_at == 0 or s.expires_at > now)
            ]

    def accept(self, suggestion_id: str) -> bool:
        """Mark a suggestion as accepted.

        Returns:
            ``False`` if the suggestion was not found or was already
            dismissed (terminal states are mutually exclusive).
        """
        with self._lock:
            s = self._suggestions.get(suggestion_id)
            if s is None or s.dismissed:
                return False
            s.accepted = True
            self._save()
            return True

    def dismiss(self, suggestion_id: str) -> bool:
        """Mark a suggestion as dismissed (user declined).

        Returns:
            ``False`` if the suggestion was not found or was already
            accepted (terminal states are mutually exclusive).
        """
        with self._lock:
            s = self._suggestions.get(suggestion_id)
            if s is None or s.accepted:
                return False
            s.dismissed = True
            self._save()
            return True

    def prune_expired(self) -> int:
        """Remove expired suggestions.  Returns count of pruned entries."""
        now = time.time()
        with self._lock:
            before = len(self._suggestions)
            self._suggestions = {
                sid: s for sid, s in self._suggestions.items()
                if s.expires_at == 0 or s.expires_at > now
            }
            pruned = before - len(self._suggestions)
            if pruned:
                self._save()
            return pruned
