"""Regression tests for issue #6294: tool argument coercion."""
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

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
