"""``praisonai steward`` (S-4c): watch loop with attempt caps, branch guard, and ``--once``."""

import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from praisonai_code.ship import is_ship_disabled
from praisonai_code.ship.flow import ShipRefused
from praisonai_code.ship.steward import next_action, read_pr_state
from praisonai_code.ship.steward_turn import run_steward_turn


@dataclass
class StewardSummary:
    reason: str
    cycles: int = 0
    turns: int = 0
    attempts: Dict[str, int] = field(default_factory=dict)


def _current_branch(run: Callable) -> Optional[str]:
    proc = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def watch_pr(
    pr: Optional[str] = None, *, interval: float = 60.0, max_days: float = 7.0,
    max_attempts: int = 3, once: bool = False, llm: Optional[str] = None, agent=None,
    run: Callable = subprocess.run, sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic, on_event: Optional[Callable[[str], None]] = None,
) -> StewardSummary:
    """Poll a PR until merged/closed, branch switch, Ctrl+C, ``once``, or ``max_days``."""
    if reason := is_ship_disabled():
        raise ShipRefused(reason)
    if interval <= 0 or max_days <= 0 or max_attempts < 1:
        raise ValueError("interval and max_days must be > 0, and max_attempts >= 1")
    pr = pr.lstrip("#") if pr and pr.startswith("#") else pr
    emit, start_branch = on_event or (lambda _msg: None), (_current_branch(run) if pr is None else None)
    attempts, cycles, turns, deadline = {}, 0, 0, monotonic() + max_days * 86400.0
    while monotonic() < deadline:
        if start_branch is not None and (cur := _current_branch(run)) and cur != start_branch:
            emit(f"steward: branch switched ({start_branch} -> {cur}); stopping")
            return StewardSummary("branch switched", cycles, turns, attempts)
        cycles += 1
        state = read_pr_state(pr, run=run)
        for key, count in getattr(state, "prior_attempts", {}).items():
            if count > attempts.get(key, 0):
                attempts[key] = count
        action = next_action(state, attempts, max_attempts=max_attempts)
        if action.kind == "stop":
            emit(f"steward: {action.detail}")
            return StewardSummary(action.detail, cycles, turns, attempts)
        if action.kind != "wait":
            attempts[action.key] = attempts.get(action.key, 0) + 1
            res = run_steward_turn(state, action, agent=agent, llm=llm, run=run, record_attempt=once)
            turns += 1
            emit(f"steward: {action.kind} ({action.key}) -> {res.pushed_sha or 'no push'}")
        else:
            emit(f"steward: wait ({action.detail})")
        if once:
            return StewardSummary("once", cycles, turns, attempts)
        try:
            sleep(interval)
        except KeyboardInterrupt:
            emit("steward: interrupted")
            return StewardSummary("interrupted", cycles, turns, attempts)
    emit("steward: max_days reached")
    return StewardSummary("max_days reached", cycles, turns, attempts)
