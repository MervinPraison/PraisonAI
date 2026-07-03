"""
Self-healing dead-target registry for outbound delivery (issue #2486).

When a gateway delivers to a channel that has become *permanently* unreachable
— the bot was kicked/blocked, the group was deleted, the chat no longer exists
— there is otherwise no memory of that. Every subsequent proactive, scheduled
or broadcast send re-attempts the dead target from scratch: a fresh API call, a
fresh failure, and a fresh stack of log lines. For a long-lived gateway pushing
periodic updates to many channels this quietly burns rate-limit budget, slows
fan-out (every cycle waits on doomed calls), and floods logs with noise.

This module provides a small, bounded, **self-healing** registry:
  - record a ``(platform, channel_id)`` as dead only on a *confirmed permanent*
    failure (e.g. ``403 Forbidden``, ``404``/"chat not found"),
  - short-circuit future sends to it (consulted by ``DeliveryRouter.deliver``),
  - **automatically clear** the flag the moment any send to that target
    succeeds again (user re-adds the bot, group is restored).

Design constraints (per PraisonAI principles):
  - Wrapper-only — heavy code stays out of the core SDK.
  - Lazy/stdlib only — JSON + atomic file replace, no extra dependency.
  - Default OFF — ``DeliveryRouter`` works exactly as before unless a registry
    is constructed and attached.
  - Bounded: ``max_size`` + ``ttl_seconds`` prevent unbounded growth/staleness.
  - Thread-safe: a per-instance ``threading.Lock`` guards mutation + persistence.
  - Persistence is best-effort: failures are logged, never raised.

Public API:
  - ``DeadTargetRegistry(persist_path=None, *, max_size=10_000, ttl_seconds=...)``
  - ``is_dead(platform, channel_id) -> bool``
  - ``should_reprobe(platform, channel_id) -> bool``  (periodic self-heal probe)
  - ``mark_dead(platform, channel_id, reason) -> None``
  - ``clear(platform, channel_id) -> None``  (called on every success)
  - ``list_dead() -> list[DeadTarget]``
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ._delivery_control_store import DeliveryControlStore

logger = logging.getLogger(__name__)

# 30 days default — a kicked bot is rarely re-added within seconds, but we still
# want the registry to forget very old entries so a target that was dead long
# ago is re-probed eventually even if no traffic ever cleared it.
_DEFAULT_TTL_SECONDS = 30 * 86400
_DEFAULT_MAX_SIZE = 10_000
# How long to fully suppress a dead target before allowing a single re-probe.
# A kicked bot is rarely re-added within seconds, but waiting the full 30-day
# TTL to retry a *recovered* target is far too long. Letting one send through
# roughly once an hour bounds self-heal latency to ~1h while still suppressing
# the overwhelming majority of doomed cycles.
_DEFAULT_REPROBE_SECONDS = 3600


@dataclass(frozen=True)
class DeadTarget:
    """A single target confirmed permanently unreachable."""

    platform: str
    channel_id: str
    reason: str
    ts: float


class DeadTargetRegistry:
    """Persistent, bounded, self-healing registry of dead delivery targets.

    Args:
        persist_path: JSON file path for durability. Defaults to
            ``~/.praisonai/state/dead_targets.json``. Pass ``None`` explicitly
            via ``persist=False`` semantics is not supported; use a temp path
            for ephemeral instances in tests.
        max_size: Maximum dead entries kept; oldest evicted when exceeded.
        ttl_seconds: Entries older than this are dropped on the next access so
            a long-dead target is eventually re-probed.

    Example::

        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry()
        if reg.is_dead("telegram", "-1001234"):
            ...  # short-circuit
        reg.mark_dead("telegram", "-1001234", reason="403 Forbidden: bot kicked")
        reg.clear("telegram", "-1001234")  # on next successful send
    """

    def __init__(
        self,
        persist_path: Optional[Path] = None,
        *,
        max_size: int = _DEFAULT_MAX_SIZE,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        reprobe_seconds: int = _DEFAULT_REPROBE_SECONDS,
        store: Optional["DeliveryControlStore"] = None,
    ) -> None:
        state_dir = Path.home() / ".praisonai" / "state"
        self.max_size = int(max_size)
        self.ttl_seconds = int(ttl_seconds)
        self.reprobe_seconds = int(reprobe_seconds)
        self._lock = threading.Lock()
        # (platform, channel_id) -> DeadTarget
        self._dead: Dict[Tuple[str, str], DeadTarget] = {}
        # Shared SQLite store: when provided, dead targets are stored as rows
        # (atomic upsert) that survive restart and are correct across workers,
        # instead of the per-process in-memory dict + whole-file JSON rewrite
        # (issue #2579). Single-process gateways keep the JSON path (default).
        self._store = store
        if store is not None:
            # The store's dead-target TTL/bound sweeps are table-wide, so every
            # registry sharing one store must agree on ``ttl_seconds`` /
            # ``max_size``. Register this registry's bounds; a later registry
            # attaching to the same store with divergent settings fails loudly
            # instead of silently pruning this registry's suppressions
            # (Greptile P1, issue #2579).
            store.register_dead_config(self.ttl_seconds, self.max_size)
            self._persist_path = None
            return
        self._persist_path = Path(
            persist_path or (state_dir / "dead_targets.json")
        ).expanduser()
        self._load()

    # ── Helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _key(platform: str, channel_id: str) -> Tuple[str, str]:
        return (str(platform).lower(), str(channel_id))

    def _evict_expired_locked(self) -> bool:
        """Drop expired entries. Caller must hold the lock. Returns True if changed."""
        if self.ttl_seconds <= 0:
            return False
        cutoff = time.time() - self.ttl_seconds
        stale = [k for k, v in self._dead.items() if v.ts < cutoff]
        for k in stale:
            self._dead.pop(k, None)
        return bool(stale)

    def _enforce_bound_locked(self) -> None:
        """Evict oldest entries beyond ``max_size``. Caller must hold the lock."""
        if self.max_size <= 0 or len(self._dead) <= self.max_size:
            return
        # Oldest first by timestamp.
        ordered = sorted(self._dead.items(), key=lambda kv: kv[1].ts)
        overflow = len(self._dead) - self.max_size
        for k, _ in ordered[:overflow]:
            self._dead.pop(k, None)

    # ── Persistence (best-effort, atomic) ───────────────────────────
    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            with open(self._persist_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("DeadTargetRegistry: failed to load %s: %s", self._persist_path, e)
            return
        entries = data.get("dead", []) if isinstance(data, dict) else []
        if not isinstance(entries, list):
            return
        for item in entries:
            try:
                platform = str(item["platform"]).lower()
                channel_id = str(item["channel_id"])
                reason = str(item.get("reason", ""))
                ts = float(item.get("ts", time.time()))
            except (KeyError, TypeError, ValueError):
                continue
            self._dead[(platform, channel_id)] = DeadTarget(
                platform=platform, channel_id=channel_id, reason=reason, ts=ts
            )
        # Prune anything already expired/over-bound on load.
        self._evict_expired_locked()
        self._enforce_bound_locked()
        logger.info(
            "DeadTargetRegistry: loaded %d dead target(s) from %s",
            len(self._dead),
            self._persist_path,
        )

    def _save_locked(self) -> None:
        """Persist current state. Caller must hold the lock."""
        try:
            data = {
                "dead": [
                    {
                        "platform": v.platform,
                        "channel_id": v.channel_id,
                        "reason": v.reason,
                        "ts": v.ts,
                    }
                    for v in self._dead.values()
                ]
            }
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self._persist_path)
        except Exception as e:
            logger.error("DeadTargetRegistry: failed to save %s: %s", self._persist_path, e)

    # ── Public API ──────────────────────────────────────────────────
    def is_dead(self, platform: str, channel_id: str) -> bool:
        """Return True if the target is currently suppressed as dead."""
        key = self._key(platform, channel_id)
        if self._store is not None:
            ts = self._store.dead_get_ts(key[0], key[1])
            if ts is None:
                return False
            if self.ttl_seconds > 0 and ts < time.time() - self.ttl_seconds:
                self._store.dead_clear(key[0], key[1])
                return False
            return True
        with self._lock:
            entry = self._dead.get(key)
            if entry is None:
                return False
            # Honour TTL lazily so a long-dead target re-enters circulation.
            if self.ttl_seconds > 0 and entry.ts < time.time() - self.ttl_seconds:
                self._dead.pop(key, None)
                self._save_locked()
                return False
            return True

    def should_reprobe(self, platform: str, channel_id: str) -> bool:
        """Return True if a dead target is due for a single self-healing re-probe.

        A suppressed target can only prove it has recovered by being sent to, but
        ``is_dead`` would otherwise block every send until the (long) TTL expires.
        To bound self-heal latency, once ``reprobe_seconds`` has elapsed since the
        target was last marked dead we allow *one* send through. If it succeeds,
        :meth:`clear` un-suppresses it; if it fails permanently again,
        :meth:`mark_dead` resets the clock for another ``reprobe_seconds`` window.
        """
        if self.reprobe_seconds <= 0:
            return False
        key = self._key(platform, channel_id)
        if self._store is not None:
            ts = self._store.dead_get_ts(key[0], key[1])
            if ts is None:
                return False
            return ts < time.time() - self.reprobe_seconds
        with self._lock:
            entry = self._dead.get(key)
            if entry is None:
                return False
            return entry.ts < time.time() - self.reprobe_seconds

    def mark_dead(self, platform: str, channel_id: str, reason: str) -> None:
        """Record a confirmed-permanent failure, suppressing future sends."""
        key = self._key(platform, channel_id)
        if self._store is not None:
            already = self._store.dead_get_ts(key[0], key[1]) is not None
            self._store.dead_mark(key[0], key[1], str(reason))
            self._store.dead_enforce_bound(self.max_size)
            if not already:
                logger.warning(
                    "DeadTargetRegistry: suppressing dead target %s:%s (%s)",
                    key[0],
                    key[1],
                    reason,
                )
            return
        with self._lock:
            already = key in self._dead
            self._dead[key] = DeadTarget(
                platform=key[0], channel_id=key[1], reason=str(reason), ts=time.time()
            )
            self._enforce_bound_locked()
            self._save_locked()
        if not already:
            logger.warning(
                "DeadTargetRegistry: suppressing dead target %s:%s (%s)",
                key[0],
                key[1],
                reason,
            )

    def clear(self, platform: str, channel_id: str) -> None:
        """Un-suppress a target. Called on every successful send (self-healing)."""
        key = self._key(platform, channel_id)
        if self._store is not None:
            if self._store.dead_get_ts(key[0], key[1]) is None:
                return
            self._store.dead_clear(key[0], key[1])
            logger.info(
                "DeadTargetRegistry: target %s:%s recovered — suppression cleared",
                key[0],
                key[1],
            )
            return
        with self._lock:
            if key not in self._dead:
                return
            self._dead.pop(key, None)
            self._save_locked()
        logger.info(
            "DeadTargetRegistry: target %s:%s recovered — suppression cleared",
            key[0],
            key[1],
        )

    def list_dead(self) -> List[DeadTarget]:
        """Return a snapshot of currently-dead targets (expired ones pruned)."""
        if self._store is not None:
            if self.ttl_seconds > 0:
                self._store.dead_expire(time.time() - self.ttl_seconds)
            return [
                DeadTarget(platform=p, channel_id=c, reason=r, ts=t)
                for (p, c, r, t) in self._store.dead_list()
            ]
        with self._lock:
            if self._evict_expired_locked():
                self._save_locked()
            return sorted(self._dead.values(), key=lambda d: d.ts)

    def size(self) -> int:
        """Number of currently-suppressed targets (expired ones pruned)."""
        if self._store is not None:
            if self.ttl_seconds > 0:
                self._store.dead_expire(time.time() - self.ttl_seconds)
            return self._store.dead_count()
        with self._lock:
            if self._evict_expired_locked():
                self._save_locked()
            return len(self._dead)
