"""The CLI image generator forwards a supported default and explicit overrides."""

import sys
from types import ModuleType

import pytest

from praisonai_code.cli.features.image import ImageGenerateHandler


@pytest.mark.parametrize(
    ("requested_model", "expected_model"),
    [
        (None, "gpt-image-2.5-flare"),
        ("gpt-image-2.5-flare", "gpt-image-2.5-flare"),
        ("dall-e-3", "dall-e-3"),
    ],
)
def test_image_generation_model_selection(monkeypatch, requested_model, expected_model):
    calls = []

    class FakeImageAgent:
        def __init__(self, **kwargs):
            calls.append(kwargs["llm"])

        def chat(self, prompt):
            return {"data": [{"b64_json": "dGVzdA=="}]}

    fake_agents = ModuleType("praisonaiagents")
    monkeypatch.setattr(fake_agents, "ImageAgent", FakeImageAgent, raising=False)
    monkeypatch.setitem(sys.modules, "praisonaiagents", fake_agents)
    monkeypatch.setattr(
        ImageGenerateHandler, "check_dependencies", lambda self: (True, "")
    )

    result = ImageGenerateHandler().execute(prompt="A blue square", llm=requested_model)

    assert calls == [expected_model]
    assert result == {"data": [{"b64_json": "dGVzdA=="}]}
