"""Regression tests for issue #6294."""
import os
import subprocess
import sys
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
    assert _coerce_value([1, 2], Tuple[float, float]) == (1.0, 2.0)
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


def test_import_leaves_root_logging_to_host(tmp_path):
    log_file = tmp_path / "app.log"
    code = (
        "import logging, praisonaiagents\n"
        "root = logging.getLogger()\n"
        "assert root.handlers == [], root.handlers\n"
        "assert root.level == logging.WARNING\n"
        "assert logging.getLogger('httpx').propagate\n"
        f"logging.basicConfig(filename={str(log_file)!r}, level=logging.DEBUG)\n"
        "logging.getLogger('myapp').debug('hello')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "LOGLEVEL"}
    subprocess.run([sys.executable, "-c", code], check=True, env=env, cwd=str(tmp_path))
    assert "hello" in log_file.read_text()
