"""
TDD tests for the autonomous-run spend kill-switch (issue #3003).

Covers:
- USD cap halts the run with a typed BUDGET_EXHAUSTED outcome
- Token cap halts the run
- budget_action='pause' is recoverable (partial output + paused status)
- No cap set = unlimited (identical to today's behaviour)
- TerminationReason enum string values are stable + budget_exhausted added
- Budget cap coexists with turn/time caps (whichever trips first wins)
"""

import pytest
from unittest.mock import patch

from praisonaiagents.run_outcome import (
    TerminationReason,
    termination_to_run_status,
)


def _make_agent(**autonomy):
    from praisonaiagents import Agent
    cfg = {"max_iterations": 20, "auto_escalate": False}
    cfg.update(autonomy)
    return Agent(instructions="Test agent", autonomy=cfg)


# ---------------------------------------------------------------------------
# Enum stability
# ---------------------------------------------------------------------------

def test_termination_reason_enum_values_stable():
    """Enum string values equal the strings historically emitted; budget added."""
    assert TerminationReason.GOAL_MET == "goal"
    assert TerminationReason.TOOL_COMPLETION == "tool_completion"
    assert TerminationReason.PROMISE == "promise"
    assert TerminationReason.NO_TOOL_CALLS == "no_tool_calls"
    assert TerminationReason.MAX_ITERATIONS == "max_iterations"
    assert TerminationReason.TIMEOUT == "timeout"
    assert TerminationReason.DOOM_LOOP == "doom_loop"
    assert TerminationReason.NEEDS_HELP == "needs_help"
    assert TerminationReason.INTERRUPTED == "interrupted"
    assert TerminationReason.CANCELLED == "cancelled"
    assert TerminationReason.ERROR == "error"
    # NEW
    assert TerminationReason.BUDGET_EXHAUSTED == "budget_exhausted"


def test_termination_to_run_status_mapping():
    """budget_exhausted maps into the shared AgentRunOutcome vocabulary."""
    assert termination_to_run_status(TerminationReason.GOAL_MET) == "success"
    assert termination_to_run_status(TerminationReason.BUDGET_EXHAUSTED) == "failure"
    assert termination_to_run_status(TerminationReason.TIMEOUT) == "timeout"
    assert termination_to_run_status("interrupted") == "cancelled"
    assert termination_to_run_status("unknown_reason") == "failure"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_accepts_budget_fields():
    from praisonaiagents.agent.autonomy import AutonomyConfig
    c = AutonomyConfig(max_budget_usd=2.0, max_tokens=400_000, budget_action="stop")
    assert c.max_budget_usd == 2.0
    assert c.max_tokens == 400_000
    assert c.budget_action == "stop"


def test_config_rejects_bad_budget_action():
    from praisonaiagents.agent.autonomy import AutonomyConfig
    with pytest.raises(ValueError):
        AutonomyConfig(budget_action="explode")


def test_config_from_dict_budget_fields():
    from praisonaiagents.agent.autonomy import AutonomyConfig
    c = AutonomyConfig.from_dict({
        "max_budget_usd": 1.5, "max_tokens": 100, "budget_action": "pause",
    })
    assert c.max_budget_usd == 1.5
    assert c.max_tokens == 100
    assert c.budget_action == "pause"


# ---------------------------------------------------------------------------
# Enforcement — USD
# ---------------------------------------------------------------------------

@patch("praisonaiagents.agent.agent.Agent.chat")
@patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
def test_usd_cap_halts_run(mock_stage, mock_chat):
    """Cumulative cost crossing max_budget_usd stops with BUDGET_EXHAUSTED."""
    mock_chat.return_value = "still working on it, more to do"
    agent = _make_agent(max_budget_usd=1.0, budget_action="stop")

    # Cost accrues $0.40 per iteration → crosses $1.00 at iteration 3.
    spend = {"n": 0}

    def fake_spend():
        spend["n"] += 1
        return (0.40 * spend["n"], 0)

    with patch.object(type(agent), "_run_spend", lambda self: fake_spend()):
        result = agent.run_autonomous("Do something")

    assert result.completion_reason == TerminationReason.BUDGET_EXHAUSTED
    assert result.success is False
    assert result.iterations == 3
    assert result.metadata["spend_usd"] == pytest.approx(1.2)
    assert result.metadata["status"] == "stopped"


# ---------------------------------------------------------------------------
# Enforcement — tokens
# ---------------------------------------------------------------------------

@patch("praisonaiagents.agent.agent.Agent.chat")
@patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
def test_token_cap_halts_run(mock_stage, mock_chat):
    """Cumulative tokens crossing max_tokens stops with BUDGET_EXHAUSTED."""
    mock_chat.return_value = "still working on it, more to do"
    agent = _make_agent(max_tokens=1000)

    spend = {"n": 0}

    def fake_spend():
        spend["n"] += 1
        return (0.0, 400 * spend["n"])

    with patch.object(type(agent), "_run_spend", lambda self: fake_spend()):
        result = agent.run_autonomous("Do something")

    assert result.completion_reason == TerminationReason.BUDGET_EXHAUSTED
    assert result.iterations == 3
    assert result.metadata["tokens"] == 1200


# ---------------------------------------------------------------------------
# Pause is recoverable
# ---------------------------------------------------------------------------

@patch("praisonaiagents.agent.agent.Agent.chat")
@patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
def test_budget_pause_is_recoverable(mock_stage, mock_chat):
    """budget_action='pause' returns paused status with the partial output."""
    mock_chat.return_value = "partial progress, still working"
    agent = _make_agent(max_budget_usd=1.0, budget_action="pause")

    with patch.object(type(agent), "_run_spend", lambda self: (5.0, 0)):
        result = agent.run_autonomous("Do something")

    assert result.completion_reason == TerminationReason.BUDGET_EXHAUSTED
    assert result.metadata["status"] == "paused"
    assert result.output == "partial progress, still working"
    # Raising the cap and resuming continues (no early stop).
    agent.autonomy_config["max_budget_usd"] = 100.0
    with patch.object(type(agent), "_run_spend", lambda self: (5.0, 0)):
        resumed = agent.run_autonomous("Do something")
    assert resumed.completion_reason != TerminationReason.BUDGET_EXHAUSTED


# ---------------------------------------------------------------------------
# No cap = unlimited
# ---------------------------------------------------------------------------

@patch("praisonaiagents.agent.agent.Agent.chat")
@patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
def test_no_cap_is_unlimited(mock_stage, mock_chat):
    """Caps unset → no early budget stop even with high spend."""
    mock_chat.return_value = "The task is done."
    agent = _make_agent()

    with patch.object(type(agent), "_run_spend", lambda self: (999.0, 999999)):
        result = agent.run_autonomous("Do something")

    assert result.completion_reason != TerminationReason.BUDGET_EXHAUSTED
    assert result.success is True


# ---------------------------------------------------------------------------
# Coexistence with turn cap
# ---------------------------------------------------------------------------

@patch("praisonaiagents.agent.agent.Agent.chat")
@patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
def test_turn_cap_wins_when_it_trips_first(mock_stage, mock_chat):
    """If spend never crosses the cap, the turn cap still bounds the run."""
    mock_chat.return_value = "still working, more to do"
    agent = _make_agent(max_iterations=2, max_budget_usd=1000.0)

    with patch.object(type(agent), "_run_spend", lambda self: (0.01, 10)):
        result = agent.run_autonomous("Do something")

    assert result.completion_reason == TerminationReason.MAX_ITERATIONS
    assert result.iterations == 2


# ---------------------------------------------------------------------------
# Async parity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("praisonaiagents.agent.agent.Agent.get_recommended_stage", return_value="heuristic")
async def test_async_usd_cap_halts_run(mock_stage):
    from unittest.mock import AsyncMock
    agent = _make_agent(max_budget_usd=1.0, budget_action="stop")

    spend = {"n": 0}

    def fake_spend():
        spend["n"] += 1
        return (0.40 * spend["n"], 0)

    with patch.object(type(agent), "achat", new=AsyncMock(return_value="still working, more to do")):
        with patch.object(type(agent), "_run_spend", lambda self: fake_spend()):
            result = await agent.run_autonomous_async("Do something")

    assert result.completion_reason == TerminationReason.BUDGET_EXHAUSTED
    assert result.iterations == 3
