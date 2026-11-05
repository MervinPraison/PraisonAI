"""ImageAgent results expose .save() while keeping the raw response API (#6260)."""

import base64
import sys
import types

import pytest

from praisonaiagents import ImageAgent

GIF = b"GIF89a\x01\x00\x01\x00fake"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


def _response(*payloads):
    return types.SimpleNamespace(
        data=[types.SimpleNamespace(b64_json=base64.b64encode(p).decode(), url=None) for p in payloads],
        usage={"total_tokens": 5},
    )


@pytest.fixture
def agent(monkeypatch):
    agent = ImageAgent(llm="openai/gpt-image-2.6-flare", verbose=False)
    sent = {}

    def fake(name, payloads):
        def call(**kwargs):
            sent[name] = kwargs
            return _response(*payloads)
        return call

    monkeypatch.setattr(agent, "_litellm", fake("generate", [GIF]))
    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(
        image_edit=fake("edit", [SVG, GIF]),
        image_variation=fake("variation", [GIF]),
        get_llm_provider=lambda model: (model, "openai", None, None),
    ))
    agent.sent = sent
    return agent


def test_generate_save_writes_decoded_bytes(agent, tmp_path):
    out = agent.generate("A cat waving", output_format="gif", frame_count=8).save(str(tmp_path / "cat.gif"))
    assert open(out, "rb").read() == GIF
    assert agent.sent["generate"]["output_format"] == "gif"
    assert agent.sent["generate"]["frame_count"] == 8


def test_edit_save_index_and_raw_access(agent, tmp_path):
    src = tmp_path / "photo.png"
    src.write_bytes(b"png")
    result = agent.edit(str(src), "make the cup blue", markup="circle.png", n=2)
    assert agent.sent["edit"]["markup"] == "circle.png"
    assert len(result.images) == 2
    assert result.usage == {"total_tokens": 5}
    assert base64.b64decode(result.data[1].b64_json) == GIF
    result.save(str(tmp_path / "a.svg"))
    assert (tmp_path / "a.svg").read_bytes() == SVG


def test_variation_and_dict_response(agent, tmp_path, monkeypatch):
    src = tmp_path / "photo.png"
    src.write_bytes(b"png")
    assert agent.variation(str(src)).save(str(tmp_path / "v.gif"))
    monkeypatch.setattr(agent, "_litellm", lambda **kw: {"data": [{"b64_json": base64.b64encode(SVG).decode()}]})
    result = agent.generate("logo")
    assert result["data"][0]["b64_json"]
    result.save(str(tmp_path / "logo.svg"))
    assert (tmp_path / "logo.svg").read_bytes() == SVG


def test_save_without_image_data_raises(agent, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_litellm", lambda **kw: {"data": []})
    with pytest.raises(ValueError):
        agent.generate("nothing").save(str(tmp_path / "x.png"))
