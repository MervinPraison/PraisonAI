"""Salvaged JSON content and one corrupt file must not break session loading."""

from pathlib import Path
import json

import pytest

from praisonaiagents.session.store import DefaultSessionStore, SessionMessage


@pytest.mark.parametrize("incoming,expected", [
    ({"b": [2], "a": [1]}, 1),
    ({"a": [[1]], "b": [2]}, 2),
])
def test_spill_key_preserves_object_order_and_array_structure(tmp_path, monkeypatch, incoming, expected):
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    monkeypatch.setattr(store, "_spill_dir", lambda: str(tmp_path / "spill"))
    assert store.add_message("s", "user", {"a": [1], "b": [2]})
    timestamp = store.get_session("s").messages[0].timestamp
    spill = store._spill("s", [SessionMessage("user", incoming, timestamp=timestamp)])

    assert len(store.get_chat_history("s")) == expected
    assert not Path(spill).exists()


@pytest.mark.parametrize("existing", [False, True])
def test_deep_json_content_does_not_abort_recovery(tmp_path, monkeypatch, existing):
    directory = tmp_path / "sessions"
    store = DefaultSessionStore(session_dir=str(directory), retention="keep_all")
    monkeypatch.setattr(store, "_spill_dir", lambda: str(tmp_path / "spill"))
    # Valid JSON whose recursive key conversion exceeded Python's stack limit.
    content = json.loads("[" * 500 + "0" + "]" * 500)
    message = SessionMessage(role="user", content=content, timestamp=123)
    if existing:
        assert store.add_message("s", "user", content)
        message = store.get_session("s").messages[0]
    spill = store._spill("s", [message])
    neighbor = store._spill("s", [SessionMessage("user", "neighbor", timestamp=124)])

    history = store.get_chat_history("s")

    assert len(history) == 2
    assert json.dumps(history[0]["content"]) == json.dumps(content)
    assert history[1]["content"] == "neighbor"
    assert not Path(spill).exists()
    assert not Path(neighbor).exists()
    reopened = DefaultSessionStore(session_dir=str(directory), retention="keep_all")
    assert json.dumps(reopened.get_chat_history("s")) == json.dumps(history)


def test_json_parse_recursion_failure_preserves_spill_and_recovers_neighbor(tmp_path, monkeypatch):
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    directory = tmp_path / "spill"
    monkeypatch.setattr(store, "_spill_dir", lambda: str(directory))
    neighbor = store._spill("s", [SessionMessage("user", "neighbor", timestamp=124)])
    bad = directory / "s.000.json"
    raw = json.dumps({"session_id": "s", "messages": []})
    bad.write_text(raw, encoding="utf-8")
    load = json.load

    def decoder(file, *args, **kwargs):
        if Path(file.name) == bad:
            raise RecursionError("decoder nesting limit")
        return load(file, *args, **kwargs)

    monkeypatch.setattr(json, "load", decoder)

    assert store.get_chat_history("s") == [{"role": "user", "content": "neighbor"}]
    assert bad.read_text(encoding="utf-8") == raw
    assert not Path(neighbor).exists()


@pytest.mark.parametrize("existing", [False, True])
def test_structured_content_recovers_once(tmp_path, monkeypatch, existing):
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    monkeypatch.setattr(store, "_spill_dir", lambda: str(tmp_path / "spill"))
    content = [{"type": "text", "text": "hello"}, {
        "type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="},
    }]
    if existing:
        assert store.add_message("s", "user", content)
        msg = store.get_session("s").messages[0]
    else:
        msg = SessionMessage(role="user", content=content, timestamp=123)
    spill = store._spill("s", [msg])
    assert spill is not None
    history = store.get_chat_history("s")
    assert history == [{"role": "user", "content": content}]
    assert not Path(spill).exists()
    assert store.get_chat_history("s") == history


def test_invalid_utf8_spill_does_not_block_valid_neighbor(tmp_path, monkeypatch):
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    directory = tmp_path / "spill"
    monkeypatch.setattr(store, "_spill_dir", lambda: str(directory))
    spill = store._spill("s", [SessionMessage(role="user", content="recovered", timestamp=123)])
    bad = directory / "s.000.json"
    bad.write_bytes(b"\xff\xfeinvalid")
    assert store.get_chat_history("s") == [{"role": "user", "content": "recovered"}]
    assert not Path(spill).exists()
    assert bad.read_bytes() == b"\xff\xfeinvalid"


@pytest.mark.parametrize("shape", ["object", "array"])
@pytest.mark.parametrize("previous,incoming", [(True, 1), (1, 1.0), (False, 0), (True, True)])
def test_spill_identity_preserves_json_scalar_types(tmp_path, monkeypatch, shape, previous, incoming):
    directory = tmp_path / "sessions"
    store = DefaultSessionStore(session_dir=str(directory))
    monkeypatch.setattr(store, "_spill_dir", lambda: str(tmp_path / "spill"))

    def content(value):
        return {"nested": {"value": value}} if shape == "object" else [{"value": value}]

    assert store.add_message("s", "user", content(previous))
    timestamp = store.get_session("s").messages[0].timestamp
    spill = store._spill("s", [SessionMessage(role="user", content=content(incoming), timestamp=timestamp)])
    assert spill is not None
    history = store.get_chat_history("s")
    expected = 1 if type(previous) is type(incoming) else 2
    assert len(history) == expected

    reopened = DefaultSessionStore(session_dir=str(directory))
    persisted = reopened.get_chat_history("s")
    assert len(persisted) == expected
    values = [m["content"]["nested"]["value"] if shape == "object" else m["content"][0]["value"] for m in persisted]
    assert [type(value) for value in values] == ([type(previous)] if expected == 1 else [type(previous), type(incoming)])
    assert not Path(spill).exists()
