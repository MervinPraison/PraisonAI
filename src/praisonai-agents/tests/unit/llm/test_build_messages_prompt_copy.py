"""The JSON instruction must not be written into the caller's own prompt parts.

``LLM._build_messages`` (every litellm route) and ``OpenAIClient.build_messages``
(the OpenAI-compatible route) accept a multimodal prompt -- a list of content
parts -- together with ``output_json``/``output_pydantic``. They copied the list
but edited the caller's part dicts in place, so the instruction was appended to
the caller's prompt and once more on every later turn that reused it.
"""

import pytest
from pydantic import BaseModel

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient

INSTRUCTION = "Return ONLY a valid JSON object"

PARTS = [
    {"type": "text", "text": "Describe the pixel."},
    {"type": "image_url", "image_url": {"url": "https://example.com/p.png"}},
]


class Answer(BaseModel):
    value: int


def _llm_build(prompt):
    llm = LLM(model="anthropic/claude-3-5-sonnet-20240620")
    return llm._build_messages(prompt, "system", output_pydantic=Answer)


def _openai_build(prompt):
    client = OpenAIClient.__new__(OpenAIClient)
    return client.build_messages(prompt, "system", output_pydantic=Answer)


BUILDERS = [
    pytest.param(_llm_build, id="llm"),
    pytest.param(_openai_build, id="openai-client"),
]


def _text_of(message):
    content = message["content"]
    if isinstance(content, str):
        return content
    return next(part["text"] for part in content if part.get("type") == "text")


@pytest.mark.parametrize("build", BUILDERS)
def test_reused_prompt_is_not_modified(build):
    prompt = [dict(part) for part in PARTS]

    first, _ = build(prompt)
    second, _ = build(prompt)

    assert prompt == PARTS
    assert _text_of(first[-1]).count(INSTRUCTION) == 1
    assert _text_of(second[-1]).count(INSTRUCTION) == 1


@pytest.mark.parametrize("build", BUILDERS)
def test_instruction_goes_to_the_first_text_part_only(build):
    prompt = [
        {"type": "text", "text": "Describe the pixel."},
        {"type": "text", "text": "And the border."},
        {"type": "image_url", "image_url": {"url": "https://example.com/p.png"}},
    ]
    before = [dict(part) for part in prompt]

    messages, original_prompt = build(prompt)

    assert prompt == before
    assert original_prompt is prompt
    assert messages[-1]["content"][0]["text"].count(INSTRUCTION) == 1
    assert messages[-1]["content"][1]["text"] == "And the border."


@pytest.mark.parametrize("build", BUILDERS)
def test_non_dict_part_is_skipped_instead_of_raising(build):
    prompt = ["plain string part", {"type": "text", "text": "Describe the pixel."}]

    messages, _ = build(prompt)

    assert messages[-1]["content"][0] == "plain string part"
    assert messages[-1]["content"][1]["text"].count(INSTRUCTION) == 1


@pytest.mark.parametrize("build", BUILDERS)
def test_prompt_without_a_text_part_gets_no_instruction(build):
    prompt = [{"type": "image_url", "image_url": {"url": "https://example.com/p.png"}}]

    messages, _ = build(prompt)

    assert prompt == [{"type": "image_url", "image_url": {"url": "https://example.com/p.png"}}]
    assert INSTRUCTION not in repr(messages[-1]["content"])
