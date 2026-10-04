"""Shared lazy run-lock helper for core orchestration modules.

AgentTeam (``agents/agents.py``) and Workflow/AgentFlow (``workflows/workflows.py``)
both lazily mint a per-instance re-entrancy lock the first time a run begins.
Creation is serialized through a single module-level guard (double-checked
locking) so two threads racing into the first ``start()``/``astart()``/``run()``
observe the *same* lock object rather than each minting and acquiring its own.
"""
import threading

# Guards lazy creation of each instance's per-instance ``_run_lock`` so two
# threads that first reach start()/astart()/run() concurrently observe the same
# lock object (double-checked locking) rather than each minting its own.
_RUN_LOCK_INIT_GUARD = threading.Lock()


def ensure_run_lock(obj):
    """Lazily mint ``obj._run_lock`` under a shared module guard.

    ``getattr(obj, "_run_lock", None)`` works for both the dataclass-field case
    (Workflow) and the plain-attribute case (AgentTeam), so the behaviour is
    identical to the per-module implementations it replaces.
    """
    lock = getattr(obj, "_run_lock", None)
    if lock is None:
        with _RUN_LOCK_INIT_GUARD:
            lock = getattr(obj, "_run_lock", None)
            if lock is None:
                lock = threading.Lock()
                obj._run_lock = lock
    return lock
