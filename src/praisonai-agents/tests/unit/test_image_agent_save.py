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
    result = agent.edit(str(src), "make the cup blue", n=2)
    assert agent.sent["edit"]["n"] == 2
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


def test_save_nonzero_index(agent, tmp_path):
    src = tmp_path / "photo.png"
    src.write_bytes(b"png")
    result = agent.edit(str(src), "two takes", n=2)
    assert result.save(str(tmp_path / "b.gif"), index=1) == str(tmp_path / "b.gif")
    assert (tmp_path / "b.gif").read_bytes() == GIF


class _FakeHTTP:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]


def _url_response(url):
    return {"data": [{"b64_json": None, "url": url}]}


def test_save_downloads_url(agent, tmp_path, monkeypatch):
    import urllib.request

    seen = {}

    def fake_urlopen(url, timeout=None):
        seen.update(url=url, timeout=timeout)
        return _FakeHTTP(GIF)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(agent, "_litellm", lambda **kw: _url_response("https://example.com/i.gif"))
    agent.generate("cat").save(str(tmp_path / "u.gif"))
    assert (tmp_path / "u.gif").read_bytes() == GIF
    assert seen == {"url": "https://example.com/i.gif", "timeout": 30}


def test_save_rejects_non_http_url(agent, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_litellm", lambda **kw: _url_response("file:///etc/passwd"))
    with pytest.raises(ValueError, match="http"):
        agent.generate("x").save(str(tmp_path / "x.png"))
    assert not (tmp_path / "x.png").exists()


def test_save_rejects_oversized_download(agent, tmp_path, monkeypatch):
    import urllib.request
    from praisonaiagents.agent import _image_result

    monkeypatch.setattr(_image_result, "_MAX_DOWNLOAD_BYTES", 4)
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _FakeHTTP(b"123456"))
    monkeypatch.setattr(agent, "_litellm", lambda **kw: _url_response("https://example.com/big.png"))
    with pytest.raises(ValueError, match="maximum"):
        agent.generate("x").save(str(tmp_path / "big.png"))
    assert not (tmp_path / "big.png").exists()
