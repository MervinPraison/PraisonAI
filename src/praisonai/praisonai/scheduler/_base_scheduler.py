"""
Shared, lock-agnostic scheduler logic for both sync and async variants.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _extract_usage(result: Any) -> Tuple[int, int, str]:
    """Pull (input_tokens, output_tokens, model) off whatever the agent returned.

    Looks for the common LiteLLM / SDK response shapes. Falls back to
    (0, 0, '') so a response with no usage metadata contributes $0 — not a
    fake constant. The budget brake should err on the side of running forever
    rather than tripping prematurely on missing metadata.
    """
    usage = getattr(result, "usage", None)
    if usage is None and isinstance(result, dict):
        usage = result.get("usage")

    model = getattr(result, "model", None)
    if model is None and isinstance(result, dict):
        model = result.get("model")
    model = model or ""

    if usage is None:
        return 0, 0, model

    if isinstance(usage, dict):
        in_tok = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        out_tok = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        return int(in_tok), int(out_tok), model

    in_tok = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0
    out_tok = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0
    return int(in_tok), int(out_tok), model


def _compute_run_cost(result: Any) -> Tuple[float, int, int, str]:
    """Compute the real cost of a single run from its usage metadata.

    Returns (cost, input_tokens, output_tokens, model). Returns a cost of 0.0
    when no token usage is available rather than a misleading constant.
    """
    in_tok, out_tok, model = _extract_usage(result)
    if not (in_tok or out_tok):
        return 0.0, in_tok, out_tok, model
    from praisonai.cli.features.cost_tracker import get_pricing
    cost = get_pricing(model).calculate_cost(in_tok, out_tok)
    return cost, in_tok, out_tok, model


class _BaseAgentScheduler:
    """Shared, lock-agnostic scheduler logic — used by both sync and async variants."""

    is_running: bool
    max_cost: Optional[float]
    _execution_count: int
    _success_count: int
    _failure_count: int
    _total_cost: float
    _start_time: Optional[datetime]

    def _build_stats(
        self,
        *,
        execs: int,
        success: int,
        failed: int,
        total_cost: float,
    ) -> Dict[str, Any]:
        """Build stats dictionary for both sync and async schedulers."""
        runtime = (
            (datetime.now() - self._start_time).total_seconds()
            if self._start_time else 0
        )
        return {
            "is_running": self.is_running,
            "total_executions": execs,
            "successful_executions": success,
            "failed_executions": failed,
            "success_rate": (success / execs * 100) if execs > 0 else 0,
            "total_cost_usd": round(total_cost, 4),
            "remaining_budget": (
                round(self.max_cost - total_cost, 4) if self.max_cost is not None else None
            ),
            "runtime_seconds": runtime,
            "cost_per_execution": (
                round(total_cost / execs, 4) if execs > 0 else 0
            ),
        }

    def _update_state_if_daemon(self) -> None:
        """Update ~/.praisonai/schedulers/*.json for the current PID, if present.

        Safe for both sync and async callers — it's plain blocking file I/O that
        runs once per execution and is wrapped in try/except.
        """
        try:
            state_dir = os.path.expanduser("~/.praisonai/schedulers")
            if not os.path.exists(state_dir):
                return
            current_pid = os.getpid()
            for fname in os.listdir(state_dir):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(state_dir, fname)
                try:
                    with open(path, "r") as f:
                        state = json.load(f)
                    if state.get("pid") == current_pid:
                        state["executions"] = self._execution_count
                        state["cost"] = round(self._total_cost, 4)
                        with open(path, "w") as f:
                            json.dump(state, f, indent=2)
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Failed to update state: %s", e)