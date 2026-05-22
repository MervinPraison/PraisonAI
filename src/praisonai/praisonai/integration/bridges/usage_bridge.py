"""Wire core token usage collector to optional persistence sink."""

from __future__ import annotations

from typing import Any, Optional


def register_usage_sink() -> Optional[Any]:
    """Attach global token collector to in-memory sink when available."""
    try:
        from praisonaiagents.telemetry.protocols import (
            InMemoryTokenUsageSink,
            InMemoryUsageQuery,
            TokenCollectorUsageQuery,
        )
        from praisonaiagents.telemetry.token_collector import get_token_collector

        sink = InMemoryTokenUsageSink()
        collector = get_token_collector()
        collector.set_sink(sink)
        return sink
    except ImportError:
        return None


def get_usage_query():
    """Return UsageQueryProtocol adapter for UI consumption."""
    try:
        from praisonaiagents.telemetry.protocols import (
            InMemoryUsageQuery,
            TokenCollectorUsageQuery,
        )
        from praisonaiagents.telemetry.token_collector import get_token_collector

        collector = get_token_collector()
        sink = getattr(collector, "_sink", None)
        if sink is not None and hasattr(sink, "records"):
            return InMemoryUsageQuery(sink)
        return TokenCollectorUsageQuery(collector)
    except ImportError:
        return None
