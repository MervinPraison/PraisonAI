"""A provider-prefixed default model must reach LLM (litellm), not OpenAIClient.

`Agent._PROVIDER_DEFAULT_MODELS` maps a credential env var to a provider-prefixed
default model, e.g. ``OLLAMA_HOST -> "ollama/llama3.2"``. The branch chain in
``Agent.__init__`` that routes ``provider/model`` strings to ``LLM`` tests the
*original* ``llm=`` argument, which is ``None`` when the model came from the
environment. Such an agent therefore fell through to ``OpenAIClient`` and failed
with "OPENAI_API_KEY environment variable is required" -- while holding a model
name OpenAI has never heard of.

These tests assert on constructed state only. They make no network call and need
no server, so they are safe in the default suite.
"""

import pytest

from praisonaiagents import Agent


# Every credential env var the Agent scans, so a stray one in the developer's
# environment cannot change which default is resolved.
_CREDENTIAL_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "OLLAMA_HOST",
    "OPENAI_MODEL_NAME",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove every credential var, and reset Agent's cached default model."""
    for var in _CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    # The default model is memoised on the class; without this the first test to
    # run would pin the answer for every later one.
    monkeypatch.setattr(Agent, "_default_model_checked", False, raising=False)
    monkeypatch.setattr(Agent, "_default_model", None, raising=False)
    yield
    monkeypatch.setattr(Agent, "_default_model_checked", False, raising=False)
    monkeypatch.setattr(Agent, "_default_model", None, raising=False)


@pytest.mark.parametrize(
    "env_var, env_value, expected_model",
    [
        ("OLLAMA_HOST", "http://localhost:11434", "ollama/llama3.2"),
        ("ANTHROPIC_API_KEY", "sk-ant-test", "anthropic/claude-3-5-sonnet-latest"),
        ("GEMINI_API_KEY", "test", "gemini/gemini-1.5-flash"),
        ("GOOGLE_API_KEY", "test", "google/gemini-1.5-flash"),
        ("GROQ_API_KEY", "test", "groq/llama-3.3-70b-versatile"),
        ("COHERE_API_KEY", "test", "cohere/command-r"),
    ],
)
def test_provider_prefixed_default_routes_to_llm(
    clean_env, monkeypatch, env_var, env_value, expected_model
):
    """A credential env var alone must produce an agent wired to litellm.

    Before the fix every one of these resolved the right model name and then
    routed it to OpenAIClient, which has no provider adapters and demands an
    OpenAI key.
    """
    monkeypatch.setenv(env_var, env_value)

    agent = Agent(instructions="test")

    assert agent.llm == expected_model
    assert agent._using_custom_llm is True, (
        f"{env_var} resolved {agent.llm!r} but left _using_custom_llm False, "
        "so the agent routes to OpenAIClient instead of litellm"
    )
    assert agent._llm_init_params is not None
    assert agent._llm_init_params["model"] == expected_model


def test_openai_default_still_uses_openai_client(clean_env, monkeypatch):
    """The OpenAI default has no provider prefix and must not change route.

    This is the backward-compatibility anchor: existing OpenAI users keep the
    plain openai-SDK path.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    agent = Agent(instructions="test")

    assert agent.llm == "gpt-4o-mini"
    assert agent._using_custom_llm is False
    assert getattr(agent, "_llm_init_params", None) is None


def test_explicit_bare_model_still_uses_openai_client(clean_env, monkeypatch):
    """An explicit bare model name keeps its current route."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    agent = Agent(instructions="test", llm="gpt-4o")

    assert agent.llm == "gpt-4o"
    assert agent._using_custom_llm is False


def test_openai_model_name_with_prefix_routes_to_llm(clean_env, monkeypatch):
    """OPENAI_MODEL_NAME carrying a provider prefix behaves like llm=.

    `Agent(llm="ollama/x")` already routes to litellm; the env-var form must not
    disagree with it.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL_NAME", "ollama/llama3.2")

    agent = Agent(instructions="test")

    assert agent.llm == "ollama/llama3.2"
    assert agent._using_custom_llm is True
    assert agent._llm_init_params["model"] == "ollama/llama3.2"


def test_env_default_matches_explicit_llm_routing(clean_env, monkeypatch):
    """The same model must route identically whether given by env or by llm=."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    from_env = Agent(instructions="test")

    for var in _CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(Agent, "_default_model_checked", False, raising=False)
    explicit = Agent(instructions="test", llm="ollama/llama3.2")

    assert from_env.llm == explicit.llm
    assert from_env._using_custom_llm == explicit._using_custom_llm
    assert from_env._llm_init_params["model"] == explicit._llm_init_params["model"]


def test_non_string_llm_argument_does_not_raise(clean_env, monkeypatch):
    """A dict without a "model" key falls into the same branch; guard the type.

    The prefix check must not assume `model_name` is a string, or this raises.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    agent = Agent(instructions="test", llm={"temperature": 0.5})

    assert agent._using_custom_llm is False
