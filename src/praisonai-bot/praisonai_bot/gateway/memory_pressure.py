"""Concrete cgroup-aware memory-pressure reader for the gateway (Issue #3804).

The core SDK ships the *decision* — :func:`praisonaiagents.gateway.plan_pressure_evictions`
plus the :class:`praisonaiagents.gateway.MemoryPressureProtocol` contract — but the
*mechanism* (reading the container's real memory ceiling and the process's own
anonymous RSS) belongs in the running gateway. This module is that mechanism: a
tiny, stdlib-only implementation of ``MemoryPressureProtocol`` so the eviction
budget tracks the actual cgroup limit the process runs under (``memory.high`` /
``memory.max`` on cgroup v2, ``memory.limit_in_bytes`` on v1) rather than total
host RAM or a hard-coded number.

Every probe degrades to ``None``/``0.0`` when the platform cannot report it, so
``BotSessionManager.sweep_under_pressure`` becomes a safe no-op on hosts without
a cgroup limit — preserving today's behaviour exactly.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_MIB = 1024.0 * 1024.0

# cgroup v2 reports "no limit" as this literal; v1 uses a very large sentinel.
_V2_MAX = "max"
# A cgroup v1 limit at/above this many bytes means "unlimited" in practice
# (kernels expose PAGE_COUNTER_MAX * PAGE_SIZE, ~8 EiB); treat as no limit.
_V1_UNLIMITED_BYTES = 1 << 62


class CgroupMemoryPressure:
    """Read the container memory budget and anonymous RSS via cgroup + procfs.

    Implements :class:`praisonaiagents.gateway.MemoryPressureProtocol`. All I/O
    is best-effort and swallowed: a probe that cannot read its source returns
    ``None`` (budget) or ``0.0`` (RSS) so the pressure sweep never crashes the
    gateway it is meant to protect.
    """

    def cgroup_limit_mb(self) -> Optional[float]:
        """Return the container memory limit in MiB, or ``None`` if unknown.

        Prefers cgroup v2 ``memory.high`` (the soft throttle ceiling the kernel
        reclaims against) then ``memory.max`` (the hard OOM ceiling); falls back
        to cgroup v1 ``memory.limit_in_bytes``. Returns ``None`` when no finite
        limit is configured (unconstrained host).
        """
        for path in (
            "/sys/fs/cgroup/memory.high",  # cgroup v2 soft limit
            "/sys/fs/cgroup/memory.max",   # cgroup v2 hard limit
        ):
            mb = self._read_v2_limit(path)
            if mb is not None:
                return mb
        # cgroup v1 fallback
        return self._read_v1_limit("/sys/fs/cgroup/memory/memory.limit_in_bytes")

    def anon_rss_mb(self) -> float:
        """Return current anonymous (non-reclaimable) RSS in MiB.

        Reads ``RssAnon`` from ``/proc/self/status`` (Linux). Anonymous RSS is
        the memory that *cannot* be reclaimed by dropping caches — the pages
        that actually push a container toward its cgroup ceiling. Returns
        ``0.0`` when unavailable (non-Linux / unreadable), which makes the
        planner a no-op.
        """
        try:
            with open("/proc/self/status", "r") as fh:
                for line in fh:
                    if line.startswith("RssAnon:"):
                        # Format: "RssAnon:\t   12345 kB"
                        parts = line.split()
                        if len(parts) >= 2:
                            return float(parts[1]) / 1024.0
        except (OSError, ValueError):
            pass
        return 0.0

    @staticmethod
    def _read_v2_limit(path: str) -> Optional[float]:
        try:
            with open(path, "r") as fh:
                raw = fh.read().strip()
        except OSError:
            return None
        if not raw or raw == _V2_MAX:
            return None
        try:
            return float(int(raw)) / _MIB
        except ValueError:
            return None

    @staticmethod
    def _read_v1_limit(path: str) -> Optional[float]:
        try:
            with open(path, "r") as fh:
                raw = fh.read().strip()
        except OSError:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        if value <= 0 or value >= _V1_UNLIMITED_BYTES:
            return None
        return float(value) / _MIB
