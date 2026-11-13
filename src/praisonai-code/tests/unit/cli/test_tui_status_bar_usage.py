"""Status bar shows live context-window usage and session cost (Issue #6357)."""

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


def _track(collector, model="gpt-4o-mini", i=1000, o=100):
    from praisonaiagents.telemetry.token_collector import TokenMetrics

    collector.track_tokens(model, "a", TokenMetrics(input_tokens=i, output_tokens=o))


def test_no_usage_renders_original_bar(collector):
    tui = AsyncTUI(config=AsyncTUIConfig(model="gpt-4o-mini"))
    tui._refresh_usage_status()
    bar = tui._status_bar_text()
    assert bar == f" ? for help | PageUp/Down to scroll  |  gpt-4o-mini  |  Session: {tui.session_id} "


def test_mid_session_shows_context_and_cost(collector):
    tui = AsyncTUI(config=AsyncTUIConfig(model="gpt-4o-mini"))
    tui._conversation_history = [
        {"role": "user", "content": "hello " * 200},
        {"role": "assistant", "content": "world " * 200},
    ]
    _track(collector)
    tui._refresh_usage_status()
    bar = tui._status_bar_text()
    expected = get_pricing("gpt-4o-mini").calculate_cost(1000, 100)
    assert "ctx " in bar and "/128.0k (" in bar
    assert f"1.1k tok ${expected:.4f}" in bar
    assert bar.isascii()


def test_show_cost_false_hides_cost(collector):
    tui = AsyncTUI(config=AsyncTUIConfig(model="gpt-4o-mini", show_cost=False))
    _track(collector)
    tui._refresh_usage_status()
    bar = tui._status_bar_text()
    assert "1.1k tok" in bar
    assert "$" not in bar


def test_unpriced_model_hides_cost(collector):
    tui = AsyncTUI(config=AsyncTUIConfig(model="totally-unknown-model-xyz"))
    _track(collector, model="totally-unknown-model-xyz")
    tui._refresh_usage_status()
    bar = tui._status_bar_text()
    assert "1.1k tok" in bar
    assert "$" not in bar


def test_context_failure_degrades_gracefully(collector, monkeypatch):
    tui = AsyncTUI(config=AsyncTUIConfig(model="gpt-4o-mini"))
    tui._conversation_history = [{"role": "user", "content": "hi"}]

    def boom():
        raise RuntimeError("no context package")

    monkeypatch.setattr(tui, "_get_context_manager", boom)
    tui._refresh_usage_status()
    assert "ctx" not in tui._status_bar_text()


def test_new_conversation_clears_readout(collector):
    tui = AsyncTUI(config=AsyncTUIConfig(model="gpt-4o-mini"))
    _track(collector)
    tui._refresh_usage_status()
    assert "tok" in tui._status_bar_text()
    tui._handle_command("/new")
    tui._refresh_usage_status()
    assert "tok" not in tui._status_bar_text()
