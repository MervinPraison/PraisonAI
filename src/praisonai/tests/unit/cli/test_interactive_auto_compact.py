"""
Tests for interactive auto-compaction wiring.

Verifies that the interactive worker loop honours the ``auto_compact`` flag and
triggers the existing compaction path when the running conversation nears the
model's usable context budget, plus the reactive context-length error detection.
"""

import pytest

il = pytest.importorskip(
    "praisonai.cli.legacy.interactive_legacy",
    reason="interactive_legacy requires optional CLI dependencies",
)


class _FakeConsole:
    def print(self, *args, **kwargs):
        pass


def test_model_context_window_lookup():
    assert il._model_context_window("gpt-4o-mini") == 128000
    assert il._model_context_window("openai/gpt-4o") == 128000
    assert il._model_context_window("claude-3-5-sonnet-latest") == 200000
    assert il._model_context_window(None) == 128000
    assert il._model_context_window("totally-unknown-model") == 128000


def test_usable_budget_subtracts_output_reserve():
    session_state = {
        "current_model": "gpt-4o-mini",
        "context_config": {"output_reserve": 8000},
    }
    assert il._usable_context_budget(session_state) == 128000 - 8000


def test_usable_budget_caps_reserve_on_small_models():
    # gpt-4 has an 8192-token window; an 8000-token reserve must not swallow it.
    session_state = {
        "current_model": "gpt-4",
        "context_config": {"output_reserve": 8000},
    }
    budget = il._usable_context_budget(session_state)
    assert budget == 8192 - (8192 // 4)
    assert budget > 1000


def test_context_length_error_detection():
    assert il._is_context_length_error(
        Exception("This model's maximum context length is 8192 tokens")
    )
    assert il._is_context_length_error(Exception("context_length_exceeded"))
    assert not il._is_context_length_error(Exception("rate limit reached"))


def test_auto_compact_respects_disabled_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(il, "_handle_compact_command",
                        lambda *a, **k: calls.append(1))
    session_state = {
        "context_config": {"auto_compact": False},
        "conversation_history": [{"role": "user", "content": "x" * 999999}] * 10,
        "current_model": "gpt-4",
    }
    assert il._maybe_auto_compact(None, _FakeConsole(), session_state) is False
    assert calls == []


def test_auto_compact_noop_below_threshold(monkeypatch):
    calls = []
    monkeypatch.setattr(il, "_handle_compact_command",
                        lambda *a, **k: calls.append(1))
    session_state = {
        "context_config": {"auto_compact": True, "threshold": 0.8},
        "conversation_history": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
        ] * 2,
        "current_model": "gpt-4o-mini",
    }
    assert il._maybe_auto_compact(None, _FakeConsole(), session_state) is False
    assert calls == []


def test_auto_compact_triggers_over_threshold(monkeypatch):
    calls = []
    monkeypatch.setattr(il, "_handle_compact_command",
                        lambda *a, **k: calls.append(1))
    big = "word " * 5000
    session_state = {
        "context_config": {
            "auto_compact": True,
            "threshold": 0.8,
            "output_reserve": 8000,
        },
        "conversation_history": [
            {"role": "user", "content": big},
            {"role": "assistant", "content": big},
        ] * 3,
        "current_model": "gpt-4",
    }
    assert il._maybe_auto_compact(None, _FakeConsole(), session_state) is True
    assert calls == [1]
