"""Salvaged JSON content and one corrupt file must not break session loading."""

from pathlib import Path

import pytest

from praisonaiagents.session.store import DefaultSessionStore, SessionMessage


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
