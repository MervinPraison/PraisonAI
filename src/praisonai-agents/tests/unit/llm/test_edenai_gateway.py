"""Tests for the Eden AI gateway route (``edenai/<vendor>/<model>``).

Eden AI is an OpenAI-compatible gateway: one endpoint fronts many vendors, and
the model id it expects is itself ``<vendor>/<model>``. LiteLLM has no
``edenai`` provider, so PraisonAI routes ``edenai/`` through LiteLLM's
OpenAI-compatible client against Eden AI's endpoint.

Two properties carry most of the risk and are asserted directly:

* The vendor named *inside* an Eden AI id is reached **through** the gateway,
  so it must not be read as a direct Anthropic/Gemini/Ollama route -- those
  paths disable streaming or rewrite the message shape.
* The model reaching LiteLLM is ``openai/...``, so LiteLLM would happily fill
  in ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL`` for it. The route must resolve
  both explicitly and fail closed rather than spend an OpenAI credential
  against api.edenai.run.

No network access and no Eden AI credentials are required.
"""

import json

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.model_providers import is_edenai_model

# Every credential/endpoint variable that could leak into a resolved request.
_PROVIDER_ENV = (
    "EDENAI_API_KEY", "EDENAI_BASE_URL",
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_MODEL_NAME",
    "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OLLAMA_API_BASE",
    "OLLAMA_HOST",
)

EDEN_ROUTES = [
    "edenai/openai/gpt-4.1-mini",
    "edenai/anthropic/claude-sonnet-4-5",
    "edenai/google/gemini-2.5-flash",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate provider env vars, then supply only an Eden AI key."""
    for var in _PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EDENAI_API_KEY", "eden-test-key")


# ---------------------------------------------------------------- recognition

@pytest.mark.parametrize("model", EDEN_ROUTES)
def test_route_is_recognised_as_edenai(model):
    assert is_edenai_model(model)
    assert LLM(model=model)._detect_provider() == "edenai"


def test_prefix_match_is_case_insensitive_and_scoped():
    assert is_edenai_model("EdenAI/openai/gpt-4.1-mini")
    # Not a route prefix: a vendor or model that merely contains the word.
    assert not is_edenai_model("openai/edenai-tuned-model")
    assert not is_edenai_model("edenai")
    assert not is_edenai_model("")


@pytest.mark.parametrize(
    "value",
    [None, 123, 4.5, True, b"edenai/x", ["edenai/x"], {"model": "edenai/x"}, object()],
)
def test_non_string_models_are_not_eden_routes(value):
    """The predicate runs on every request build, so odd values must not raise.

    ``_resolve_openai_compatible_model`` already guards ``isinstance(model, str)``;
    this guards the same way and returns a real ``bool``. Before the type check,
    a duck-typed stand-in answered ``startswith`` with a truthy object, which
    classified it as an Eden AI route and then demanded ``EDENAI_API_KEY``.
    """
    assert is_edenai_model(value) is False


def test_a_mock_model_is_not_an_eden_route():
    """The specific footgun: a mock answers any method with a truthy mock.

    Called out separately from the other non-string values because a test
    double is the way this would realistically reach the predicate.
    """
    from unittest.mock import MagicMock

    assert is_edenai_model(MagicMock()) is False


def test_predicate_returns_a_real_bool_on_the_positive_path():
    """``is`` rather than truthiness, so the ``-> bool`` annotation is enforced."""
    assert is_edenai_model("edenai/openai/gpt-4.1-mini") is True
    assert is_edenai_model("openai/gpt-4.1-mini") is False


# -------------------------------------------------------- model normalisation

@pytest.mark.parametrize(
    "model,expected",
    [
        ("edenai/openai/gpt-4.1-mini", "openai/openai/gpt-4.1-mini"),
        ("edenai/anthropic/claude-sonnet-4-5", "openai/anthropic/claude-sonnet-4-5"),
        ("edenai/google/gemini-2.5-flash", "openai/google/gemini-2.5-flash"),
    ],
)
def test_model_is_routed_through_the_openai_compatible_client(model, expected):
    assert LLM(model=model)._build_completion_params()["model"] == expected


def test_arbitrary_vendor_and_model_are_forwarded_untouched():
    """No catalogue: anything after ``edenai/`` is passed through verbatim.

    Eden AI adds vendors and models continuously, so a route naming one this
    package has never heard of -- at any segment depth -- must still resolve.
    """
    for tail in ("acme/some-future-model-v9", "vendor/family/size-42b", "bare-model-id"):
        params = LLM(model=f"edenai/{tail}")._build_completion_params()
        assert params["model"] == f"openai/{tail}"


# ------------------------------------------------------- endpoint resolution

def test_default_endpoint_is_eden_ai():
    params = LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params()
    assert params["base_url"] == "https://api.edenai.run/v3"


def test_edenai_base_url_env_overrides_the_default(monkeypatch):
    monkeypatch.setenv("EDENAI_BASE_URL", "https://eu.edenai.example/v3")
    params = LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params()
    assert params["base_url"] == "https://eu.edenai.example/v3"


def test_explicit_base_url_overrides_the_env_var(monkeypatch):
    monkeypatch.setenv("EDENAI_BASE_URL", "https://eu.edenai.example/v3")
    params = LLM(
        model="edenai/openai/gpt-4.1-mini",
        base_url="https://api.edenai.run/v3",
    )._build_completion_params()
    assert params["base_url"] == "https://api.edenai.run/v3"


def test_a_stray_openai_base_url_cannot_redirect_the_route(monkeypatch):
    """The endpoint is resolved explicitly, so OPENAI_BASE_URL is not consulted."""
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    params = LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params()
    assert params["base_url"] == "https://api.edenai.run/v3"


# ----------------------------------------------------- credentials, closed

def test_api_key_comes_from_edenai_api_key():
    params = LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params()
    assert params["api_key"] == "eden-test-key"


def test_explicit_api_key_overrides_the_env_var():
    params = LLM(
        model="edenai/openai/gpt-4.1-mini", api_key="caller-key"
    )._build_completion_params()
    assert params["api_key"] == "caller-key"


def test_missing_edenai_key_fails_closed(monkeypatch):
    monkeypatch.delenv("EDENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="EDENAI_API_KEY"):
        LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params()


def test_openai_key_is_never_used_as_the_edenai_fallback(monkeypatch):
    """The security property: an Eden AI route must not spend an OpenAI key.

    The model handed to LiteLLM is ``openai/...``, so LiteLLM's own resolution
    would fall back to OPENAI_API_KEY. Refusing must happen here, before the
    request is built, and the refusal must not echo the secret.
    """
    monkeypatch.delenv("EDENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai-secret")

    with pytest.raises(ValueError) as exc:
        LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params()

    message = str(exc.value)
    assert "EDENAI_API_KEY" in message
    assert "sk-real-openai-secret" not in message


def test_blank_edenai_key_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("EDENAI_API_KEY", "   ")
    with pytest.raises(ValueError, match="EDENAI_API_KEY"):
        LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params()


# ------------------------------------ vendor heuristics stay out of the way

@pytest.mark.parametrize("model", EDEN_ROUTES)
def test_eden_routes_use_the_default_adapter(model):
    """Not the Anthropic adapter (streaming off) nor the Gemini one."""
    llm = LLM(model=model)
    assert type(llm._provider_adapter).__name__ == "DefaultAdapter"


def test_eden_claude_route_is_not_the_direct_anthropic_provider():
    llm = LLM(model="edenai/anthropic/claude-sonnet-4-5")
    assert llm._detect_provider() == "edenai"
    assert llm._provider_adapter.supports_streaming() is True


def test_eden_gemini_route_is_not_the_direct_gemini_provider():
    llm = LLM(model="edenai/google/gemini-2.5-flash")
    assert llm._detect_provider() == "edenai"
    assert llm._provider_adapter.supports_streaming_with_tools() is True


def test_eden_route_is_not_ollama_even_with_a_local_endpoint(monkeypatch):
    """An open-weights vendor behind Eden AI must not take the Ollama path.

    ``is_hosted_only_model`` deliberately does not cover open-weights families
    (Ollama really can serve Mistral), so a local ``OPENAI_BASE_URL`` -- the
    documented local-model recipe -- used to capture this route. The Ollama
    adapter rewrites tool results into natural-language user turns and drops
    ``tool_calls`` from the assistant message.
    """
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    llm = LLM(model="edenai/mistral/mistral-large-latest")

    assert llm._is_ollama_provider() is False
    assert llm._detect_provider() == "edenai"
    assert type(llm._provider_adapter).__name__ == "DefaultAdapter"
    # The standard OpenAI tool-result shape, not Ollama's "user" rewrite.
    assert llm._provider_adapter.format_tool_result_message("f", {"ok": 1})["role"] == "tool"


# ----------------------------------------------------------- request shape

def test_streaming_is_available_on_the_default_path():
    llm = LLM(model="edenai/anthropic/claude-sonnet-4-5")
    assert llm._provider_adapter.supports_streaming() is True
    assert llm._supports_streaming_tools() is True


def test_tools_and_caller_tool_choice_survive_the_route():
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Look up weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
        },
    }]
    params = LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params(
        messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        tool_choice="auto",
    )
    assert params["tools"] == tools
    assert params["tool_choice"] == "auto"


def test_structured_output_does_not_inject_gemini_native_parameters():
    """A Gemini model behind Eden AI still speaks OpenAI, not Gemini.

    ``response_mime_type``/``response_schema`` are Gemini-native and would be
    wrong on Eden AI's OpenAI-shaped endpoint. LiteLLM reports no
    structured-output capability for a gateway-routed model, so PraisonAI falls
    back to putting the schema in the prompt -- which is the safe behaviour and
    the one asserted here.
    """
    from pydantic import BaseModel

    class Answer(BaseModel):
        text: str

    params = LLM(model="edenai/google/gemini-2.5-flash")._build_completion_params(
        messages=[{"role": "user", "content": "hi"}],
        output_pydantic=Answer,
    )
    assert "response_mime_type" not in params
    assert "response_schema" not in params
    # Internal-only parameters never reach the provider.
    assert "output_pydantic" not in params


def test_eden_route_does_not_select_the_responses_api():
    for model in EDEN_ROUTES:
        assert LLM(model=model)._supports_responses_api() is False


# --------------------------------------------- LiteLLM call construction

def test_resolved_params_produce_the_expected_edenai_request(monkeypatch):
    """Integration-style: feed the resolved params to LiteLLM, mock the socket.

    Asserts the request LiteLLM actually builds -- URL, bearer token and the
    ``model`` in the JSON body -- because that body is what Eden AI validates.
    LiteLLM strips only the first path segment, so the vendor-qualified id must
    survive intact.
    """
    import httpx
    import litellm

    captured = {}

    def fake_send(self, request, **kwargs):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content or b"{}")
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "anthropic/claude-sonnet-4-5",
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "hello"},
                }],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            },
        )

    monkeypatch.setattr(httpx.Client, "send", fake_send)

    params = LLM(model="edenai/anthropic/claude-sonnet-4-5")._build_completion_params(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
    )
    response = litellm.completion(**params)

    assert captured["url"] == "https://api.edenai.run/v3/chat/completions"
    assert captured["authorization"] == "Bearer eden-test-key"
    assert captured["body"]["model"] == "anthropic/claude-sonnet-4-5"
    assert response.choices[0].finish_reason == "stop"
    assert response.usage.total_tokens == 4


@pytest.mark.parametrize(
    "status,expected_category",
    [(401, "auth"), (429, "rate_limit"), (400, "invalid_request"), (500, "transient")],
)
def test_edenai_errors_reuse_the_existing_classifier(monkeypatch, status, expected_category):
    """Gateway failures need no Eden-specific handling.

    Going out over LiteLLM's OpenAI client means Eden AI's HTTP statuses arrive
    as the same exception classes every other OpenAI-compatible provider
    raises, which the existing classifier already routes correctly.

    HTTP 422 -- which Eden AI returns for a malformed request body -- is
    deliberately absent: LiteLLM retries it once and then returns ``None``
    instead of raising. That was measured to be identical for a direct
    ``openai/gpt-4o-mini`` route and for bare ``litellm.completion`` with no
    PraisonAI involvement, so it is pre-existing LiteLLM behaviour rather than
    anything this route introduces. Asserting it here would pin a third-party
    quirk instead of this integration's contract.
    """
    import httpx
    import litellm

    from praisonaiagents.llm.error_classifier import classify_error

    def fake_send(self, request, **kwargs):
        return httpx.Response(status, request=request, json={"error": {"message": "nope"}})

    monkeypatch.setattr(httpx.Client, "send", fake_send)

    params = LLM(model="edenai/openai/gpt-4.1-mini")._build_completion_params(
        messages=[{"role": "user", "content": "hi"}],
        num_retries=0,
    )
    with pytest.raises(Exception) as exc:
        litellm.completion(**params)

    assert classify_error(exc.value).value == expected_category


# -------------------------------------------------------------- regression

@pytest.mark.parametrize(
    "model,expected_provider,expected_model",
    [
        ("gpt-4o-mini", "openai", "gpt-4o-mini"),
        ("openai/gpt-4o", "openai", "openai/gpt-4o"),
        ("anthropic/claude-3-5-sonnet", "anthropic", "anthropic/claude-3-5-sonnet"),
        ("gemini/gemini-1.5-flash", "gemini", "gemini/gemini-1.5-flash"),
        ("ollama/llama3", "ollama", "ollama/llama3"),
        # A different gateway: deliberately untouched by this change.
        ("openrouter/anthropic/claude-3.5-sonnet", "anthropic",
         "openrouter/anthropic/claude-3.5-sonnet"),
    ],
)
def test_direct_and_other_provider_routes_are_unchanged(model, expected_provider, expected_model):
    """Nothing outside the ``edenai/`` prefix may change behaviour."""
    llm = LLM(model=model)
    params = llm._build_completion_params()

    assert llm._detect_provider() == expected_provider
    assert params["model"] == expected_model
    # No endpoint or credential is invented for a non-Eden route.
    assert "base_url" not in params
    assert "api_key" not in params


def test_direct_ollama_detection_still_works(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    # Explicit prefix, and the env-based detection for a bare open-weights model.
    assert LLM(model="ollama/llama3")._is_ollama_provider() is True
    assert LLM(model="mistral-large")._is_ollama_provider() is True
    # A hosted-only family stays hosted even against a local endpoint.
    assert LLM(model="gpt-4o")._is_ollama_provider() is False


def test_direct_anthropic_and_gemini_heuristics_are_untouched():
    """The vendor predicates keep their meaning for direct routes."""
    assert LLM(model="anthropic/claude-3-5-sonnet")._is_anthropic_model() is True
    assert LLM(model="claude-3-5-sonnet")._is_anthropic_model() is True
    assert LLM(model="gemini/gemini-1.5-flash")._is_gemini_model() is True
    assert LLM(model="anthropic/claude-3-5-sonnet")._provider_adapter.supports_streaming() is False
