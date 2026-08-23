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

    from praisonai_bot.bots import GatewayMetrics

    metrics = GatewayMetrics()
    metrics.inc("messages_inbound_total")
    metrics.inc("outbound_failed_total", labels={"channel": "telegram"})
    metrics.set_gauge("outbox_depth", 3)
    with metrics.timer("gateway_turn_latency_seconds", labels={"platform": "telegram"}):
        ...                              # observe a duration distribution
    text = metrics.render_prometheus()   # serve at GET /metrics
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, List, Optional, Tuple

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
    "prompt_cache_invalidations_total": (
        "Total turns whose prompt prefix (model + tool schemas + system prompt) "
        "changed from the previous turn, invalidating the provider prompt cache."
    ),
}

_GAUGE_HELP: Dict[str, str] = {
    "outbox_depth": "Current number of messages pending outbound delivery.",
    "approval_pending": "Current number of approvals awaiting a decision.",
    "active_sessions": "Current number of active gateway sessions.",
    "channel_recoveries": "Total supervision recoveries per channel.",
}

_HISTOGRAM_HELP: Dict[str, str] = {
    "gateway_turn_latency_seconds": "Turn latency (inbound received -> reply delivered).",
    "gateway_llm_latency_seconds": "LLM-call latency in seconds.",
    "gateway_tool_latency_seconds": "Tool-call latency in seconds.",
    "gateway_queue_wait_seconds": "Admission/queue wait time before dispatch.",
    "gateway_outbound_latency_seconds": "Outbound send latency in seconds.",
}

# Sane default buckets (seconds) covering sub-second to multi-second turns.
DEFAULT_BUCKETS: Tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)

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


def _fmt_bound(bound: float) -> str:
    """Render a bucket upper bound without a trailing ``.0`` for whole numbers."""
    if bound == int(bound):
        return str(int(bound))
    return repr(bound)


def _validate_buckets(buckets: Tuple[float, ...]) -> Tuple[float, ...]:
    """Coerce and validate bucket bounds: finite and strictly increasing.

    The implicit ``+Inf`` bucket is always appended at render time, so callers
    supply only the finite upper bounds here.
    """
    bounds = tuple(float(b) for b in buckets)
    if not bounds:
        raise ValueError("histogram buckets must be non-empty")
    previous: Optional[float] = None
    for bound in bounds:
        if bound != bound or bound in (float("inf"), float("-inf")):
            raise ValueError(f"histogram bucket bound must be finite: {bound!r}")
        if previous is not None and bound <= previous:
            raise ValueError(
                "histogram bucket bounds must be strictly increasing: "
                f"{bounds!r}"
            )
        previous = bound
    return bounds


class _HistData:
    """Mutable per-label-set histogram accumulator."""

    __slots__ = ("counts", "sum", "count")

    def __init__(self, counts: List[int], total: float, count: int) -> None:
        self.counts = counts
        self.sum = total
        self.count = count

    def copy(self) -> "_HistData":
        return _HistData(list(self.counts), self.sum, self.count)


class GatewayMetrics:
    """Thread-safe, dependency-free message-flow metrics registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # name -> label_key -> value
        self._counters: Dict[str, Dict[_LabelKey, float]] = {}
        self._gauges: Dict[str, Dict[_LabelKey, float]] = {}
        # name -> callable returning a live value (e.g. outbox_depth probe)
        self._gauge_providers: Dict[str, Callable[[], float]] = {}
        # name -> label_key -> {"buckets": {le: count}, "sum": float, "count": int}
        self._histograms: Dict[str, Dict[_LabelKey, _HistData]] = {}
        self._histogram_buckets: Dict[str, Tuple[float, ...]] = {}

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

    # ── Histograms ──────────────────────────────────
    def observe(
        self,
        name: str,
        seconds: float,
        buckets: Tuple[float, ...] = DEFAULT_BUCKETS,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a duration observation into a histogram.

        Accumulates cumulative bucket counts plus running ``_sum``/``_count`` so
        the exposition can render Prometheus histogram series and clients can
        compute p50/p95/p99.
        """
        if labels and "le" in labels:
            raise ValueError("'le' is a reserved histogram label name")
        value = float(seconds)
        key = _label_key(labels)
        new_bounds = _validate_buckets(buckets)
        with self._lock:
            existing = self._histogram_buckets.get(name)
            if existing is None:
                bounds = new_bounds
                self._histogram_buckets[name] = bounds
            elif existing != new_bounds:
                raise ValueError(
                    f"histogram {name!r} already registered with different "
                    f"buckets {existing!r}; cannot re-register {new_bounds!r}"
                )
            else:
                bounds = existing
            series = self._histograms.setdefault(name, {})
            data = series.get(key)
            if data is None:
                data = _HistData(counts=[0] * len(bounds), total=0.0, count=0)
                series[key] = data
            for i, bound in enumerate(bounds):
                if value <= bound:
                    data.counts[i] += 1
            data.sum += value
            data.count += 1

    @contextmanager
    def timer(
        self,
        name: str,
        buckets: Tuple[float, ...] = DEFAULT_BUCKETS,
        labels: Optional[Dict[str, str]] = None,
    ) -> Iterator[None]:
        """Context manager timing its body and recording it via :meth:`observe`."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(
                name, time.perf_counter() - start, buckets=buckets, labels=labels
            )

    # ── Snapshot / rendering ────────────────────────────────────────
    def snapshot(self) -> Dict[str, Dict[str, float]]:
        """Return a plain-dict snapshot for JSON callers or tests.

        Series with labels are flattened to ``name{a="b"}`` keys; unlabelled
        series use the bare ``name``.
        """
        out: Dict[str, Dict[str, float]] = {
            "counters": {},
            "gauges": {},
            "histograms": {},
        }
        with self._lock:
            for name, series in self._counters.items():
                for key, value in series.items():
                    out["counters"][name + _render_labels(key)] = value
            gauges = {
                name: dict(series) for name, series in self._gauges.items()
            }
            providers = dict(self._gauge_providers)
            for name, series in self._histograms.items():
                bounds = self._histogram_buckets.get(name, ())
                for key, data in series.items():
                    rendered = _render_labels(key)
                    out["histograms"][name + "_count" + rendered] = float(data.count)
                    out["histograms"][name + "_sum" + rendered] = data.sum
                    for i, bound in enumerate(bounds):
                        out["histograms"][
                            f"{name}_bucket" + _render_labels(
                                key + (("le", _fmt_bound(bound)),)
                            )
                        ] = float(data.counts[i])
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
            histograms = {
                name: {k: v.copy() for k, v in series.items()}
                for name, series in self._histograms.items()
            }
            histogram_bounds = dict(self._histogram_buckets)

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

        for name in sorted(histograms):
            help_text = _HISTOGRAM_HELP.get(name, name)
            bounds = histogram_bounds.get(name, ())
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} histogram")
            for key in sorted(histograms[name]):
                data = histograms[name][key]
                for i, bound in enumerate(bounds):
                    bucket_key = key + (("le", _fmt_bound(bound)),)
                    lines.append(
                        f"{name}_bucket{_render_labels(bucket_key)} "
                        f"{data.counts[i]}"
                    )
                inf_key = key + (("le", "+Inf"),)
                lines.append(
                    f"{name}_bucket{_render_labels(inf_key)} {data.count}"
                )
                lines.append(f"{name}_sum{_render_labels(key)} {data.sum}")
                lines.append(f"{name}_count{_render_labels(key)} {data.count}")

        return "\n".join(lines) + "\n"


__all__ = ["GatewayMetrics"]
