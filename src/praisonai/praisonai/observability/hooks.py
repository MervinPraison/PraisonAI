"""
Observability hooks for PraisonAI.

Centralizes observability initialization (AgentOps, etc.) so it can be 
used consistently across all entry points without duplicating logic.
"""

import os
import sys
import inspect
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ObservabilityRun:
    """Per-run observability handle.

    Holds only the sinks installed for a single run plus the trace emitter that
    was active before this run took over. Teardown restores that emitter and
    closes only this run's sinks, so concurrent runs never close each other's
    sinks or leave the global emitter stuck in a Fanout state.
    """

    sinks: List[Any] = field(default_factory=list)
    prev_emitter: Any = None
    own_emitter: Any = None
    _emitter_swapped: bool = False
    agentops_session: Any = None
    # Which AgentOps teardown this run owns:
    #   "session" -> end THIS run's ``agentops_session`` handle only;
    #   "global"  -> legacy singleton path, end the package-global session;
    #   None      -> AgentOps was never initialised for this run (nothing to end).
    # Prevents a run whose per-session ``start_session`` failed from falling back
    # to the global ``end_session`` and cross-finalizing an unrelated live run.
    _agentops_mode: Optional[str] = None


# Thread-local LIFO stack of the runs started on the current thread. ``init``
# and ``finalize`` are called separately (init in the generator, finalize in
# each adapter) but on the same thread per run, so a per-thread stack lets
# finalize tear down exactly the run it belongs to — even when the void-
# returning legacy signatures are used. This replaces the previous single
# process-wide ``_installed_sinks`` list that made concurrent runs trample
# each other.
_run_stack = threading.local()

# Process-wide guard for the global trace emitter swap/restore. The emitter set
# via ``set_default_emitter`` is a single process-global slot, so concurrent
# runs on different threads form a logical chain (each run's ``prev_emitter``
# points at whatever was active when it swapped in). This lock serialises the
# swap and the restore so the chain can be repaired safely regardless of the
# order in which overlapping runs finalize (non-LIFO included).
_emitter_lock = threading.Lock()

# Ordered list of runs that currently hold an emitter swap, oldest first. Used
# only to repair the ``prev_emitter`` chain when a middle run finalizes out of
# order. Guarded by ``_emitter_lock``.
_swapped_runs: List["ObservabilityRun"] = []

# Serialises AgentOps init/end so overlapping runs on different threads don't
# race on the package-global session. Runs that use the newer per-session API
# get a run-scoped handle on ``ObservabilityRun.agentops_session``; the legacy
# singleton path is at least protected from concurrent init/end interleaving.
_agentops_lock = threading.Lock()


def _get_run_stack() -> List[ObservabilityRun]:
    stack = getattr(_run_stack, "runs", None)
    if stack is None:
        stack = []
        _run_stack.runs = stack
    return stack


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
    """Whether a sink factory accepts the framework tag as its first argument.

    Only positional-capable parameters count. A ``**kwargs``-only factory would
    otherwise be mis-detected and called as ``factory(framework_tag)``, raising
    ``TypeError`` and silently dropping the sink.
    """
    try:
        sig = inspect.signature(factory)
        positional_kinds = {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        }
        return any(p.kind in positional_kinds for p in sig.parameters.values())
    except (ValueError, TypeError):
        return False


def _instantiate_discovered_sinks(framework_tag: str) -> List[Any]:
    """Discover and instantiate third-party trace sinks (best-effort).

    Returns the freshly instantiated sinks without touching any process-wide
    state, so each run owns its own list.
    """
    sinks: List[Any] = []
    for factory in discover_observability_sinks():
        try:
            sink = factory(framework_tag) if _factory_wants_tag(factory) else factory()
            if sink is not None:
                sinks.append(sink)
        except Exception:  # noqa: BLE001 -- a broken plugin must not break a run
            logger.debug("observability sink factory %r failed", factory, exc_info=True)
    return sinks


def init_observability(
    framework_tag: str, *, tags: Optional[List[str]] = None
) -> ObservabilityRun:
    """
    Initialize observability providers (AgentOps, etc.) if available.

    Returns a per-run :class:`ObservabilityRun` handle. The handle is also
    pushed onto a thread-local stack so a decoupled ``finalize_observability``
    call (which only receives the framework tag) still tears down exactly this
    run. Callers may keep the handle and pass it back explicitly for the
    sanctioned, fully-scoped API.

    Args:
        framework_tag: Primary framework tag (e.g., "crewai", "autogen_v4")
        tags: Additional tags to include
    """
    # Honour the documented "praisonai.observability_sinks" entry-point group so
    # third-party TraceSinkProtocol implementations are actually loaded — but
    # scope the sinks and the emitter swap to THIS run only.
    sinks = _instantiate_discovered_sinks(framework_tag)
    run = ObservabilityRun(sinks=sinks)

    # Start a per-run AgentOps session so overlapping runs don't stomp each
    # other's tags/context or cross-finalize each other's status. The handle is
    # stored on ``run`` and torn down in ``finalize_observability``.
    _init_agentops(framework_tag, tags or [], run)

    if sinks:
        try:
            from praisonaiagents.trace.protocol import (
                TraceEmitter,
                get_default_emitter,
                set_default_emitter,
            )
        except Exception:  # noqa: BLE001 -- core trace API unavailable; skip silently
            logger.debug("trace protocol unavailable; skipping sink wiring", exc_info=True)
        else:
            emitter = TraceEmitter(sink=_FanoutSink(sinks), enabled=True)
            # Serialise capture + swap + registration so an overlapping run on
            # another thread can never observe a half-updated chain.
            with _emitter_lock:
                try:
                    run.prev_emitter = get_default_emitter()
                except Exception:  # noqa: BLE001 -- older cores may lack the getter
                    run.prev_emitter = None
                run.own_emitter = emitter
                set_default_emitter(emitter)
                run._emitter_swapped = True
                _swapped_runs.append(run)

    _get_run_stack().append(run)

    # Future: Add other observability providers here
    # _init_langfuse(framework_tag, tags)
    # _init_wandb(framework_tag, tags)
    return run


def finalize_observability(
    framework_tag: str,
    *,
    status: str = "Success",
    run: Optional[ObservabilityRun] = None,
) -> None:
    """
    Close observability providers (AgentOps, etc.) if available.

    Symmetric with init_observability — always call at run end so dashboards
    don't show sessions stuck "in progress". Errors here are swallowed because
    telemetry must never crash a user run.

    Args:
        framework_tag: Framework name for context (reserved for future observability providers)
        status: Session status ("Success", "Failure", etc.)
        run: Explicit per-run handle to tear down. When omitted, the most recent
            run started on this thread is popped and torn down, preserving the
            legacy void-returning call pattern while staying concurrency-safe.
    """
    if run is None:
        stack = _get_run_stack()
        run = stack.pop() if stack else None
    else:
        # Explicit handle: remove it from the thread-local stack if present so a
        # later void-call doesn't tear it down twice.
        stack = _get_run_stack()
        try:
            stack.remove(run)
        except ValueError:
            pass

    # End AgentOps against THIS run's session (resolved above) so overlapping
    # runs never finalize each other's session. Done before the sink teardown
    # so a legacy void-call with no run still ends the singleton once.
    _end_agentops(status, run)

    if run is None:
        return

    # Flush + close only THIS run's sinks. Each call is guarded independently so
    # a failing flush() still lets close() release the sink's resources.
    for sink in run.sinks:
        try:
            sink.flush()
        except Exception:  # noqa: BLE001 -- telemetry must not crash the caller
            logger.debug("sink flush failed", exc_info=True)
        try:
            sink.close()
        except Exception:  # noqa: BLE001
            logger.debug("sink close failed", exc_info=True)

    # Restore the emitter chain. Because the global emitter is a single
    # process-wide slot shared by every thread, overlapping runs form a chain
    # (each run captured whatever was active when it swapped in). Repair it so:
    #   * if THIS run is still the active (top) emitter, restore its prev; else
    #   * a newer run swapped in on top — just splice this run out of the chain
    #     by pointing whichever run captured us at our own prev, and leave the
    #     live global emitter untouched.
    # This keeps traces flowing to the correct sink even when a middle run
    # finalizes out of LIFO order or two runs overlap across threads.
    if run._emitter_swapped:
        try:
            from praisonaiagents.trace.protocol import (
                get_default_emitter,
                set_default_emitter,
            )
        except Exception:  # noqa: BLE001
            logger.debug("failed to import trace emitter API for restore", exc_info=True)
        else:
            with _emitter_lock:
                try:
                    current = get_default_emitter()
                except Exception:  # noqa: BLE001
                    current = None
                if current is run.own_emitter:
                    # This run is the live top: hand control back to its prev.
                    set_default_emitter(run.prev_emitter)
                else:
                    # A newer run is on top. Re-parent it onto our prev so that
                    # when it later restores, it skips our (now closed) emitter.
                    for other in _swapped_runs:
                        if other is not run and other.prev_emitter is run.own_emitter:
                            other.prev_emitter = run.prev_emitter
                try:
                    _swapped_runs.remove(run)
                except ValueError:
                    pass

    run.sinks = []
    run.own_emitter = None
    run._emitter_swapped = False

    # Future: Add other observability providers here
    # _end_langfuse(status)
    # _end_wandb(status)


def _init_agentops(
    framework_tag: str,
    additional_tags: List[str],
    run: Optional[ObservabilityRun] = None,
) -> None:
    """Initialize AgentOps if available, scoped to ``run`` when possible.

    AgentOps' ``init`` mutates package-global session state, so two overlapping
    runs would otherwise share (and cross-finalize) one session. When the
    installed SDK exposes the newer per-session ``start_session`` API we start a
    dedicated session and stash its handle on ``run`` so ``_end_agentops`` can
    end exactly this run's session. Otherwise we fall back to the legacy
    singleton under ``_agentops_lock`` so at least the single-session cases don't
    interleave.
    """
    try:
        import agentops
    except ImportError:
        logger.debug("AgentOps not available, skipping initialization")
        return
    try:
        agentops_api_key = os.getenv("AGENTOPS_API_KEY")
        if not agentops_api_key:
            return
        all_tags = [framework_tag] + additional_tags
        with _agentops_lock:
            start_session = getattr(agentops, "start_session", None)
            if callable(start_session):
                # Per-session mode: this run owns exactly the handle returned
                # here. Record the mode BEFORE the call so that even if
                # ``start_session`` returns None/an unusable handle, teardown
                # stays scoped to this run and never falls back to the global
                # ``end_session`` (which would truncate a concurrent run).
                if run is not None:
                    run._agentops_mode = "session"
                    run.agentops_session = start_session(tags=all_tags)
                else:
                    start_session(tags=all_tags)
            else:
                agentops.init(agentops_api_key, default_tags=all_tags)
                if run is not None:
                    run._agentops_mode = "global"
        logger.debug("Initialized AgentOps with tags: %s", all_tags)
    except Exception as e:
        logger.warning("Failed to initialize AgentOps: %s", e)


def _end_agentops(status: str, run: Optional[ObservabilityRun] = None) -> None:
    """End the AgentOps session for ``run`` if available.

    Teardown is scoped to what ``_init_agentops`` actually started for this run:

    * ``_agentops_mode == "session"`` — end THIS run's own handle. If the handle
      is missing/unusable (``start_session`` returned None or raised) we end
      NOTHING rather than falling back to the package-global ``end_session``,
      because that global call would truncate a *different* run's live session.
    * ``_agentops_mode == "global"`` — legacy singleton path: end the
      package-global session.
    * ``run is None`` (legacy void-call with no handle) — preserve the historical
      contract and end the package-global session once.
    * ``_agentops_mode is None`` on a real run — AgentOps was never initialised
      for this run; do nothing.
    """
    try:
        import agentops
    except ImportError:
        return

    if run is None:
        mode = "global"
    else:
        mode = run._agentops_mode
    if mode is None:
        return

    session = getattr(run, "agentops_session", None) if run is not None else None
    try:
        with _agentops_lock:
            if mode == "session":
                if session is not None and hasattr(session, "end_session"):
                    session.end_session(status)
                else:
                    # Per-session start failed; do NOT cross-finalize the
                    # package-global session that may belong to another run.
                    logger.debug(
                        "AgentOps per-session handle unavailable; skipping "
                        "global end_session to avoid cross-finalizing another run"
                    )
                    return
            else:
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
    run = init_observability(framework_tag, tags=tags)
    try:
        yield
    finally:
        # status reflects whether an exception is currently propagating
        status = "Failure" if sys.exc_info()[0] is not None else "Success"
        try:
            # Pass the explicit handle so this run's sinks/emitter are torn down
            # regardless of any nested runs pushed onto the thread-local stack.
            finalize_observability(framework_tag, status=status, run=run)
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