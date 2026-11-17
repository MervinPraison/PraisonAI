"""D-14: an untyped tool parameter takes its schema type from its default.

``def lookup(q, n=3, exact=False)`` was described to the model with every
parameter typed ``string``, so the model was told to send ``"3"`` and
``"False"``. A default of a plain type now sets the type; a hint, when
present, still wins, and an untyped parameter with no default stays a string.
"""

import inspect
import logging
import typing

import pytest

from praisonaiagents.tools.schema import build_parameters_schema, build_tool_definition


def lookup(q, n=3, exact=False, ratio=0.5, tags=None, opts=()):
    return q


def typed(q: str, n: str = "3"):
    """Typed: hints win."""
    return q


@pytest.mark.parametrize("build", ["definition", "parameters"])
def test_default_sets_the_type(build):
    props = (build_tool_definition(lookup)["function"]["parameters"] if build == "definition"
             else build_parameters_schema(inspect.signature(lookup), typing.get_type_hints(lookup)))["properties"]
    assert props["q"]["type"] == "string"
    assert props["n"]["type"] == "integer"
    assert props["exact"]["type"] == "boolean"
    assert props["ratio"]["type"] == "number"
    assert props["tags"]["type"] == "string"   # None says nothing about the type


@pytest.mark.parametrize("build", ["definition", "parameters"])
def test_hints_still_win(build):
    props = (build_tool_definition(typed)["function"]["parameters"] if build == "definition"
             else build_parameters_schema(inspect.signature(typed), typing.get_type_hints(typed)))["properties"]
    assert props["n"]["type"] == "string"


def test_untyped_tool_warns_once(caplog):
    def untyped_once(a, b=1):
        return a
    with caplog.at_level(logging.WARNING):
        build_tool_definition(untyped_once)
        build_tool_definition(untyped_once)
    hits = [r for r in caplog.records if "untyped_once" in r.getMessage() and "type hints" in r.getMessage()]
    assert len(hits) == 1
