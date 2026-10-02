"""Failed atomic saves preserve the target and remove their staging file."""

import json

import pytest

from praisonaiagents.storage.base import BaseJSONStore


@pytest.mark.parametrize("use_lock", [True, False])
@pytest.mark.parametrize("failure", ["circular", "encoding", "replace"])
def test_failed_save_removes_staging_file(tmp_path, monkeypatch, use_lock, failure):
    path = tmp_path / "store.json"
    original = b'{"saved": "original"}'
    path.write_bytes(original)
    neighbor = tmp_path / "unrelated.tmp"
    neighbor.write_bytes(b"keep")
    store = BaseJSONStore(path, use_file_lock=use_lock)
    payload = {"prefix": "written before failure"}
    if failure == "circular":
        payload["loop"] = payload
        error = ValueError
    elif failure == "encoding":
        payload["invalid"] = "\ud800"
        error = UnicodeEncodeError
    else:
        def fail_replace(*args):
            raise OSError("replace refused")

        monkeypatch.setattr("praisonaiagents.storage.base.os.replace", fail_replace)
        error = OSError

    with pytest.raises(error):
        store.save(payload)

    assert path.read_bytes() == original
    assert neighbor.read_bytes() == b"keep"
    assert set(tmp_path.iterdir()) == {path, neighbor}


@pytest.mark.parametrize("use_lock", [True, False])
def test_successful_save_replaces_target_without_staging_files(tmp_path, use_lock):
    path = tmp_path / "store.json"
    path.write_text('{"saved": "original"}', encoding="utf-8")
    store = BaseJSONStore(path, use_file_lock=use_lock)
    payload = {"saved": "你好 café 😀"}
    store.save(payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert set(tmp_path.iterdir()) == {path}
