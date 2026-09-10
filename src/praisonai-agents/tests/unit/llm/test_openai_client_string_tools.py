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
import contextlib

import pytest

from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.tools.registry import get_registry


def get_weather(city: str) -> str:
    """Return the weather for a city."""
    return f"sunny in {city}"


@pytest.fixture
def client():
    # The fixture always passes an explicit key, so nothing here should touch
    # the process-wide OPENAI_API_KEY and leak a fake credential into unrelated
    # tests that exercise the no-key path.
    return OpenAIClient(api_key="sk-test-not-real")


@contextlib.contextmanager
def _registry_name(name, tool):
    """Register ``name`` for the test and restore the registry afterwards.

    get_registry() is a process-global singleton, so a test that overwrites or
    removes an entry without restoring it makes later tests depend on execution
    order. Snapshot the prior entry and put it back on exit.
    """
    registry = get_registry()
    previous = registry._tools.get(name)
    registry.register(tool, name=name, overwrite=True)
    try:
        yield name
    finally:
        if previous is not None:
            registry._tools[name] = previous
        else:
            registry.unregister(name)


@contextlib.contextmanager
def _registry_absent(name):
    """Ensure ``name`` is unregistered for the test and restore it afterwards."""
    registry = get_registry()
    previous = registry._tools.get(name)
    registry.unregister(name)
    try:
        yield name
    finally:
        if previous is not None:
            registry._tools[name] = previous
        else:
            registry.unregister(name)


@pytest.fixture
def registered_tool():
    with _registry_name("get_weather", get_weather) as name:
        yield name


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
    with _registry_absent("lookup_from_main"):
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
    with _registry_absent("hand_written"):
        assert client.format_tools(["hand_written"]) == [definition]


def test_unknown_string_tool_is_still_dropped(client):
    # Unchanged behaviour, and deliberately so: a name that resolves to nothing
    # cannot be turned into a schema. This pins that the fix did not start
    # inventing definitions.
    with _registry_absent("no_such_tool_anywhere"):
        assert client.format_tools(["no_such_tool_anywhere"]) in (None, [])


def test_string_tool_is_not_cached_across_registry_changes(client):
    # A string name resolves against the mutable registry, so a re-registration
    # between two format_tools() calls must reach the model as the new schema,
    # never a stale cached one.
    def get_weather(city: str, unit: str) -> str:
        """Return the weather for a city in a given unit."""
        return f"sunny in {city} ({unit})"

    with _registry_name("get_weather", get_weather):
        first = client.format_tools(["get_weather"])
        assert set(first[0]["function"]["parameters"]["properties"]) == {"city", "unit"}

        def get_weather(city: str) -> str:  # noqa: F811 - deliberate re-definition
            """Return the weather for a city."""
            return f"sunny in {city}"

        get_registry().register(get_weather, name="get_weather", overwrite=True)
        second = client.format_tools(["get_weather"])
        assert set(second[0]["function"]["parameters"]["properties"]) == {"city"}
