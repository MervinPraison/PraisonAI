"""ImageAgent must not send the base Agent's chat default model to image APIs (#5944)."""

import sys
import types

import pytest

from praisonaiagents import ImageAgent


@pytest.mark.parametrize("model_kwargs,expected", [
    ({}, {"generate": "gpt-image-2.5-flare", "edit": "gpt-image-2.5-flare", "variation": "dall-e-2"}),
    ({"llm": "openai/gpt-image-1"}, dict.fromkeys(("generate", "edit", "variation"), "openai/gpt-image-1")),
    ({"model": "openai/gpt-image-1"}, dict.fromkeys(("generate", "edit", "variation"), "openai/gpt-image-1")),
])
def test_image_model_resolution(monkeypatch, tmp_path, model_kwargs, expected):
    calls = {}

    def record(name):
        def call(**kwargs):
            calls[name] = kwargs
            return {"data": []}
        return call

    agent = ImageAgent(instructions="Create images", verbose=False, **model_kwargs)
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


IMAGES_26_PARAMS = {"quality": "low", "frame_count": 4, "frame_duration_ms": 100,
                    "complexity": "low", "output_format": "gif"}


def test_generate_forwards_images_26_params(monkeypatch):
    calls = {}
    agent = ImageAgent(llm="gpt-image-2.6-flare", verbose=False)
    monkeypatch.setattr(agent, "_litellm", lambda **kw: calls.update(kw) or {"data": []})
    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(
        get_llm_provider=lambda model: (model, "openai", None, None)))
    agent.generate_image("x", **IMAGES_26_PARAMS)
    assert IMAGES_26_PARAMS.items() <= calls.items()


def test_edit_rejects_markup_instead_of_dropping_it(monkeypatch):
    called = []
    agent = ImageAgent(llm="gpt-image-2.5-flare", verbose=False)
    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(
        image_edit=lambda **kw: called.append(kw)))
    with pytest.raises(ValueError, match="markup"):
        agent.edit("photo.png", "make the circled cup blue", markup="markup.png")
    assert not called
