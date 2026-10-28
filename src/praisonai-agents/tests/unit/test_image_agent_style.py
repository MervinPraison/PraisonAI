"""OpenAI image calls must only forward style to models that accept it (dall-e-3)."""

import pytest

from praisonaiagents import ImageAgent


@pytest.mark.parametrize("llm,kwargs,expected", [
    ("openai/dall-e-2", {}, None),
    ("openai/gpt-image-1", {}, None),
    ("openai/gpt-image-1", {"style": "vivid"}, None),
    (None, {}, None),
    ("openai/dall-e-3", {}, None),
    ("openai/dall-e-3", {"style": "natural"}, "natural"),
    ("openai/dall-e-3", {"style": "vivid"}, "vivid"),
])
def test_style_forwarding(llm, kwargs, expected):
    agent = ImageAgent(llm=llm, verbose=False)
    received = {}

    def fake_image_generation(**call_kwargs):
        received.update(call_kwargs)
        return {"data": [{"url": "https://example.com/image.png"}]}

    agent._litellm = fake_image_generation
    try:
        agent.generate("A small green square icon", **kwargs)
        if expected is None:
            assert "style" not in received
        else:
            assert received["style"] == expected
    finally:
        agent.close()


@pytest.mark.parametrize("config,expected", [
    ({}, None),
    ({"style": "vivid"}, "vivid"),
])
def test_yaml_image_agent_style(config, expected):
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    agent = YAMLWorkflowParser()._create_image_agent("img", "openai/dall-e-3", config)
    try:
        assert agent.image_config.style == expected
    finally:
        agent.close()
