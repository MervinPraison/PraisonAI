"""Unit tests for Agent.chat structured-output coercion.

Covers the fix for issue #5594: ``Agent.chat(output_pydantic=Model)`` must
return a validated Pydantic instance (not a raw JSON string) on the live
OpenAI/LiteLLM path. These tests exercise the ``_coerce_structured_output``
helper directly so no live LLM is required.
"""
from pydantic import BaseModel

from praisonaiagents.agent.chat_mixin import ChatMixin


class Pair(BaseModel):
    city: str
    country: str


def _mixin():
    m = ChatMixin()
    m.name = "TestAgent"
    return m


def test_valid_json_string_returns_model():
    out = _mixin()._coerce_structured_output(
        '{"city": "Paris", "country": "France"}', Pair
    )
    assert isinstance(out, Pair)
    assert out.city == "Paris"
    assert out.country == "France"


def test_markdown_fenced_json_returns_model():
    fenced = '```json\n{"city": "Paris", "country": "France"}\n```'
    out = _mixin()._coerce_structured_output(fenced, Pair)
    assert isinstance(out, Pair)
    assert out.city == "Paris"


def test_prose_falls_back_to_raw_string():
    out = _mixin()._coerce_structured_output(
        "The capital of France is Paris.", Pair
    )
    assert isinstance(out, str)
    assert out == "The capital of France is Paris."


def test_no_schema_returns_input_unchanged():
    out = _mixin()._coerce_structured_output("hello", None)
    assert out == "hello"


def test_non_string_input_returns_unchanged():
    instance = Pair(city="Paris", country="France")
    out = _mixin()._coerce_structured_output(instance, Pair)
    assert out is instance


def test_dict_schema_without_model_validate_json_returns_raw():
    # dict schemas (inline JSON schema) have no model_validate_json; must not crash
    out = _mixin()._coerce_structured_output('{"a": 1}', {"type": "object"})
    assert out == '{"a": 1}'
