"""`/context` uses the same full-window percent as the status bar."""

from praisonai_code.cli.features.context_manager import _context_window_figures
from praisonai_code.cli.features.display_jsonl import _window_fields


def test_nested_stats_use_the_full_window_not_usable_budget():
    # gpt-4o usable budget is 128000 - 16384 = 111616.
    # 15234 / 111616 is 13%. 15234 / 128000 is 11%. The report must say 11.
    stats = {
        "model": "gpt-4o",
        "budget": {
            "model_limit": 128000,
            "output_reserve": 16384,
            "usable": 111616,
        },
        "ledger": {
            "total": 15234,
            "segments": {
                "history": {"tokens": 15234, "budget": 80000, "utilization": 0.19},
            },
        },
        "utilization": 15234 / 111616,
    }
    figures = _context_window_figures(stats)
    assert figures["percent"] == 11
    assert figures["limit"] == 128000
    assert figures["used"] == 15234
    assert figures["usable"] == 111616
    assert "history" in figures["segments"]


def test_unknown_model_has_no_percent_even_when_the_budget_says_128k():
    stats = {
        "model": "totally-unknown-model-xyz",
        "budget": {"model_limit": 128000, "output_reserve": 8000, "usable": 120000},
        "ledger": {"total": 1000, "segments": {}},
    }
    figures = _context_window_figures(stats)
    assert figures["percent"] is None
    assert figures["known"] is False
    assert figures["used"] == 1000


def test_explicit_zero_usage_stays_zero():
    figures = _context_window_figures({
        "model": "gpt-4o",
        "budget": {"model_limit": 128000, "usable": 111616, "output_reserve": 16384},
        "ledger": {"total": 0},
        "total_tokens": 99999,
    })
    assert figures["used"] == 0
    assert figures["percent"] == 0


def test_headless_jsonl_reports_the_same_window():
    fields = _window_fields(
        1000,
        "claude-3-5-sonnet",
        {
            "input_tokens": 1000,
            "cache_read_input_tokens": 5000,
            "cache_creation_input_tokens": 2000,
        },
    )
    assert fields == {
        "context_tokens": 8000,
        "context_window_size": 200000,
        "context_usage_percent": 4,
    }


def test_headless_jsonl_omits_an_unknown_model():
    assert _window_fields(1000, "totally-unknown-model-xyz", None) == {}


class _Console:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(arg) for arg in args))


def test_context_show_survives_live_manager_stats():
    from praisonai_code.cli.features.context_manager import (
        ContextManagerHandler,
        _show_context_summary,
    )

    handler = ContextManagerHandler(model="gpt-4o")
    handler.track_history([
        {"role": "user", "content": "hello " * 200},
        {"role": "assistant", "content": "world"},
    ])
    console = _Console()
    _show_context_summary(console, handler)
    text = "\n".join(console.lines)
    assert "Current Usage:" in text
    assert "% of 128,000" in text
    assert "Turns:" in text and "Messages:" in text


def test_context_show_unknown_model_does_not_raise():
    from praisonai_code.cli.features.context_manager import (
        ContextManagerHandler,
        _show_context_summary,
    )

    handler = ContextManagerHandler(model="totally-unknown-model-xyz")
    handler.track_history([{"role": "user", "content": "hi"}])
    console = _Console()
    _show_context_summary(console, handler)
    text = "\n".join(console.lines)
    assert "Model Limit:    unknown" in text
    assert "128,000" not in text


def test_flat_stats_still_report_a_percent():
    figures = _context_window_figures({
        "total_tokens": 8192,
        "model_limit": 128000,
        "usable": 100000,
        "output_reserve": 28000,
    })
    assert figures["percent"] == 6
    assert figures["limit"] == 128000


def test_interactive_stats_distinguish_unrecorded_categories():
    from praisonai_code.cli.features.context_manager import handle_context_command

    state = {"current_model": "gpt-4o", "conversation_history": [{"role": "user", "content": "hello"}]}
    console = _Console()
    handle_context_command(console, "stats", state)
    lines = console.lines
    assert any("Partial estimate" in line for line in lines)
    assert next(line for line in lines if line.startswith("system_prompt")).split()[1] == "-"
    assert int(next(line for line in lines if line.startswith("history")).split()[1]) > 0
    # The machine-facing ledger remains numeric and its contract is unchanged.
    assert state["context_manager"].get_stats()["ledger"]["ledger"]["system_prompt"] == 0


def test_interactive_stats_preserve_recorded_zero_and_summary_is_partial():
    from praisonai_code.cli.features.context_manager import ContextManagerHandler, handle_context_command

    manager = ContextManagerHandler(model="gpt-4o")
    manager.track_system_prompt("")
    state = {"conversation_history": []}
    console = _Console()
    handle_context_command(console, "stats", state, manager)
    assert next(line for line in console.lines if line.startswith("system_prompt")).split()[1] == "0"
    console = _Console()
    handle_context_command(console, "show", state, manager)
    assert any("Partial estimate" in line for line in console.lines)
