"""Zero-cost hook the YAML runner calls on the team/flow it builds.

Kept apart from :mod:`praisonai.replay.rerun` (which imports the workflow
engine) so a normal run pays one ContextVar lookup and nothing else.
"""

import contextvars
from typing import Any

#: (RerunPlan, on_seeded) while ``praisonai.replay.rerun.rerun_scope`` is active.
ACTIVE_PLAN: contextvars.ContextVar = contextvars.ContextVar("praisonai_replay_rerun_plan", default=None)


def apply_rerun_seed(obj: Any) -> None:
    """Seed ``obj`` from the active re-run plan, if any (no-op otherwise)."""
    active = ACTIVE_PLAN.get()
    if active is None:
        return
    from .rerun import _seed_built

    plan, on_seeded = active
    _seed_built(obj, plan, on_seeded)
