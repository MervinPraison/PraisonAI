"""ImageAgent must not send the base Agent's chat default model to image APIs (#5944)."""

import sys
import types

import pytest

from praisonaiagents import ImageAgent


@pytest.mark.parametrize("llm,expected", [
    (None, {"generate": "dall-e-3", "edit": "dall-e-2", "variation": "dall-e-2"}),
    ("openai/gpt-image-1", dict.fromkeys(("generate", "edit", "variation"), "openai/gpt-image-1")),
])
def test_image_model_resolution(monkeypatch, tmp_path, llm, expected):
    calls = {}

    def record(name):
        def call(**kwargs):
            calls[name] = kwargs
            return {"data": []}
        return call

    agent = ImageAgent(instructions="Create images", llm=llm, verbose=False)
    monkeypatch.setattr(agent, "_litellm", record("generate"))
    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(
        image_edit=record("edit"),
        image_variation=record("variation"),
        get_llm_provider=lambda model: (model, "openai", None, None),
    ))
    image = tmp_path / "source.png"
    image.write_bytes(b"png")

    agent.generate("A red circle")
    agent.edit(str(image), "Add clouds")
    agent.variation(str(image))

    assert {name: kwargs["model"] for name, kwargs in calls.items()} == expected
