"""The stream path now filters Ollama's tool arguments, like the other two.

`_validate_and_filter_ollama_arguments` drops arguments that do not appear in the
target function's signature. Weak local models routinely emit arguments belonging
to a *different* function, and dispatching those calls the user's tool with
parameters it never declared.

It was applied on the sync and async paths and absent from both of the stream
path's dispatch points. Porting it is safe there because it runs *before*
`execute_tool_fn`, so nothing has been yielded that would need retracting -- which
is what separates it from the repair-and-retry compensations that genuinely
cannot work while streaming.
"""

import inspect

import pytest

from praisonaiagents.llm import llm as llm_module
from praisonaiagents.llm.llm import LLM

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _source(name):
    return inspect.getsource(getattr(LLM, name))


def test_stream_path_now_filters_arguments():
    """Both stream dispatch points guard before calling the tool."""
    src = _source("get_response_stream")
    assert src.count("_validate_and_filter_ollama_arguments") == 2, (
        "expected the filter at both the streaming and fallback dispatch points"
    )


@pytest.mark.parametrize("method", ["get_response", "get_response_async", "get_response_stream"])
def test_every_response_path_filters(method):
    """The parity this step exists to create."""
    assert "_validate_and_filter_ollama_arguments" in _source(method)


def test_filter_runs_before_dispatch_in_the_stream_path():
    """Pre-dispatch placement is what makes this streaming-safe."""
    src = _source("get_response_stream")
    first_filter = src.index("_validate_and_filter_ollama_arguments")
    first_exec = src.index("execute_tool_fn(function_name, arguments)")
    assert first_filter < first_exec


# --- the filter's own behaviour ------------------------------------------------

def make_llm():
    return LLM(model="ollama/qwen3:0.6b")


def get_weather(city: str) -> str:
    """Get the weather.

    Args:
        city: the city
    """
    return f"{city}: sunny"


def test_argument_from_another_function_is_dropped():
    llm = make_llm()
    filtered = llm._validate_and_filter_ollama_arguments(
        "get_weather", {"city": "Paris", "stock_symbol": "AAPL"}, [get_weather])
    assert filtered == {"city": "Paris"}


def test_valid_arguments_survive_untouched():
    llm = make_llm()
    assert llm._validate_and_filter_ollama_arguments(
        "get_weather", {"city": "Paris"}, [get_weather]) == {"city": "Paris"}


def test_unknown_function_is_left_alone():
    """If we cannot inspect the target, do not silently drop the user's data."""
    llm = make_llm()
    args = {"anything": 1}
    assert llm._validate_and_filter_ollama_arguments("not_a_tool", args, [get_weather]) == args


def test_no_tools_leaves_arguments_alone():
    llm = make_llm()
    args = {"city": "Paris"}
    assert llm._validate_and_filter_ollama_arguments("get_weather", args, []) == args


def test_guard_is_scoped_to_ollama():
    """`if is_ollama and tools` keeps this a no-op for every other provider."""
    src = _source("get_response_stream")
    idx = src.index("_validate_and_filter_ollama_arguments")
    window = src[max(0, idx - 400):idx]
    assert "if is_ollama and tools:" in window
