"""A tool named by a string must reach the model on the OpenAI-native path.

`OpenAIClient.format_tools()` documents string function names as a supported
tool format, and `_generate_tool_definition_from_name` returned None
unconditionally. The string branch is

    tool_def = self._generate_tool_definition_from_name(tool)
    if tool_def:
        formatted_tools.append(tool_def)

so the tool was dropped from the request with no exception and nothing above
`logging.debug`. The model was simply never offered it, and `Agent(tools=[...])`
with the same name worked on the LiteLLM path -- same code, different dispatch,
different behaviour.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.tools.registry import get_registry


def get_weather(city: str) -> str:
    """Return the weather for a city."""
    return f"sunny in {city}"


@pytest.fixture
def client():
    return OpenAIClient(api_key="sk-test-not-real")


@pytest.fixture
def registered_tool():
    registry = get_registry()
    registry.register(get_weather, name="get_weather", overwrite=True)
    yield "get_weather"


def _names(tools):
    return [t["function"]["name"] for t in (tools or [])]


def test_string_tool_from_the_registry_reaches_the_model(client, registered_tool):
    formatted = client.format_tools([registered_tool])

    assert _names(formatted) == ["get_weather"]
    assert formatted[0]["type"] == "function"
    assert "city" in formatted[0]["function"]["parameters"]["properties"]


def test_string_tool_matches_the_callable_form(client, registered_tool):
    by_name = client.format_tools([registered_tool])
    by_callable = client.format_tools([get_weather])

    # The two entry points documented by format_tools must agree; they did not,
    # because one of them produced nothing at all.
    assert by_name == by_callable


def test_string_tool_resolved_from_main(client, monkeypatch):
    # A script's own tools live in __main__, not in the registry, and the
    # LiteLLM path already falls back there.
    import __main__

    monkeypatch.setattr(__main__, "lookup_from_main", get_weather, raising=False)
    get_registry().unregister("lookup_from_main")

    formatted = client.format_tools(["lookup_from_main"])

    assert _names(formatted) == ["get_weather"]


def test_explicit_definition_dict_wins(client, monkeypatch):
    import __main__

    definition = {
        "type": "function",
        "function": {
            "name": "hand_written",
            "description": "supplied by the caller",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
    monkeypatch.setattr(__main__, "hand_written_definition", definition, raising=False)
    get_registry().unregister("hand_written")

    assert client.format_tools(["hand_written"]) == [definition]


def test_unknown_string_tool_is_still_dropped(client):
    # Unchanged behaviour, and deliberately so: a name that resolves to nothing
    # cannot be turned into a schema. This pins that the fix did not start
    # inventing definitions.
    get_registry().unregister("no_such_tool_anywhere")

    assert client.format_tools(["no_such_tool_anywhere"]) in (None, [])
