"""Regression coverage for token accounting with quiet output defaults."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from collections import defaultdict

from praisonaiagents.llm.llm import LLM
from praisonaiagents.telemetry.token_collector import get_token_collector


def _display_functions():
    return defaultdict(MagicMock)


def test_chat_completion_tracks_tokens_when_metrics_display_is_disabled(
    monkeypatch,
):
    collector = get_token_collector()
    collector.reset()
    llm = LLM(model="custom/test-model", api_key="test")
    llm.metrics = False
    llm.verbose = False
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: False)
    monkeypatch.setattr(
        llm,
        "_call_with_retry",
        lambda _fn, **_kwargs: {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
    )

    with patch(
        "praisonaiagents.llm.llm._get_display_functions",
        return_value=_display_functions(),
    ):
        assert llm.get_response(prompt="hello", stream=False, verbose=False) == "ok"

    summary = collector.get_session_summary()
    assert summary["total_interactions"] == 1
    assert summary["total_metrics"]["input_tokens"] == 12
    assert summary["total_metrics"]["output_tokens"] == 3


def test_nested_usage_details_are_collected():
    collector = get_token_collector()
    collector.reset()
    llm = LLM(model="custom/test-model", api_key="test")

    llm._track_token_usage({"usage": {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "prompt_tokens_details": {"cached_tokens": 4, "audio_tokens": 2},
        "completion_tokens_details": {"reasoning_tokens": 1, "audio_tokens": 1},
    }}, llm.model)

    metrics = collector.get_session_summary()["total_metrics"]
    assert metrics["cached_tokens"] == 4
    assert metrics["reasoning_tokens"] == 1
    assert metrics["audio_input_tokens"] == 2
    assert metrics["audio_output_tokens"] == 1


def test_responses_api_tracks_tokens_when_metrics_display_is_disabled(
    monkeypatch,
):
    collector = get_token_collector()
    collector.reset()
    llm = LLM(model="openai/gpt-4o-mini", api_key="test")
    llm.metrics = False
    llm.verbose = False
    response = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=8, output_tokens=2)
    )
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: True)
    monkeypatch.setattr(llm, "_build_responses_params", lambda **_kwargs: {})
    monkeypatch.setattr(llm, "_call_responses_api", lambda **_kwargs: response)
    monkeypatch.setattr(
        llm,
        "_extract_from_responses_output",
        lambda _response: ("ok", [], None),
    )

    with patch(
        "praisonaiagents.llm.llm._get_display_functions",
        return_value=_display_functions(),
    ):
        assert llm.get_response(prompt="hello", stream=False, verbose=False) == "ok"

    summary = collector.get_session_summary()
    assert summary["total_interactions"] == 1
    assert summary["total_metrics"]["input_tokens"] == 8
    assert summary["total_metrics"]["output_tokens"] == 2
