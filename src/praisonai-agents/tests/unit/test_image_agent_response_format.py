"""OpenAI image calls must not forward the default response_format="url"."""

import pytest

from praisonaiagents import ImageAgent


@pytest.mark.parametrize("llm,kwargs,expected", [
    ("openai/dall-e-2", {}, None),
    ("openai/gpt-image-1", {}, None),
    ("openai/dall-e-3", {"response_format": "b64_json"}, "b64_json"),
    ("gemini/imagen-3.0-generate-002", {}, None),
])
def test_response_format_forwarding(llm, kwargs, expected):
    agent = ImageAgent(llm=llm, verbose=False)
    received = {}

    def fake_image_generation(**call_kwargs):
        received.update(call_kwargs)
        return {"data": [{"url": "https://example.com/image.png"}]}

    agent._litellm = fake_image_generation
    try:
        agent.generate("A minimal red circle icon", **kwargs)
        assert received.get("response_format") == expected
    finally:
        agent.close()
