"""Unreadable UTF-8 follows FileBackend's malformed-JSON load boundary."""

import pytest

from praisonaiagents.storage.backends import FileBackend
from praisonaiagents.storage.base import BaseJSONStore


@pytest.mark.parametrize("payload", [b"\xff", b'{"message":"\xe2\x82', b'{"message":"\xed\xa0\x80"}', b"{invalid"])
def test_load_reports_unreadable_file_without_modifying_it(tmp_path, caplog, payload):
    backend = FileBackend(storage_dir=str(tmp_path))
    backend.save("bad", {"message": "original"})
    backend.save("valid", {"message": "neighbor"})
    path = tmp_path / "bad.json"
    path.write_bytes(payload)

    assert backend.load("bad") is None
    assert "Failed to load bad" in caplog.text
    assert path.read_bytes() == payload
    assert backend.exists("bad")
    assert backend.load("valid") == {"message": "neighbor"}


def test_load_preserves_valid_unicode_and_missing_file_behavior(tmp_path, caplog):
    backend = FileBackend(storage_dir=str(tmp_path))
    data = {"message": "你好 café 😀"}
    backend.save("valid", data)
    assert backend.load("valid") == data
    assert backend.load("missing") is None
    assert not caplog.records


@pytest.mark.parametrize("payload", [b"\xff", b"{invalid"])
def test_default_store_save_cannot_overwrite_unreadable_backend_record(tmp_path, payload):
    backend = FileBackend(storage_dir=str(tmp_path))
    path = tmp_path / "session.json"
    path.write_bytes(payload)
    store = BaseJSONStore("session.json", backend=backend)
    assert store.load() == {}
    with pytest.raises(OSError, match="unreadable record"):
        store.save({"iterations": [{"result": "new"}]})
    assert path.read_bytes() == payload
    assert not list(tmp_path.glob("*.tmp"))
    backend.save("neighbor", {"message": "valid"})
    assert backend.load("neighbor") == {"message": "valid"}


def test_write_protection_uses_file_identity_and_clears_after_successful_read(tmp_path):
    backend = FileBackend(storage_dir=str(tmp_path))
    path = tmp_path / "alias_key.json"
    path.write_bytes(b"\xff")
    assert backend.load("alias/key") is None
    with pytest.raises(OSError, match="unreadable record"):
        backend.save("alias_key", {"message": "new"})
    path.write_text('{"message":"repaired"}', encoding="utf-8")
    assert backend.load("alias_key") == {"message": "repaired"}
    backend.save("alias/key", {"message": "updated"})
    assert backend.load("alias_key") == {"message": "updated"}


def test_deleted_unreadable_record_can_be_created_again(tmp_path):
    backend = FileBackend(storage_dir=str(tmp_path))
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff")
    assert backend.load("bad") is None
    assert backend.delete("bad")
    backend.save("bad", {"message": "new"})
    assert backend.load("bad") == {"message": "new"}
