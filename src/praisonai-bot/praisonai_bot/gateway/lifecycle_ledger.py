"""Durable, boot-scoped process-lifecycle ledger for the gateway (Issue #4603).

The core SDK ships only the pure contract and decisions
(:class:`praisonaiagents.gateway.LifecycleRecord`,
:func:`praisonaiagents.gateway.classify_unclean_exit`,
:class:`praisonaiagents.gateway.PersistentRestartLoopGuard`,
:func:`praisonaiagents.gateway.classify_resource_pressure`). This wrapper module
owns the heavyweight, OS-specific mechanism those helpers deliberately avoid:

* a small durable sentinel file the runtime restamps on boot / shutdown and
  folds a memory sample into on every heartbeat, so the *next* boot can detect
  that the previous process died uncleanly (OOM-kill / ``SIGKILL`` run no
  handler, so signal-based forensics never fire for them);
* ``/proc`` + cgroup memory sampling and ``shutil.disk_usage`` disk headroom so
  ``GET /health`` can classify redaction-safe memory/disk *pressure*; and
* a :class:`praisonaiagents.gateway.RestartStoreProtocol` backed by the same
  sentinel so the restart-loop breaker survives the very restart it guards.

Everything here is best-effort and defensive: a sample must never raise and a
persistence failure must degrade to in-memory behaviour rather than crash the
gateway it is meant to protect.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from praisonaiagents.gateway import (
    LifecycleRecord,
    PersistentRestartLoopGuard,
    classify_resource_pressure,
    classify_unclean_exit,
)

from .memory_pressure import CgroupMemoryPressure

logger = logging.getLogger(__name__)


class LifecycleLedger:
    """Durable process-lifecycle record maintained by the gateway runtime.

    On boot the ledger reads the prior sentinel, classifies whether the previous
    process exited cleanly, and restamps ``phase="running"`` (see
    :meth:`record_boot`). A cheap :meth:`sample_memory` folds the current
    memory-budget fraction into the record so a *later* unclean death is flagged
    ``suspected_oom``. :meth:`mark_exited` stamps a clean exit on the graceful
    stop path only.

    Args:
        path: Sentinel file path. Its parent directory is created best-effort.
        memory_budget_fraction: Budget fraction at/above which memory pressure
            is classified ``critical`` (also the OOM-suspicion threshold).
        disk_min_free_mb: Free-disk floor (MiB) below which disk is ``critical``.
    """

    def __init__(
        self,
        path: str,
        *,
        memory_budget_fraction: float = 0.9,
        disk_min_free_mb: float = 512.0,
    ):
        self.path = path
        self.memory_budget_fraction = float(memory_budget_fraction)
        self.disk_min_free_mb = float(disk_min_free_mb)
        self._mem = CgroupMemoryPressure()
        self._record: LifecycleRecord = LifecycleRecord()
        # Set on the first boot classification so /health can report the last
        # exit without re-reading the file; None until record_boot() runs.
        self._boot_exit_kind: Optional[str] = None
        self._boot_suspected_oom: bool = False
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        except OSError as exc:  # pragma: no cover - defensive
            logger.debug("lifecycle: could not prepare sentinel dir: %s", exc)

    # ── persistence (best-effort) ──

    def _read(self) -> Optional[LifecycleRecord]:
        try:
            with open(self.path, "r") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        return LifecycleRecord.from_dict(data)

    def _write(self, record: LifecycleRecord) -> None:
        """Atomically persist ``record`` to the sentinel; never raises."""
        tmp = f"{self.path}.tmp.{os.getpid()}"
        try:
            with open(tmp, "w") as fh:
                json.dump(record.to_dict(), fh)
            os.replace(tmp, self.path)
        except OSError as exc:  # pragma: no cover - defensive
            logger.debug("lifecycle: could not persist sentinel: %s", exc)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    # ── lifecycle transitions ──

    def record_boot(self) -> LifecycleRecord:
        """Read the prior sentinel, classify its exit, and restamp ``running``.

        Returns the fresh boot record. When the previous process was still
        ``running`` in its last write, the record's ``exit_kind`` is
        ``"unclean"`` (and ``suspected_oom`` when its last memory sample was
        high) — the boot-time signal that a signal-less OOM/``SIGKILL`` occurred.
        """
        prev = self._read()
        record = classify_unclean_exit(
            prev, oom_fraction=self.memory_budget_fraction
        )
        self._boot_exit_kind = record.exit_kind
        self._boot_suspected_oom = record.suspected_oom
        # Stamp our own pid-owned boot marker so a graceful stop from *this*
        # process can be told apart from a stale file another process left.
        self._record = record
        self._owner_pid = os.getpid()
        self._write(record)
        if record.exit_kind == "unclean":
            logger.warning(
                "Gateway previous process exited uncleanly%s "
                "(no graceful-stop marker; suspected OOM/SIGKILL)",
                " — suspected OOM" if record.suspected_oom else "",
            )
        return record

    def sample_memory(self) -> Optional[float]:
        """Fold a fresh memory-budget fraction into the sentinel (<1ms).

        Returns the sampled fraction (anon RSS / cgroup budget) in ``[0, ∞)`` or
        ``None`` when the platform has no cgroup limit to measure against. Cheap
        enough to call from the heartbeat; persists the running record so a
        subsequent hard-kill leaves the last sample behind for OOM suspicion.
        """
        frac = self._memory_fraction()
        record = LifecycleRecord(
            phase="running",
            exit_kind=self._record.exit_kind,
            suspected_oom=self._record.suspected_oom,
            last_mem_fraction=frac,
            restart_events=list(self._record.restart_events),
        )
        self._record = record
        self._write(record)
        return frac

    def mark_exited(self) -> None:
        """Stamp a clean exit — graceful-stop path only, ownership-checked.

        Only the process that wrote the boot marker may record a clean exit, so
        a late call from a forked/stale context cannot mask another process's
        unclean death.
        """
        if getattr(self, "_owner_pid", None) != os.getpid():
            return
        record = LifecycleRecord(
            phase="exited",
            exit_kind="clean",
            suspected_oom=False,
            last_mem_fraction=self._record.last_mem_fraction,
            restart_events=list(self._record.restart_events),
        )
        self._record = record
        self._write(record)

    # ── health surface ──

    def _memory_fraction(self) -> Optional[float]:
        """Anon RSS / cgroup budget fraction, or ``None`` when unmeasurable."""
        try:
            budget = self._mem.cgroup_limit_mb()
            if not budget or budget <= 0:
                return None
            rss = self._mem.anon_rss_mb()
            return float(rss) / float(budget)
        except Exception:
            return None

    def _disk_free_mb(self) -> Optional[float]:
        try:
            usage = shutil.disk_usage(os.path.dirname(self.path) or ".")
            return float(usage.free) / (1024.0 * 1024.0)
        except Exception:
            return None

    def pressure(self) -> Dict[str, str]:
        """Return the coarse ``{"memory", "disk"}`` pressure block for /health."""
        return classify_resource_pressure(
            mem_fraction=self._memory_fraction(),
            disk_free_mb=self._disk_free_mb(),
            mem_critical=self.memory_budget_fraction,
            disk_min_free_mb=self.disk_min_free_mb,
        )

    def last_exit(self) -> Dict[str, Any]:
        """Return the ``{"last_exit", "suspected_oom"}`` lifecycle block."""
        return {
            "last_exit": self._boot_exit_kind or "unknown",
            "suspected_oom": bool(self._boot_suspected_oom),
        }


class SentinelRestartStore:
    """A :class:`RestartStoreProtocol` backed by the lifecycle sentinel file.

    Reads / writes only the ``restart_events`` slice of the durable
    :class:`LifecycleRecord`, so the persistent restart-loop breaker shares one
    file with the lifecycle ledger instead of introducing a second sentinel.
    Best-effort on both ends: a read failure yields ``[]`` and a write failure
    is swallowed, degrading the breaker to in-memory behaviour.
    """

    def __init__(self, ledger: LifecycleLedger):
        self._ledger = ledger

    def load_events(self) -> List[float]:
        record = self._ledger._read()
        if record is None:
            return list(self._ledger._record.restart_events)
        return list(record.restart_events)

    def save_events(self, events: List[float]) -> None:
        rec = self._ledger._record
        merged = LifecycleRecord(
            phase=rec.phase,
            exit_kind=rec.exit_kind,
            suspected_oom=rec.suspected_oom,
            last_mem_fraction=rec.last_mem_fraction,
            restart_events=[float(t) for t in events],
        )
        self._ledger._record = merged
        self._ledger._write(merged)


def default_sentinel_path() -> str:
    """Return the default lifecycle sentinel path under ``~/.praisonai``."""
    return os.path.join(
        os.path.expanduser("~"), ".praisonai", "gateway", "lifecycle.json"
    )


def build_persistent_restart_guard(
    ledger: LifecycleLedger,
    *,
    max_restarts: int = 3,
    window_seconds: float = 3600.0,
) -> PersistentRestartLoopGuard:
    """Construct a durable restart-loop guard sharing the ledger's sentinel."""
    return PersistentRestartLoopGuard(
        SentinelRestartStore(ledger),
        max_restarts=max_restarts,
        window_seconds=window_seconds,
    )


__all__ = [
    "LifecycleLedger",
    "SentinelRestartStore",
    "default_sentinel_path",
    "build_persistent_restart_guard",
]
