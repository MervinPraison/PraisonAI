"""
Message-flow metrics for the PraisonAI gateway.

Provides a tiny, dependency-free metrics registry so the gateway can expose
throughput/flow counters and gauges (``messages_inbound_total``,
``outbound_failed_total``, ``outbox_depth``, per-channel error counts, ...)
over a ``/metrics`` endpoint in Prometheus text-exposition format.

Design constraints (per PraisonAI principles):
  - Wrapper-only — gateway infrastructure, not a core/agent concern.
  - Zero-dependency: stdlib only; no ``prometheus_client`` requirement. If
    ``prometheus_client`` happens to be installed, callers may still scrape
    this surface since the output follows the text format.
  - Thread-safe: a single lock guards all mutations so background supervision
    threads and the asyncio loop can both update counters safely.
  - Optional: nothing here runs unless the gateway constructs a registry.

Usage::

    from praisonai.bots import GatewayMetrics

    metrics = GatewayMetrics()
    metrics.inc("messages_inbound_total")
    metrics.inc("outbound_failed_total", labels={"channel": "telegram"})
    metrics.set_gauge("outbox_depth", 3)
    text = metrics.render_prometheus()   # serve at GET /metrics
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional, Tuple

# Stable metric names + help text so the exposition output is self-describing.
_COUNTER_HELP: Dict[str, str] = {
    "messages_inbound_total": "Total inbound messages received by the gateway.",
    "messages_dispatched_total": "Total inbound messages dispatched to an agent run.",
    "messages_duplicate_total": "Total inbound messages dropped as duplicates.",
    "outbound_sent_total": "Total outbound messages successfully delivered.",
    "outbound_failed_total": "Total outbound messages that failed delivery.",
    "approval_pending_total": "Total approval requests created.",
    "approval_decided_total": "Total approval requests decided (allowed or denied).",
    "channel_errors_total": "Total channel errors observed by supervision.",
    "channel_restarts_total": "Total channel restarts performed by supervision.",
}

_GAUGE_HELP: Dict[str, str] = {
    "outbox_depth": "Current number of messages pending outbound delivery.",
    "approval_pending": "Current number of approvals awaiting a decision.",
    "active_sessions": "Current number of active gateway sessions.",
    "channel_recoveries": "Total supervision recoveries per channel.",
}

# A label set is a sorted tuple of (name, value) pairs so it is hashable and
# renders deterministically.
_LabelKey = Tuple[Tuple[str, str], ...]


def _label_key(labels: Optional[Dict[str, str]]) -> _LabelKey:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _render_labels(key: _LabelKey) -> str:
    if not key:
        return ""
    inner = ",".join(f'{name}="{_escape(value)}"' for name, value in key)
    return "{" + inner + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class GatewayMetrics:
    """Thread-safe, dependency-free message-flow metrics registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # name -> label_key -> value
        self._counters: Dict[str, Dict[_LabelKey, float]] = {}
        self._gauges: Dict[str, Dict[_LabelKey, float]] = {}
        # name -> callable returning a live value (e.g. outbox_depth probe)
        self._gauge_providers: Dict[str, Callable[[], float]] = {}

    # ── Counters ────────────────────────────────────────────────────
    def inc(
        self,
        name: str,
        amount: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter (monotonically increasing)."""
        key = _label_key(labels)
        with self._lock:
            series = self._counters.setdefault(name, {})
            series[key] = series.get(key, 0.0) + amount

    def counter_value(
        self, name: str, labels: Optional[Dict[str, str]] = None
    ) -> float:
        key = _label_key(labels)
        with self._lock:
            return self._counters.get(name, {}).get(key, 0.0)

    # ── Gauges ──────────────────────────────────────────────────────
    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge to an absolute value."""
        key = _label_key(labels)
        with self._lock:
            self._gauges.setdefault(name, {})[key] = float(value)

    def register_gauge_provider(
        self, name: str, provider: Callable[[], float]
    ) -> None:
        """Register a callable sampled at render time for a live gauge value.

        Useful for values derived from external state (e.g. an ``OutboundQueue``
        ``pending_count``) so ``/metrics`` always reflects the current depth
        without the caller pushing updates.
        """
        with self._lock:
            self._gauge_providers[name] = provider

    def gauge_value(
        self, name: str, labels: Optional[Dict[str, str]] = None
    ) -> float:
        key = _label_key(labels)
        with self._lock:
            if key == () and name in self._gauge_providers:
                try:
                    return float(self._gauge_providers[name]())
                except Exception:
                    pass
            return self._gauges.get(name, {}).get(key, 0.0)

    # ── Snapshot / rendering ────────────────────────────────────────
    def snapshot(self) -> Dict[str, Dict[str, float]]:
        """Return a plain-dict snapshot for JSON callers or tests.

        Series with labels are flattened to ``name{a="b"}`` keys; unlabelled
        series use the bare ``name``.
        """
        out: Dict[str, Dict[str, float]] = {"counters": {}, "gauges": {}}
        with self._lock:
            for name, series in self._counters.items():
                for key, value in series.items():
                    out["counters"][name + _render_labels(key)] = value
            gauges = {
                name: dict(series) for name, series in self._gauges.items()
            }
            providers = dict(self._gauge_providers)
        for name, provider in providers.items():
            try:
                gauges.setdefault(name, {})[()] = float(provider())
            except Exception:
                continue
        for name, series in gauges.items():
            for key, value in series.items():
                out["gauges"][name + _render_labels(key)] = value
        return out

    def render_prometheus(self) -> str:
        """Render all metrics in Prometheus text-exposition format."""
        lines: List[str] = []
        with self._lock:
            counters = {
                name: dict(series) for name, series in self._counters.items()
            }
            gauges = {name: dict(series) for name, series in self._gauges.items()}
            providers = dict(self._gauge_providers)

        # Sample live gauge providers outside the lock.
        for name, provider in providers.items():
            try:
                gauges.setdefault(name, {})[()] = float(provider())
            except Exception:
                continue

        for name in sorted(counters):
            help_text = _COUNTER_HELP.get(name, name)
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} counter")
            for key in sorted(counters[name]):
                lines.append(f"{name}{_render_labels(key)} {counters[name][key]}")

        for name in sorted(gauges):
            help_text = _GAUGE_HELP.get(name, name)
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} gauge")
            for key in sorted(gauges[name]):
                lines.append(f"{name}{_render_labels(key)} {gauges[name][key]}")

        return "\n".join(lines) + "\n"


__all__ = ["GatewayMetrics"]
