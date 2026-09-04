"""The provider registry must accept the forms its own errors recommend.

`parse_model_string` raises, for an un-inferable model:

    Cannot infer provider from model 'llama3'. Use the 'provider/model' form,
    e.g. 'ollama/llama3', 'bedrock/anthropic.claude-3-sonnet'.

Following that advice then failed:

    Unknown praisonai.llm_providers plugin: 'ollama'.
    Available: ['anthropic', 'custom-gateway', 'google', 'litellm-proxy', ...]

Only openai, anthropic and google had builtin loaders, even though every one of
these routes is resolved by litellm, which is what the loaders wrap.
"""

import pytest

from praisonai.llm.registry import create_llm_provider, parse_model_string


LOCAL_MODELS = [
    "ollama/llama3",
    "ollama_chat/llama3",
    "lm_studio/qwen2.5-7b-instruct",
    "vllm/meta-llama/Llama-3.1-8B-Instruct",
    "hosted_vllm/Qwen2.5-7B",
]


@pytest.mark.parametrize("model", LOCAL_MODELS)
def test_local_provider_can_be_created(model):
    """The provider/model form must produce a provider, not a ValueError."""
    provider = create_llm_provider(model)
    assert provider is not None


@pytest.mark.parametrize("model", LOCAL_MODELS)
def test_local_provider_keeps_the_full_model_string(model):
    """litellm needs the prefix to route, so it must not be stripped.

    The provider stores the prefix (in config["provider"]) and the suffix (in
    model_id) separately, then reconstructs "provider/model" at request time.
    Assert BOTH survive -- checking the suffix alone would let a regression that
    drops the prefix pass here and only fail once litellm is actually called.
    """
    provider_id, model_suffix = model.split("/", 1)

    provider = create_llm_provider(model)

    model_attr = getattr(provider, "model_id", None) or getattr(provider, "model", None)
    assert model_attr is not None
    assert model_suffix in str(model_attr)

    # The prefix must survive too, otherwise litellm cannot route the request.
    prefix = getattr(provider, "config", {}).get("provider")
    assert prefix == provider_id


def test_the_exact_example_from_the_error_message_works():
    """`ollama/llama3` is the string parse_model_string tells users to write."""
    assert create_llm_provider("ollama/llama3") is not None


@pytest.mark.parametrize("model", LOCAL_MODELS)
def test_parse_model_string_agrees_with_creation(model):
    parsed = parse_model_string(model)
    assert parsed["provider_id"] == model.split("/", 1)[0]
    create_llm_provider(model)  # must not raise


# --- unchanged behaviour ------------------------------------------------------

@pytest.mark.parametrize(
    "model", ["openai/gpt-4o", "anthropic/claude-3-5-sonnet-latest", "google/gemini-1.5-flash"]
)
def test_existing_providers_still_work(model):
    assert create_llm_provider(model) is not None


def test_unknown_provider_still_raises():
    """Adding local routes must not turn the registry into a silent accept-all."""
    with pytest.raises(ValueError) as exc:
        create_llm_provider("definitely-not-a-provider/some-model")
    assert "definitely-not-a-provider" in str(exc.value)


def test_uninferable_bare_model_still_raises():
    with pytest.raises(ValueError) as exc:
        parse_model_string("llama3")
    assert "provider/model" in str(exc.value)
