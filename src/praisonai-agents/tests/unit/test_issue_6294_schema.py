"""Regression tests for issue #6294: container/model tool schemas."""
from dataclasses import dataclass
from typing import List, Mapping, Sequence, Set, Tuple, TypedDict

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
