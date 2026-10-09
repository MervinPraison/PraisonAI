"""Unit tests for Agent.chat structured-output coercion.

Covers the fix for issue #5594: ``Agent.chat(output_pydantic=Model)`` must
return a validated Pydantic instance (not a raw JSON string) on the live
OpenAI/LiteLLM path. These tests exercise the ``_coerce_structured_output``
helper directly so no live LLM is required.
"""
from types import SimpleNamespace

from pydantic import BaseModel

from praisonaiagents.agent.chat_mixin import ChatMixin


class Pair(BaseModel):
    city: str
    country: str


def _fake_completion(content):
    """Build a minimal OpenAI-style response object for mocking."""
    message = SimpleNamespace(content=content, reasoning_content=None, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


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


def test_embedded_json_object_in_prose_returns_model():
    prose = 'Here is the answer:\n{"city": "Paris", "country": "France"}\nThanks.'
    out = _mixin()._coerce_structured_output(prose, Pair)
    assert isinstance(out, Pair)
    assert out.city == "Paris"


def test_structured_output_from_message_parsed():
    class Answer(BaseModel):
        value: int

    message = SimpleNamespace(
        parsed=Answer(value=42),
        content=None,
    )
    out = _mixin()._structured_output_from_message(message, Answer, "")
    assert isinstance(out, Answer)
    assert out.value == 42


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


# --- Public-path tests: chat()/achat() wiring and backward-compat guards ---


def _agent(monkeypatch, content):
    """Build a real Agent whose LLM call is mocked to return ``content``.

    A placeholder API key lets the lazy OpenAI client construct; the network is
    never touched because ``_chat_completion`` is mocked.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "not-needed")
    from praisonaiagents import Agent

    agent = Agent(name="TestAgent", instructions="test")
    monkeypatch.setattr(agent, "_chat_completion", lambda *a, **k: _fake_completion(content))
    return agent


def test_chat_output_pydantic_returns_model(monkeypatch):
    # Public chat() path must return a validated Pydantic instance (issue #5594).
    agent = _agent(monkeypatch, '{"city": "Paris", "country": "France"}')
    out = agent.chat("capital of France?", output_pydantic=Pair)
    assert isinstance(out, Pair)
    assert out.city == "Paris"


def test_chat_output_json_stays_string(monkeypatch):
    # Backward compat: output_json must keep returning a raw JSON string so that
    # downstream task/workflow JSON parsing (json.loads) keeps working.
    agent = _agent(monkeypatch, '{"city": "Paris", "country": "France"}')
    out = agent.chat("capital of France?", output_json=Pair)
    assert isinstance(out, str)
    assert '"Paris"' in out


def test_after_agent_hook_receives_string_for_pydantic(monkeypatch):
    # A Pydantic response must not crash command/string hooks: the after-agent
    # hook payload truncates via response[:500], which requires a string.
    agent = _agent(monkeypatch, '{"city": "Paris", "country": "France"}')
    payload = agent._build_after_agent_input(
        prompt="p", response=Pair(city="Paris", country="France"), start_time=0.0
    )
    assert isinstance(payload.response, str)
    # to_dict() performs the [:500] slice that would otherwise raise on a model
    assert isinstance(payload.to_dict()["response"], str)


def test_embedded_json_uses_first_complete_object():
    out = _mixin()._coerce_structured_output(
        'Answer: {"city": "Paris", "country": "France"}. Metadata: {"ok": true}', Pair
    )
    assert isinstance(out, Pair)
    assert out.city == "Paris"


def test_parsed_ignored_when_guardrail_changed_response():
    # message.parsed must not override a guardrail-approved replacement answer.
    message = SimpleNamespace(parsed=Pair(city="Paris", country="France"))
    approved = '{"city": "Lyon", "country": "France"}'
    out = _mixin()._structured_output_from_message(message, Pair, approved, "original")
    assert out.city == "Lyon"
    same = _mixin()._structured_output_from_message(message, Pair, "x", "x")
    assert same.city == "Paris"
