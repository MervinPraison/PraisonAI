"""N-7: output_pydantic on the default route reaches the model and parses.

``Agent(llm="gpt-4o-mini")`` with no base URL goes through the OpenAI
Responses API. Native structured output is used there, so the schema text is
left out of the prompt -- but ``response_format`` was dropped while building
the Responses request, leaving the model with no schema and the reply unparsed
("could not be parsed into the model", a plain str back).

The contract suite's stub server sets a base URL, which turns the Responses
API off, so it never covered this path. Here the SDK's ``responses.create`` is
patched instead: the request is recorded and no network is used.
"""

import asyncio
import json

import pydantic
import pytest

from praisonaiagents import Agent

openai = pytest.importorskip("openai")
from openai.resources.responses import AsyncResponses, Responses  # noqa: E402
from openai.types.responses import Response  # noqa: E402


class Answer(pydantic.BaseModel):
    city: str


REQUESTS = []


def _response(req):
    REQUESTS.append(req)
    text = json.dumps({"city": "Paris"})
    return Response.model_validate({
        "id": "resp_1", "object": "response", "created_at": 0, "status": "completed",
        "model": "gpt-4o-mini", "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        "output": [{"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]}],
        "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    })


@pytest.fixture
def default_route(monkeypatch, tmp_path):
    REQUESTS.clear()
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setattr(Responses, "create", lambda self, **req: _response(req))

    async def _acreate(self, **req):
        return _response(req)

    monkeypatch.setattr(AsyncResponses, "create", _acreate)


def _run(mode, agent):
    if mode == "chat":
        return agent.chat("Capital of France?", output_pydantic=Answer)
    if mode == "achat":
        return asyncio.run(agent.achat("Capital of France?", output_pydantic=Answer))
    return agent.start("Capital of France?", output_pydantic=Answer)


@pytest.mark.parametrize("mode", ["chat", "achat", "start"])
def test_output_pydantic_reaches_the_responses_api(default_route, mode):
    result = _run(mode, Agent(name="s", instructions="Answer briefly.", llm="gpt-4o-mini", output="silent"))

    assert REQUESTS, "the default route did not use the Responses API"
    fmt = (REQUESTS[-1].get("text") or {}).get("format") or {}
    assert fmt.get("type") == "json_schema", REQUESTS[-1].keys()
    assert "city" in json.dumps(fmt.get("schema"))
    assert isinstance(result, Answer) and result.city == "Paris"


def test_response_format_maps_to_responses_text_format():
    from praisonaiagents.llm.openai_client import OpenAIClient

    to_text = OpenAIClient._responses_text_format
    assert to_text({"type": "json_schema", "json_schema": {"name": "A", "schema": {"type": "object"},
                                                           "strict": True}}) == {
        "type": "json_schema", "name": "A", "schema": {"type": "object"}, "strict": True}
    assert to_text({"type": "json_object"}) == {"type": "json_object"}
    assert to_text(None) is None and to_text("json") is None
