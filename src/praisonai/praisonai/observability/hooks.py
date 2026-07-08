"""
Observability hooks for PraisonAI.

Centralizes observability initialization (AgentOps, etc.) so it can be 
used consistently across all entry points without duplicating logic.
"""

import os
import sys
import inspect
import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Sinks installed via entry-point discovery for the current run. Torn down in
# finalize_observability so flush()/close() always runs.
_installed_sinks: List[Any] = []


class _FanoutSink:
    """TraceSinkProtocol implementation that forwards to every registered sink.

    Lets multiple third-party sinks (e.g. Langfuse + Arize + a custom sink) all
    receive the same trace stream instead of the last-registered one replacing
    the rest. Every per-sink call is guarded so a broken sink can't break a run.
    """

    def __init__(self, sinks: List[Any]):
        self._sinks = list(sinks)

    def emit(self, event: Any) -> None:
        for s in self._sinks:
            try:
                s.emit(event)
            except Exception:  # noqa: BLE001 -- telemetry must not crash the caller
                logger.debug("sink emit failed", exc_info=True)

    def flush(self) -> None:
        for s in self._sinks:
            try:
                s.flush()
            except Exception:  # noqa: BLE001
                logger.debug("sink flush failed", exc_info=True)

    def close(self) -> None:
        for s in self._sinks:
            try:
                s.close()
            except Exception:  # noqa: BLE001
                logger.debug("sink close failed", exc_info=True)


def _factory_wants_tag(factory: Callable) -> bool:
    """Whether a sink factory accepts the framework tag as its first argument."""
    try:
        sig = inspect.signature(factory)
        return len(sig.parameters) >= 1
    except (ValueError, TypeError):
        return False


def _install_discovered_sinks(framework_tag: str) -> None:
    """Discover, instantiate and wire third-party trace sinks (best-effort)."""
    sinks: List[Any] = []
    for factory in discover_observability_sinks():
        try:
            sink = factory(framework_tag) if _factory_wants_tag(factory) else factory()
            if sink is not None:
                sinks.append(sink)
        except Exception:  # noqa: BLE001 -- a broken plugin must not break a run
            logger.debug("observability sink factory %r failed", factory, exc_info=True)

    if not sinks:
        return

    try:
        from praisonaiagents.trace.protocol import TraceEmitter, set_default_emitter
    except Exception:  # noqa: BLE001 -- core trace API unavailable; skip silently
        logger.debug("trace protocol unavailable; skipping sink wiring", exc_info=True)
        return

    _installed_sinks.extend(sinks)
    set_default_emitter(TraceEmitter(sink=_FanoutSink(sinks), enabled=True))


def init_observability(framework_tag: str, *, tags: Optional[List[str]] = None) -> None:
    """
    Initialize observability providers (AgentOps, etc.) if available.
    
    Args:
        framework_tag: Primary framework tag (e.g., "crewai", "autogen_v4")
        tags: Additional tags to include
    """
    # Try to initialize AgentOps if available
    _init_agentops(framework_tag, tags or [])

    # Honour the documented "praisonai.observability_sinks" entry-point group so
    # third-party TraceSinkProtocol implementations are actually loaded.
    _install_discovered_sinks(framework_tag)

    # Future: Add other observability providers here
    # _init_langfuse(framework_tag, tags)
    # _init_wandb(framework_tag, tags)


def finalize_observability(_framework_tag: str, *, status: str = "Success") -> None:
    """
    Close observability providers (AgentOps, etc.) if available.

    Symmetric with init_observability — always call at run end so dashboards
    don't show sessions stuck "in progress". Errors here are swallowed because
    telemetry must never crash a user run.
    
    Args:
        _framework_tag: Framework name for context (reserved for future observability providers)
        status: Session status ("Success", "Failure", etc.)
    """
    _end_agentops(status)

    # Flush + close any entry-point sinks installed for this run.
    for sink in _installed_sinks:
        try:
            sink.flush()
            sink.close()
        except Exception:  # noqa: BLE001 -- telemetry must not crash the caller
            logger.debug("sink teardown failed", exc_info=True)
    _installed_sinks.clear()

    # Future: Add other observability providers here
    # _end_langfuse(status)
    # _end_wandb(status)


def _init_agentops(framework_tag: str, additional_tags: List[str]) -> None:
    """Initialize AgentOps if available."""
    try:
        import agentops
        agentops_api_key = os.getenv("AGENTOPS_API_KEY")
        if agentops_api_key:
            all_tags = [framework_tag] + additional_tags
            agentops.init(agentops_api_key, default_tags=all_tags)
            logger.debug("Initialized AgentOps with tags: %s", all_tags)
    except ImportError:
        logger.debug("AgentOps not available, skipping initialization")
    except Exception as e:
        logger.warning("Failed to initialize AgentOps: %s", e)


def _end_agentops(status: str) -> None:
    """End AgentOps session if available."""
    try:
        import agentops
    except ImportError:
        return
    try:
        agentops.end_session(status)
        logger.debug("Ended AgentOps session: %s", status)
    except Exception as e:  # noqa: BLE001 -- telemetry must not crash the caller
        logger.warning("agentops.end_session failed: %s", e)


def is_agentops_available() -> bool:
    """Lazy check — does not import agentops at module load time."""
    from .._framework_availability import is_available
    return is_available("agentops")


@contextmanager
def observability_session(
    framework_tag: str, *, tags: Optional[List[str]] = None
) -> Iterator[None]:
    """Context manager that brackets a run with init/finalize observability.

    Guarantees ``finalize_observability`` always runs — on success *and* on
    any failure — with the correct status derived from whether an exception is
    propagating. This prevents AgentOps/other sessions from being orphaned in
    an "in progress" state on error, KeyboardInterrupt, or rate-limit paths.

    Usage::

        with observability_session(self.name, tags=tags):
            ... run agents ...
    """
    init_observability(framework_tag, tags=tags)
    try:
        yield
    finally:
        # status reflects whether an exception is currently propagating
        status = "Failure" if sys.exc_info()[0] is not None else "Success"
        try:
            finalize_observability(framework_tag, status=status)
        except Exception:  # noqa: BLE001 -- telemetry must not crash the caller
            logger.exception("finalize_observability failed")


# ---------------------------------------------------------------------------
# Pluggable trace-sink discovery (Protocol-driven extensibility).
#
# Third-party sinks implementing the core SDK's TraceSinkProtocol can register
# a zero-arg (or framework-tag-aware) factory under the entry-point group
# "praisonai.observability_sinks". Discovery is lazy and best-effort so a
# broken plugin never breaks a user run.
# ---------------------------------------------------------------------------

def discover_observability_sinks() -> List[Callable]:
    """Return third-party observability sink factories from entry points.

    Each entry point is expected to load to a callable factory. Failures are
    swallowed (logged at debug) so observability discovery never crashes a run.
    """
    factories: List[Callable] = []
    try:
        from importlib.metadata import entry_points

        try:
            eps = entry_points(group="praisonai.observability_sinks")
        except TypeError:
            # Python < 3.10 returns a dict-like mapping from entry_points().
            eps = entry_points().get("praisonai.observability_sinks", [])

        for ep in eps:
            try:
                factory = ep.load()
                if callable(factory):
                    factories.append(factory)
                else:
                    logger.debug("observability sink %r is not callable; skipping", ep)
            except Exception:  # noqa: BLE001
                logger.debug("failed to load observability sink %r", ep, exc_info=True)
    except Exception:  # noqa: BLE001
        logger.debug("no third-party observability sinks discovered", exc_info=True)
    return factories