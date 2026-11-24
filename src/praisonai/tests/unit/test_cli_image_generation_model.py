"""Exercise direct-prompt dispatch through LiteLLM with an offline HTTP response."""

import json
from types import SimpleNamespace

import httpx
import pytest

from praisonai.cli.legacy.direct_prompt import handle_direct_prompt


@pytest.mark.parametrize(
    "requested_model",
    [None, "gpt-image-2.5-flare", "openai/gpt-image-2.5-flare"],
    ids=["default", "bare", "qualified"],
)
def test_direct_prompt_image_generation(monkeypatch, requested_model):
    # Exercise the same path as a LiteLLM install lacking the remote model map.
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-no-network")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    for proxy in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(proxy, raising=False)
        monkeypatch.delenv(proxy.lower(), raising=False)

    import litellm

    monkeypatch.setattr(litellm, "telemetry", False)
    monkeypatch.delitem(litellm.model_cost, "gpt-image-2.5-flare", raising=False)
    requests = []

    def send(_client, request, **_kwargs):
        assert str(request.url) == "https://api.openai.com/v1/images/generations"
        assert request.method == "POST"
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"created": 1, "data": [{"b64_json": "dGVzdA=="}]},
            request=request,
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    cli = SimpleNamespace(
        args=SimpleNamespace(
            image_generate=True,
            llm=requested_model,
            no_rules=True,
            no_tools=True,
            tool_timeout=0,
            tool_retry_attempts=1,
        ),
        _rewrite_query_if_enabled=lambda prompt: prompt,
        _expand_prompt_if_enabled=lambda prompt: prompt,
    )

    result = handle_direct_prompt(cli, "A blue square")

    assert len(requests) == 1, result
    body = requests[0]
    assert body["model"] == "gpt-image-2.5-flare"
    assert body["prompt"] == "A blue square"
    assert "response_format" not in body
    assert result.data[0].b64_json == "dGVzdA=="
