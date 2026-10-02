"""Regression tests for Agent.chat(output_pydantic=...) structured-output contract.

Covers the bug in issue PAI-SDK-010 where chat()/achat() returned the raw
string instead of instantiating the requested Pydantic model.
"""
import os
import pytest
from types import SimpleNamespace
from pydantic import BaseModel
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")

from praisonaiagents import Agent
from praisonaiagents.errors import ValidationError


class Pair(BaseModel):
    city: str
    country: str


def _make_agent():
    return Agent(instructions="Return structured data only.", llm="gpt-4o-mini")


def _fake_response(content):
    """Minimal stand-in for an OpenAI chat completion response object."""
    message = SimpleNamespace(content=content, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class TestCoerceStructuredOutput:
    def test_parses_plain_json_into_model(self):
        agent = _make_agent()
        out = agent._coerce_structured_output(
            '{"city": "Paris", "country": "France"}', output_pydantic=Pair
        )
        assert isinstance(out, Pair)
        assert out.city == "Paris"
        assert out.country == "France"

    def test_parses_fenced_json_into_model(self):
        agent = _make_agent()
        fenced = '```json\n{"city": "Paris", "country": "France"}\n```'
        out = agent._coerce_structured_output(fenced, output_pydantic=Pair)
        assert isinstance(out, Pair)
        assert out.city == "Paris"

    def test_prose_raises_validation_error(self):
        agent = _make_agent()
        with pytest.raises(ValidationError):
            agent._coerce_structured_output(
                "The capital of France is Paris.", output_pydantic=Pair
            )

    def test_missing_field_raises_validation_error(self):
        agent = _make_agent()
        with pytest.raises(ValidationError):
            agent._coerce_structured_output('{"city": "Paris"}', output_pydantic=Pair)

    def test_output_json_returns_dict(self):
        agent = _make_agent()
        out = agent._coerce_structured_output(
            '{"a": 1}', output_json={"type": "object"}
        )
        assert out == {"a": 1}

    def test_no_schema_passthrough(self):
        agent = _make_agent()
        out = agent._coerce_structured_output("plain text")
        assert out == "plain text"


class TestChatReturnsModel:
    def test_openai_path_returns_model(self):
        agent = _make_agent()
        with patch.object(
            agent,
            "_chat_completion",
            return_value=_fake_response('{"city": "Paris", "country": "France"}'),
        ):
            out = agent.chat("Capital of France.", output_pydantic=Pair)
        assert isinstance(out, Pair)
        assert out.city == "Paris"
        assert out.country == "France"

    def test_openai_path_prose_raises(self):
        agent = _make_agent()
        with patch.object(
            agent,
            "_chat_completion",
            return_value=_fake_response("The capital of France is Paris."),
        ):
            with pytest.raises(ValidationError):
                agent.chat("Capital of France.", output_pydantic=Pair)
