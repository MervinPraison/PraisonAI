"""Give a single Agent's tools a sandbox, without touching its thinking.

``AgentFlow``/``AgentTeam`` already share one sandbox across a run and tear it
down when the run ends. A lone ``Agent(tools_run_on=...)`` has no "run" to hang
that lifetime on -- it is just an object someone calls ``chat()`` on, possibly
many times -- so the sandbox is created on first use and kept for the agent's
lifetime. That is deliberate: a file written in turn 1 is still there in turn 2,
which is what anyone who asked for a working directory expects.

Attachment is idempotent and happens at the top of ``chat``/``achat``/
``_start_stream``. Doing it once, rather than wrapping each call in a context
manager, sidesteps two real hazards in this codebase:

* ``_start_stream`` is a **generator**; a context manager around the call would
  exit before the caller consumed a single token, tearing down the sandbox while
  the model was still using it.
* ``_start_stream`` falls back to ``self.chat``, so a wrapper would **re-enter**
  itself and provision a second sandbox.
"""

from __future__ import annotations

import atexit
import logging
import threading
import weakref
from typing import Any

logger = logging.getLogger(__name__)

# Agents with a live sandbox, so the interpreter shutdown hook can close them.
# Weak so holding an agent here never keeps it alive.
_LIVE: "weakref.WeakSet" = weakref.WeakSet()
_LIVE_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


def _close_all() -> None:
    for agent in list(_LIVE):
        try:
            close_tools_sandbox(agent)
        except Exception:  # pragma: no cover - shutdown must stay quiet
            pass


def ensure_tools_placed(agent: Any) -> None:
    """Attach the sandbox tools to ``agent`` if it asked for them. Idempotent.

    Called at the top of every entry point, so it must be cheap when there is
    nothing to do -- which is the overwhelmingly common case.
    """
    place = getattr(agent, "tools_run_on", None)
    if place is None or getattr(agent, "_tools_sandbox", None) is not None:
        return

    global _ATEXIT_REGISTERED

    from ..managed.shared_compute import SharedCompute

    with _LIVE_LOCK:
        # Re-check under the lock: two threads calling chat() at once must not
        # each provision a sandbox and leak one.
        if getattr(agent, "_tools_sandbox", None) is not None:
            return
        shared = SharedCompute(place)
        # override_declared: this sandbox exists *because* the agent named a
        # place, so the skip-if-declared rule must not skip the agent itself.
        shared.attach([agent], override_declared=True)
        agent._tools_sandbox = shared
        _LIVE.add(agent)
        if not _ATEXIT_REGISTERED:
            atexit.register(_close_all)
            _ATEXIT_REGISTERED = True

    logger.info("[tools_placement] %r tools now run on %s", getattr(agent, "name", agent), place)


def close_tools_sandbox(agent: Any) -> None:
    """Tear down the agent's sandbox and put its original tools back."""
    shared = getattr(agent, "_tools_sandbox", None)
    if shared is None:
        return
    agent._tools_sandbox = None
    with _LIVE_LOCK:
        _LIVE.discard(agent)
    shared.shutdown()
