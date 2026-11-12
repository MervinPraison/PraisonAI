"""Regression tests for issue #6294: container/model tool schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, List, Mapping, Sequence, Set, Tuple, TypedDict

from typing_extensions import NotRequired, Required

import pytest
from pydantic import BaseModel

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


def test_tuple_schema_fixed_length():
    assert annotation_to_json_schema(Tuple[int])["maxItems"] == 1
    assert annotation_to_json_schema(Tuple[int, str])["minItems"] == 2


def test_empty_tuple_allows_no_items():
    assert annotation_to_json_schema(Tuple[()])["maxItems"] == 0


@dataclass
class WithExtras:
    x: int
    k: ClassVar[int] = 0
    computed: int = field(init=False)


def test_dataclass_only_constructor_fields():
    schema = annotation_to_json_schema(WithExtras)
    assert schema["properties"] == {"x": {"type": "integer"}}
    assert schema["required"] == ["x"]


@dataclass
class Node:
    name: str
    children: List["Node"]


def test_recursive_dataclass_stops_expanding():
    items = annotation_to_json_schema(Node)["properties"]["children"]["items"]
    assert items == {"type": "object"}


class TotalTD(TypedDict):
    a: NotRequired[int]
    b: int


class PartialTD(TypedDict, total=False):
    c: Required[int]
    d: int


def test_typeddict_required_markers():
    assert annotation_to_json_schema(TotalTD)["required"] == ["b"]
    assert annotation_to_json_schema(PartialTD)["required"] == ["c"]
