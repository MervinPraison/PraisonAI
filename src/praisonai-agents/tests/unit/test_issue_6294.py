"""Regression tests for issue #6294."""
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Set, Tuple, TypedDict

import pytest
from pydantic import BaseModel

from praisonaiagents.agent.tool_execution import _coerce_value
from praisonaiagents.tools.schema import annotation_to_json_schema


class Addr(BaseModel):
    city: str


@dataclass
class Point:
    x: int


class TD(TypedDict):
    a: int


@pytest.mark.parametrize("ann,expected_type", [
    (Sequence[str], "array"), (Set[str], "array"), (Tuple[int, int], "array"),
    (tuple, "array"), (set, "array"), (Mapping[str, int], "object"),
    (Addr, "object"), (Point, "object"), (TD, "object"),
])
def test_container_and_model_schemas(ann, expected_type):
    assert annotation_to_json_schema(ann)["type"] == expected_type


def test_nested_schema_items():
    assert annotation_to_json_schema(List[Addr])["items"]["type"] == "object"
    assert annotation_to_json_schema(Set[str])["uniqueItems"] is True
    assert annotation_to_json_schema(Point)["properties"] == {"x": {"type": "integer"}}


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


def _team(tasks, process="sequential"):
    from praisonaiagents import Agent, AgentTeam
    return AgentTeam(agents=[tasks[0].agent], tasks=tasks, process=process)


def _make_tasks():
    from praisonaiagents import Agent, Task
    a = Agent(name="a", instructions="x", llm="gpt-4o-mini")
    t1 = Task(name="t1", description="d1", agent=a, expected_output="o")
    t2 = Task(name="t2", description="d2", agent=a, expected_output="o", depends_on=[t1])
    return t1, t2


@pytest.mark.parametrize("process", ["sequential", "workflow"])
def test_depends_on_orders_tasks(process):
    t1, t2 = _make_tasks()
    team = _team([t2, t1], process)
    assert [t.name for t in team.tasks.values()] == ["t1", "t2"]


def test_depends_on_cycle_raises():
    t1, t2 = _make_tasks()
    t1.depends_on = [t2]
    with pytest.raises(ValueError, match="Circular"):
        _team([t1, t2], "workflow")


def test_depends_on_dangling_raises():
    t1, t2 = _make_tasks()
    with pytest.raises(ValueError, match="not part of"):
        _team([t2])


def test_linear_order_unchanged():
    from praisonaiagents import Agent, Task
    a = Agent(name="a", instructions="x", llm="gpt-4o-mini")
    tasks = [Task(name=f"t{i}", description="d", agent=a, expected_output="o") for i in range(3)]
    team = _team(tasks)
    assert [t.name for t in team.tasks.values()] == ["t0", "t1", "t2"]


def test_tuple_schema_fixed_length():
    assert annotation_to_json_schema(Tuple[int])["maxItems"] == 1
    assert annotation_to_json_schema(Tuple[int, str])["minItems"] == 2


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


def test_import_leaves_root_logging_to_host(monkeypatch):
    from praisonaiagents import _logging

    root = logging.getLogger()
    monkeypatch.delenv("LOGLEVEL", raising=False)
    monkeypatch.setattr(root, "handlers", [])
    _logging.configure_root_logger()
    assert root.handlers == []
