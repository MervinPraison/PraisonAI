"""Interactive ``/cost`` reports real usage from the token collector (Issue #6043)."""

import pytest

from praisonai_code.cli.features.cost_tracker import get_pricing
from praisonai_code.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig


@pytest.fixture
def collector():
    from praisonaiagents.telemetry.token_collector import get_token_collector

    c = get_token_collector()
    c.reset()
    yield c
    c.reset()


def test_cost_command_reflects_collected_turn(collector):
    from praisonaiagents.telemetry.token_collector import TokenMetrics

    tui = AsyncTUI(config=AsyncTUIConfig(model="gpt-4o-mini"))
    # What the LLM layer records after one agent turn.
    collector.track_tokens("gpt-4o-mini", "a", TokenMetrics(input_tokens=1000, output_tokens=100))

    assert tui._handle_command("/cost") is True
    out = tui.messages[-1].content
    expected = get_pricing("gpt-4o-mini").calculate_cost(1000, 100)
    assert "Total tokens:   1100" in out
    assert f"${expected:.4f}" in out
    assert "$0.0000" not in out
