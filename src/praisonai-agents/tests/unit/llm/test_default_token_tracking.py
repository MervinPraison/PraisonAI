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


def test_openai_client_tracks_tokens_when_display_is_disabled(monkeypatch):
    """Default Agent(llm="gpt-4o-mini") uses the native OpenAI client path.

    That path must populate the public token collector after a paid call
    even with no verbose/metrics display (Issue #3933).
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    from praisonaiagents.llm.openai_client import OpenAIClient

    collector = get_token_collector()
    collector.reset()

    client = OpenAIClient(api_key="test")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="OK", tool_calls=None, role="assistant"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=2, total_tokens=13),
    )
    monkeypatch.setattr(client, "create_completion", lambda **_kwargs: response)
    monkeypatch.setattr(client, "format_tools", lambda _tools: None)

    result = client.chat_completion_with_tools(
        messages=[{"role": "user", "content": "Say OK"}],
        model="gpt-4o-mini",
        tools=None,
        stream=False,
        verbose=False,
        agent_name="tester",
    )

    assert result.choices[0].message.content == "OK"
    summary = collector.get_session_summary()
    assert summary["total_interactions"] == 1
    assert summary["total_metrics"]["input_tokens"] == 11
    assert summary["total_metrics"]["output_tokens"] == 2
    assert "gpt-4o-mini" in summary["by_model"]
    assert "tester" in summary["by_agent"]
    assert client.last_token_metrics is not None


def test_openai_client_usage_without_tokens_is_not_recorded(monkeypatch):
    """A response with no usage (e.g. assembled stream chunks) is skipped."""
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    from praisonaiagents.llm.openai_client import OpenAIClient

    collector = get_token_collector()
    collector.reset()

    client = OpenAIClient(api_key="test")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="OK", tool_calls=None, role="assistant"),
                finish_reason="stop",
            )
        ],
        usage=None,
    )
    monkeypatch.setattr(client, "create_completion", lambda **_kwargs: response)
    monkeypatch.setattr(client, "format_tools", lambda _tools: None)

    client.chat_completion_with_tools(
        messages=[{"role": "user", "content": "Say OK"}],
        model="gpt-4o-mini",
        tools=None,
        stream=False,
        verbose=False,
    )

    assert collector.get_session_summary()["total_interactions"] == 0
