"""Tool retry has one budget and one vocabulary.

The effective RetryPolicy caps how many times a tool body runs, whichever
retry loop does the retrying; ExecutionConfig's retries/seconds/fraction
spelling is translated into that policy rather than run as a second budget.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig, ToolConfig
from praisonaiagents.tools.retry import RetryPolicy


def _runs(**agent_kwargs):
    """Run an always-failing tool once and report how many times its body ran."""
    calls = []

    def flaky():
        """Always fails."""
        calls.append(1)
        raise RuntimeError("boom")

    agent = Agent(instructions="x", tools=[flaky], **agent_kwargs)
    try:
        agent.execute_tool("flaky", {})
    except Exception:
        pass
    return len(calls)


@pytest.mark.parametrize("max_attempts", [1, 2, 3])
def test_retry_policy_caps_total_tool_runs(max_attempts):
    policy = RetryPolicy(max_attempts=max_attempts, initial_delay_ms=0)
    assert _runs(tool_config=ToolConfig(retry_policy=policy)) == max_attempts


@pytest.mark.parametrize("max_retry_limit", [0, 1, 2])
def test_execution_config_alias_still_caps_total_tool_runs(max_retry_limit):
    # ExecutionConfig counts *retries*, so total runs = limit + 1.
    assert _runs(
        execution=ExecutionConfig(
            max_retry_limit=max_retry_limit, retry_initial_delay=0.001
        )
    ) == max_retry_limit + 1


def test_execution_config_is_translated_into_the_retry_policy_vocabulary():
    agent = Agent(
        instructions="x",
        execution=ExecutionConfig(
            max_retry_limit=4,
            retry_initial_delay=2.5,   # seconds
            retry_backoff_factor=3.0,
            retry_jitter=0.1,          # fraction
        ),
    )
    policy = agent._effective_tool_retry_policy("anything")
    assert policy.max_attempts == 5          # retries + 1
    assert policy.initial_delay_ms == 2500   # seconds -> milliseconds
    assert policy.backoff_factor == 3.0
    assert policy.jitter is True             # fraction -> bool + factor
    assert policy.jitter_factor == 0.1


def test_explicit_retry_policy_wins_over_the_execution_config_alias():
    agent = Agent(
        instructions="x",
        tool_config=ToolConfig(retry_policy=RetryPolicy(max_attempts=7)),
        execution=ExecutionConfig(max_retry_limit=1),
    )
    assert agent._effective_tool_retry_policy("anything").max_attempts == 7


def test_should_retry_boundary_is_inclusive():
    """`attempt >= max_attempts` stops retrying — observed as tool-body runs.

    A `>` boundary would grant one extra run for every tool, which no
    behavioural test previously noticed.
    """
    assert RetryPolicy(max_attempts=2).should_retry("timeout", 2) is False
    policy = RetryPolicy(max_attempts=2, initial_delay_ms=0, retry_on={"unknown"})
    assert _runs(tool_config=ToolConfig(retry_policy=policy)) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"backoff_factor": 0.5},
        {"initial_delay_ms": -1},
        {"initial_delay_ms": 5000, "max_delay_ms": 1000},
        {"jitter_factor": 1.5},
    ],
)
def test_invalid_retry_policy_is_rejected_at_construction(kwargs):
    """__post_init__ must validate.

    Without it, RetryPolicy(max_attempts=0) makes the sync retry loop's
    `range(1, max_attempts + 1)` empty: the tool body never runs at all and the
    caller silently gets no result.
    """
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_zero_attempts_would_skip_the_tool_entirely():
    """Pin the harm the validation prevents, at the execution layer."""
    policy = RetryPolicy(max_attempts=1, initial_delay_ms=0)
    object.__setattr__(policy, "max_attempts", 0)  # bypass validation
    assert _runs(tool_config=ToolConfig(retry_policy=policy)) == 0


def _runs_returning(result, **agent_kwargs):
    """Run a tool that always returns ``result`` and count its body runs."""
    calls = []

    def flaky():
        """Always returns the same (error) dict."""
        calls.append(1)
        return dict(result)

    agent = Agent(instructions="x", tools=[flaky], **agent_kwargs)
    try:
        agent.execute_tool("flaky", {})
    except Exception:
        pass
    return len(calls)


@pytest.mark.parametrize("max_attempts", [2, 3, 4])
def test_inner_retried_timeout_is_not_multiplied_by_outer_loop(max_attempts):
    """A persistently-timing-out tool runs at most max_attempts times, not N².

    ``timeout`` is in the inner loop's retry_on, so the inner loop exhausts the
    whole budget before returning. The outer loop must NOT re-escalate it as
    retryable (which would restart the inner budget every outer pass -> N²).
    """
    policy = RetryPolicy(max_attempts=max_attempts, initial_delay_ms=0)
    runs = _runs_returning(
        {"error": "connection timed out", "timeout": True},
        tool_config=ToolConfig(retry_policy=policy),
    )
    assert runs == max_attempts


def test_non_inner_retried_error_still_gets_one_outer_pass():
    """An error type the inner loop does NOT retry ("unknown") gets outer passes.

    This preserves the outer loop's purpose for genuinely-uncovered errors
    while the inner-retried types above are capped at max_attempts total.
    """
    policy = RetryPolicy(max_attempts=3, initial_delay_ms=0, retry_on={"unknown"})
    runs = _runs_returning(
        {"error": "some unexpected failure"},
        tool_config=ToolConfig(retry_policy=policy),
    )
    assert runs == 3


def test_execution_config_translation_preserves_60s_delay_cap():
    """ExecutionConfig users kept a 60s base cap under the old BackoffPolicy.

    RetryPolicy defaults to a 30s cap; the translation must lift it back to 60s
    so existing configs retry with the same delay ceiling.
    """
    agent = Agent(
        instructions="x",
        execution=ExecutionConfig(
            max_retry_limit=10,
            retry_initial_delay=1.0,
            retry_backoff_factor=2.0,
            retry_jitter=0.0,   # isolate the deterministic cap
        ),
    )
    policy = agent._effective_tool_retry_policy("anything")
    assert policy.max_delay_ms == 60000
    # A late attempt would otherwise blow past 30s; confirm it caps at 60s.
    assert policy.get_delay_ms(20) == 60000
