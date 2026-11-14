"""Regression tests for issue #6294: tool argument coercion."""
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple, Union

from pydantic import BaseModel

from praisonaiagents.agent.tool_execution import _coerce_value


class Addr(BaseModel):
    city: str


@dataclass
class Point:
    x: int


def test_coerce_values():
    assert _coerce_value("5", Optional[int]) == 5
    assert _coerce_value("[1,2]", List[int]) == [1, 2]
    assert _coerce_value(["a", "b"], Set[str]) == {"a", "b"}
    out = _coerce_value(["1.5", "2"], Tuple[float, int])
    assert out == (1.5, 2) and type(out[1]) is int
    out = _coerce_value([{"city": "x"}, "5"], Tuple[Addr, int])
    assert out == (Addr(city="x"), 5)
    assert _coerce_value({"x": "3"}, Point) == Point(x=3)
    assert _coerce_value([{"x": 1}], List[Point]) == [Point(x=1)]
    assert _coerce_value({"city": "x"}, Addr) == Addr(city="x")
    assert _coerce_value('{"city": "x"}', Addr) == Addr(city="x")
    # unchanged when not convertible / already right type
    assert _coerce_value("abc", Optional[int]) == "abc"
    assert _coerce_value("hello", Optional[str]) == "hello"
    assert _coerce_value("[1,", List[int]) == "[1,"
    assert _coerce_value("5", int) == 5 and _coerce_value("true", bool) is True


def _agent_with(tool):
    from praisonaiagents import Agent
    return Agent(name="a", instructions="x", llm="gpt-4o-mini", tools=[tool])


def test_decorated_tool_and_postponed_annotations_get_models():
    from praisonaiagents import tool

    def plain(address: "Addr") -> str:
        return address.city

    @tool
    def decorated(address: Addr) -> str:
        return address.city

    agent = _agent_with(plain)
    assert agent._cast_arguments(plain, {"address": {"city": "x"}}) == {"address": Addr(city="x")}
    agent = _agent_with(decorated)
    assert agent._cast_arguments(decorated.run, {"address": {"city": "y"}}) == {"address": Addr(city="y")}


def test_async_tool_call_casts_arguments():
    def where(address: Addr) -> str:
        return address.city

    agent = _agent_with(where)
    assert asyncio.run(agent._execute_tool_async_impl("where", {"address": {"city": "z"}})) == "z"


def test_union_edge_cases():
    # PEP 604 unions are unwrapped like typing.Union
    assert _coerce_value("[1, 2]", list[int] | None) == [1, 2]
    assert _coerce_value("3", int | None) == 3
    # A member that yields the wrong type must not win over a later valid one
    assert _coerce_value('{"city": "x"}', Union[List[int], Addr]) == Addr(city="x")
    # Dataclasses accept JSON strings, like models
    assert _coerce_value('{"x": "4"}', Point) == Point(x=4)


def test_failed_conversion_returns_original_string():
    # Parsed JSON must not leak out when the target type is not produced
    assert _coerce_value('{"town": 1}', Addr) == '{"town": 1}'
    assert _coerce_value('{"a": 1}', List[int]) == '{"a": 1}'
    assert _coerce_value("[1, 2]", Tuple[int, int, int]) == "[1, 2]"
    assert _coerce_value("[1, 2]", list) == [1, 2]


def test_any_annotation_does_not_abort_casting():
    # typing.Any is a class on 3.11+; isinstance(x, Any) must not abort the whole call
    from typing import Any

    def f(n: int, data: Any) -> str:
        return ""

    agent = _agent_with(f)
    assert agent._cast_arguments(f, {"n": "5", "data": [1]}) == {"n": 5, "data": [1]}
    assert _coerce_value("[1]", Any) == "[1]"
