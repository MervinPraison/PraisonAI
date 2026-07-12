"""
Shared, lock-agnostic scheduler logic for both sync and async variants.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Type

logger = logging.getLogger(__name__)


def _to_non_negative_int(value: Any) -> int:
    """Coerce a token count to a non-negative int, defaulting to 0 on bad input.

    Guards against negative or malformed usage values that could otherwise
    produce a negative run cost (a budget-brake bypass) or raise during cost
    calculation.
    """
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


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
        return _to_non_negative_int(in_tok), _to_non_negative_int(out_tok), model

    in_tok = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0
    out_tok = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0
    return _to_non_negative_int(in_tok), _to_non_negative_int(out_tok), model


def _compute_run_cost(result: Any) -> Tuple[float, int, int, str]:
    """Compute the real cost of a single run from its usage metadata.

    Returns (cost, input_tokens, output_tokens, model). Returns a cost of 0.0
    when no token usage is available rather than a misleading constant.
    """
    in_tok, out_tok, model = _extract_usage(result)
    if not (in_tok or out_tok):
        return 0.0, in_tok, out_tok, model
    from praisonai.cli.features.cost_tracker import get_pricing
    try:
        cost = get_pricing(model or "default").calculate_cost(in_tok, out_tok)
    except Exception:
        logger.debug(
            "Cost computation failed for model=%r; treating run cost as 0.0", model
        )
        return 0.0, in_tok, out_tok, model
    return cost, in_tok, out_tok, model


def build_from_yaml(
    scheduler_cls: Type,
    yaml_path: str = "agents.yaml",
    interval_override: Optional[str] = None,
    max_retries_override: Optional[int] = None,
    timeout_override: Optional[int] = None,
    max_cost_override: Optional[float] = None,
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
) -> "_BaseAgentScheduler":
    """Construct a scheduler from an agents.yaml file.

    Shared by both the sync ``AgentScheduler`` and async ``AsyncAgentScheduler``;
    the only difference between the two is ``scheduler_cls``. The agent created
    here is framework-agnostic, so no executor-agent wrapper parameter is needed.
    """
    from .yaml_loader import load_agent_yaml_with_schedule, create_agent_from_config

    # Load configuration from YAML
    agent_config, schedule_config = load_agent_yaml_with_schedule(yaml_path)

    # Validate task before any (potentially expensive) agent construction
    task = agent_config.get('task', '')
    if not task:
        raise ValueError("No task specified in YAML file")

    # Create agent from config
    agent = create_agent_from_config(agent_config)

    # Apply overrides to schedule config
    if interval_override:
        schedule_config['interval'] = interval_override
    if max_retries_override is not None:
        schedule_config['max_retries'] = max_retries_override
    if timeout_override is not None:
        schedule_config['timeout'] = timeout_override
    if max_cost_override is not None:
        schedule_config['max_cost'] = max_cost_override

    # Create scheduler instance with timeout and cost limits
    scheduler = scheduler_cls(
        agent=agent,
        task=task,
        config=agent_config,
        timeout=schedule_config.get('timeout'),
        max_cost=schedule_config.get('max_cost'),
        on_success=on_success,
        on_failure=on_failure,
        deliver=schedule_config.get('deliver', ''),
    )

    # Store schedule config for later use
    scheduler._yaml_schedule_config = schedule_config

    return scheduler


def build_from_recipe(
    scheduler_cls: Type,
    agent_cls: Type,
    recipe_name: str,
    *,
    input_data: Any = None,
    config: Optional[Dict[str, Any]] = None,
    interval_override: Optional[str] = None,
    max_retries_override: Optional[int] = None,
    timeout_override: Optional[int] = None,
    max_cost_override: Optional[float] = None,
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
) -> "_BaseAgentScheduler":
    """Construct a scheduler from a recipe name.

    Shared by both sync and async schedulers. ``scheduler_cls`` selects the
    scheduler type and ``agent_cls`` selects the executor-agent wrapper
    (``RecipeExecutorAgent`` vs ``AsyncRecipeExecutorAgent``) — the only two
    pieces that differed between the previously-duplicated copies.
    """
    from praisonai.recipe.bridge import resolve, get_recipe_task_description

    # Only pass timeout_sec through to recipe execution when the caller
    # explicitly overrides it. Otherwise leave options empty so the recipe's
    # own runtime_config timeout (via resolved.get_timeout_sec()) is honoured
    # instead of being clobbered by the scheduler default.
    resolve_options: Dict[str, Any] = {}
    if timeout_override is not None:
        resolve_options['timeout_sec'] = timeout_override

    # Resolve the recipe
    resolved = resolve(
        recipe_name,
        input_data=input_data,
        config=config or {},
        options=resolve_options,
    )

    # Get runtime config defaults from recipe
    interval = interval_override or "hourly"
    max_retries = max_retries_override if max_retries_override is not None else 3
    timeout = timeout_override if timeout_override is not None else 300
    max_cost = max_cost_override if max_cost_override is not None else 1.00

    runtime = resolved.runtime_config
    if runtime and hasattr(runtime, 'schedule'):
        sched_config = runtime.schedule
        interval = interval_override or sched_config.interval
        max_retries = max_retries_override if max_retries_override is not None else sched_config.max_retries
        timeout = timeout_override or sched_config.timeout_sec
        max_cost = max_cost_override if max_cost_override is not None else sched_config.max_cost_usd

    # Create the executor-agent wrapper (sync or async variant)
    agent = agent_cls(resolved)
    task = get_recipe_task_description(resolved)

    # Create scheduler instance
    scheduler = scheduler_cls(
        agent=agent,
        task=task,
        timeout=timeout,
        max_cost=max_cost,
        on_success=on_success,
        on_failure=on_failure,
    )

    # Store recipe metadata and schedule config
    scheduler._recipe_name = recipe_name
    scheduler._recipe_resolved = resolved
    scheduler._yaml_schedule_config = {
        'interval': interval,
        'max_retries': max_retries,
        'run_immediately': False,
        'timeout': timeout,
        'max_cost': max_cost,
    }

    return scheduler


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