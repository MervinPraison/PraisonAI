"""Enumeration and clearing honor the complete configured filename suffix."""

import pytest

from praisonaiagents.storage.backends import FileBackend


@pytest.mark.parametrize("suffix", [".data.json", "record", ".json", ""])
@pytest.mark.parametrize("operation", ["list", "clear"])
def test_configured_suffix_selects_saved_records(tmp_path, suffix, operation):
    store = FileBackend(storage_dir=str(tmp_path), suffix=suffix)
    for key in ("session_one", "session_two", "other"):
        store.save(key, {"key": key})
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("keep", encoding="utf-8")
    directory = tmp_path / ("directory" + suffix)
    directory.mkdir()
    assert store.exists("session_one")
    assert store.load("session_one") == {"key": "session_one"}
    if operation == "list":
        assert store.list_keys() == ["other", "session_one", "session_two"]
        assert store.list_keys("session_") == ["session_one", "session_two"]
        for key in store.list_keys():
            assert store.load(key) == {"key": key}
    else:
        assert store.clear() == 3
        assert not store.exists("session_one")
        assert store.list_keys() == []
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert directory.is_dir()
