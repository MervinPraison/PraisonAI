"""Unreadable UTF-8 follows FileBackend's malformed-JSON load boundary."""

import pytest

from praisonaiagents.storage.backends import FileBackend


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
