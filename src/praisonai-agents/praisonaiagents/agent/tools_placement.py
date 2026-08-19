"""Give a single Agent's tools a sandbox, without touching its thinking.

``AgentFlow``/``AgentTeam`` already share one sandbox across a run and tear it
down when the run ends. A lone ``Agent(tools_run_on=...)`` has no "run" to hang
that lifetime on -- it is just an object someone calls ``chat()`` on, possibly
many times -- so the sandbox is created on first use and lives as long as the
agent does. That is deliberate: a file written in turn 1 is still there in turn
2, which is what anyone who asked for a working directory expects.

Attachment is idempotent and happens at the top of ``chat``/``achat``/
``_start_stream``, and in ``AgentTeam`` before the task's tool list is
snapshotted. Doing it once, rather than wrapping each call in a context
manager, sidesteps two real hazards in this codebase:

* ``_start_stream`` is a **generator**; a context manager around the call would
  exit before the caller consumed a single token, tearing down the sandbox while
  the model was still using it.
* ``_start_stream`` falls back to ``self.chat``, so a wrapper would **re-enter**
  itself and provision a second sandbox.

Lifetime is tied to the agent by ``weakref.finalize`` rather than a process-exit
hook over a weak set. The weak set leaked: an agent and its ``SharedCompute``
reference each other, so a dropped agent was reclaimed by the cycle collector,
vanished from the set, and its sandbox was never shut down. Gateways clone an
agent **per request**, so that was one orphaned container per request.
"""

from __future__ import annotations

import logging
import threading
import weakref
from typing import Any

logger = logging.getLogger(__name__)

# One lock per agent, so two unrelated agents never wait on each other and no
# lock is ever held while another agent's provider is being imported. Held only
# by ensure_tools_placed/close_tools_sandbox for that one agent.
_AGENT_LOCKS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_LOCKS_GUARD = threading.Lock()


def _lock_for(agent: Any) -> threading.Lock:
    """The placement lock for ``agent``, created on demand.

    ``_LOCKS_GUARD`` covers only this dictionary lookup -- microseconds -- never
    provider construction or attachment. An earlier version held one global lock
    across ``SharedCompute(...)``, which imports the provider SDK: unrelated
    agents serialised behind each other, and a slow import could stall
    interpreter exit.
    """
    with _LOCKS_GUARD:
        lock = _AGENT_LOCKS.get(agent)
        if lock is None:
            lock = threading.Lock()
            try:
                _AGENT_LOCKS[agent] = lock
            except TypeError:  # pragma: no cover - unhashable/non-weakrefable
                pass
        return lock


def _shutdown_orphan(shared: Any, name: str) -> None:
    """Tear down a sandbox whose agent is gone.

    Registered with ``weakref.finalize``, so it runs when the agent is collected
    *and* at interpreter exit. It must not close over the agent -- that would
    keep it alive and defeat the whole point.
    """
    try:
        shared.shutdown()
        logger.debug("[tools_placement] released the sandbox belonging to %s", name)
    except Exception:  # pragma: no cover - teardown must stay quiet
        logger.debug("[tools_placement] could not release the sandbox for %s", name)


def ensure_tools_placed(agent: Any) -> None:
    """Attach the sandbox tools to ``agent`` if it asked for them. Idempotent.

    Called at the top of every entry point, so it must be cheap when there is
    nothing to do -- which is the overwhelmingly common case.
    """
    place = getattr(agent, "tools_run_on", None)
    if place is None or getattr(agent, "_tools_sandbox", None) is not None:
        return

    from ..managed.shared_compute import SharedCompute

    with _lock_for(agent):
        # Re-check under the lock: two threads calling chat() at once must not
        # each provision a sandbox and leak one.
        if getattr(agent, "_tools_sandbox", None) is not None:
            return

        shared = SharedCompute(place)
        # override_declared: this sandbox exists *because* the agent named a
        # place, so the skip-if-declared rule must not skip the agent itself.
        shared.attach([agent], override_declared=True)
        agent._tools_sandbox = shared
        agent._tools_sandbox_finalizer = weakref.finalize(
            agent, _shutdown_orphan, shared, str(getattr(agent, "name", agent))
        )

    logger.info("[tools_placement] %r tools now run on %s", getattr(agent, "name", agent), place)


def close_tools_sandbox(agent: Any) -> None:
    """Tear down the agent's sandbox and put its original tools back."""
    with _lock_for(agent):
        # Everything happens under the lock. Clearing the marker first and
        # shutting down afterwards left a window where a concurrent chat()
        # re-attached and the in-flight shutdown then restored over it, leaving
        # the agent marked as sandboxed while holding no sandbox tools -- a
        # state ensure_tools_placed() could never repair, because its idempotent
        # early return sees the marker and does nothing.
        shared = getattr(agent, "_tools_sandbox", None)
        if shared is None:
            return
        finalizer = getattr(agent, "_tools_sandbox_finalizer", None)
        if finalizer is not None:
            finalizer.detach()          # we are shutting down explicitly
            agent._tools_sandbox_finalizer = None
        shared.shutdown()
        agent._tools_sandbox = None
