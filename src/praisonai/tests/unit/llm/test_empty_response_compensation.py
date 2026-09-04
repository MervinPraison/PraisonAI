"""Ollama's empty-turn compensation, and its selection, now go through the adapter.

Ollama often returns an empty assistant turn after a successful tool call. The
guard for that was an inline predicate repeated in the sync and async paths and
gated on `_is_ollama_provider()`; the adapter declared the same predicate and had
no caller.

Swapping the gate for adapter dispatch is only behaviour-preserving if the two
agree on every input, so that equivalence is asserted here rather than assumed.
"""

import pytest

from praisonaiagents.llm.adapters import DefaultAdapter, OllamaAdapter
from praisonaiagents.llm.llm import LLM

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


# --- the precondition for the swap -------------------------------------------

@pytest.mark.parametrize("model, base_url", [
    ("ollama/llama3", None),
    ("ollama/qwen3:0.6b", None),
    ("my-ollama-model", None),
    ("ollama_chat/llama3", None),
    ("llama3", "http://127.0.0.1:11434"),
    ("gpt-4o", None),
    ("gpt-4o", "http://127.0.0.1:11434"),
    ("claude-3-5-sonnet-latest", None),
    ("gemini/gemini-2.0-flash", None),
    ("bedrock/anthropic.claude-3", None),
    ("vertex_ai/gemini-1.5-pro", None),
    ("openrouter/anthropic/claude-3", None),
])
def test_adapter_selection_matches_is_ollama_provider(model, base_url):
    """Dispatch must select OllamaAdapter exactly when _is_ollama_provider() is True.

    If this ever diverges, the two call sites wired in this change silently start
    applying Ollama's compensation to a provider that never asked for it -- or
    stop applying it to one that needs it.
    """
    llm = LLM(model=model, base_url=base_url)
    assert isinstance(llm._provider_adapter, OllamaAdapter) == llm._is_ollama_provider()


# --- the adapter must reflect the initial failover profile, not the pre-profile
#     provider (the profile can change providers before dispatch runs) ----------

class _OneShotFailover:
    """Minimal FailoverManagerProtocol that yields a single profile once."""

    def __init__(self, profile):
        self._profile = profile
        self._served = False

    def get_next_profile(self):
        if self._served:
            return None
        self._served = True
        return self._profile

    def mark_failure(self, profile, error, is_rate_limit=False):
        pass

    def mark_success(self, profile):
        pass


def test_initial_failover_profile_to_ollama_selects_ollama_adapter():
    """A profile that switches openai -> ollama must dispatch through OllamaAdapter.

    Adapter selection runs after the initial profile is applied, so the captured
    adapter and _is_ollama_provider() must agree on the post-profile model.
    """
    from praisonaiagents.llm.failover import AuthProfile

    profile = AuthProfile(
        name="local", provider="ollama", api_key="x", model="ollama/llama3"
    )
    llm = LLM(model="gpt-4o", failover_manager=_OneShotFailover(profile))
    assert llm.model == "ollama/llama3"
    assert llm._is_ollama_provider() is True
    assert isinstance(llm._provider_adapter, OllamaAdapter)


def test_initial_failover_profile_to_openai_selects_default_adapter():
    """A profile that switches ollama -> openai must not retain Ollama policy."""
    from praisonaiagents.llm.failover import AuthProfile

    profile = AuthProfile(
        name="cloud", provider="openai", api_key="sk-test", model="gpt-4o"
    )
    llm = LLM(model="ollama/llama3", failover_manager=_OneShotFailover(profile))
    assert llm.model == "gpt-4o"
    assert llm._is_ollama_provider() is False
    assert not isinstance(llm._provider_adapter, OllamaAdapter)


# --- the predicate itself -----------------------------------------------------

def state(**kw):
    base = {"iteration_count": 1, "accumulated_tool_results": [{"r": 1}], "response_text": ""}
    base.update(kw)
    return base


def test_ollama_signals_on_empty_response_after_tools():
    assert OllamaAdapter().handle_empty_response_with_tools(state()) is True


def test_whitespace_only_counts_as_empty():
    assert OllamaAdapter().handle_empty_response_with_tools(state(response_text="  \n ")) is True


def test_non_empty_response_does_not_signal():
    """A non-empty (even malformed) response must not trigger compensation."""
    assert OllamaAdapter().handle_empty_response_with_tools(
        state(response_text="{\n\n\n}")) is False


def test_iteration_zero_does_not_signal():
    assert OllamaAdapter().handle_empty_response_with_tools(state(iteration_count=0)) is False


def test_no_tool_results_does_not_signal():
    assert OllamaAdapter().handle_empty_response_with_tools(
        state(accumulated_tool_results=[])) is False


def test_default_adapter_never_signals():
    """Non-Ollama providers must not acquire this behaviour."""
    assert DefaultAdapter().handle_empty_response_with_tools(state()) is False


def test_missing_response_text_key_is_safe():
    """The call sites pass `response_text or ''`; the adapter must also cope alone."""
    assert OllamaAdapter().handle_empty_response_with_tools(
        {"iteration_count": 1, "accumulated_tool_results": [1]}) is True


# --- the wiring ---------------------------------------------------------------

def test_llm_consults_the_adapter(monkeypatch):
    """The gate is dispatch now, not a hardcoded _is_ollama_provider() call."""
    import inspect
    from praisonaiagents.llm import llm as llm_module

    source = inspect.getsource(llm_module.LLM)
    assert source.count("handle_empty_response_with_tools") == 2, (
        "expected the adapter predicate on both the sync and async paths"
    )
    assert "_is_ollama_provider() and accumulated_tool_results" not in source, (
        "the inline predicate is still present"
    )
