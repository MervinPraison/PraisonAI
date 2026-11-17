"""Regression tests for #6558: JSON-output instruction must not mutate the caller's prompt parts."""
import copy

import pytest
from pydantic import BaseModel

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient

INSTR = "Return ONLY a valid JSON object"


class Answer(BaseModel):
    value: int


def _parts():
    return [
        {"type": "text", "text": "Describe the pixel."},
        {"type": "image_url", "image_url": {"url": "https://example.com/p.png"}},
    ]


def _builders():
    llm = LLM(model="anthropic/claude-3-5-sonnet-20240620")
    client = OpenAIClient.__new__(OpenAIClient)
    return [
        ("litellm", lambda p, **kw: llm._build_messages(p, **kw)),
        ("openai", lambda p, **kw: client.build_messages(p, **kw)),
    ]


@pytest.mark.parametrize("kwargs", [{"output_pydantic": Answer}, {"output_json": Answer}])
@pytest.mark.parametrize("idx", [0, 1])
def test_caller_prompt_untouched_and_instruction_once(idx, kwargs):
    name, build = _builders()[idx]
    parts = _parts()
    snapshot = copy.deepcopy(parts)

    for _ in range(3):
        messages, original = build(parts, **kwargs)
        sent = messages[-1]["content"]
        assert sent[0]["text"].count(INSTR) == 1, name
        assert original == snapshot, name

    assert parts == snapshot, name
