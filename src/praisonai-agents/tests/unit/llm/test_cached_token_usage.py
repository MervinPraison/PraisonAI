import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_tokens": 8000, "prompt_tokens_details": {"cached_tokens": 5000}}, 5000),
    ({"input_tokens": 8000, "input_tokens_details": {"cached_tokens": 5000}}, 5000),
    (SimpleNamespace(prompt_tokens=8000, prompt_tokens_details=SimpleNamespace(cached_tokens=5000)), 5000),
    ({"prompt_tokens": 8000, "cached_tokens": 0, "prompt_tokens_details": {"cached_tokens": 5000}}, 0),
    ({"prompt_tokens": 8000, "prompt_tokens_details": {"cached_tokens": 0}, "cache_read_input_tokens": 5000}, 0),
    ({"input_tokens": 1000, "cache_read_input_tokens": 5000, "cache_creation_input_tokens": 2000}, 5000),
    ({"prompt_tokens": 8000}, 0),
])
def test_cache_read_precedence_and_presence(usage, expected):
    llm = LLM(model="custom/test-model", api_key="test")
    result = llm._extract_token_usage({"usage": usage})
    assert result.cached_tokens == expected


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_public_response_reports_litellm_normalized_anthropic_cache(monkeypatch, mode):
    litellm = pytest.importorskip("litellm.llms.anthropic.chat.transformation")
    raw = {"input_tokens": 1000, "output_tokens": 20, "cache_read_input_tokens": 5000, "cache_creation_input_tokens": 2000}
    usage = litellm.AnthropicConfig().calculate_usage(raw, None)
    llm = LLM(model="anthropic/claude-3-5-sonnet", api_key="test", prompt_caching=True)
    llm.metrics = False
    llm.verbose = False
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: False)
    response = {"choices": [{"message": {"content": "ok"}}], "usage": usage}
    monkeypatch.setattr(llm, "_call_with_retry", lambda fn, **kwargs: response)

    async def async_response(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message={"content": "ok"}, finish_reason="stop")], usage=usage)

    monkeypatch.setattr(llm, "_acompletion_with_retry", async_response)
    with patch("praisonaiagents.llm.llm._get_display_functions", return_value=defaultdict(MagicMock)):
        kwargs = dict(prompt="hello", stream=False, verbose=False, return_token_usage=True)
        text, tokens = llm.get_response(**kwargs) if mode == "sync" else asyncio.run(llm.get_response_async(**kwargs))
    assert text == "ok"
    assert (tokens.prompt_tokens, tokens.completion_tokens, tokens.total_tokens, tokens.cached_tokens) == (8000, 20, 8020, 5000)
