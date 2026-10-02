"""Session counts use the UTF-8 writer format, independent of host locale."""

import builtins
import json
from pathlib import Path

import pytest

from praisonaiagents.storage.base import BaseJSONStore, list_json_sessions


@pytest.fixture
def legacy_text_locale(monkeypatch, tmp_path):
    original_open = builtins.open

    def locale_open(file, mode="r", *args, **kwargs):
        if Path(file).parent == tmp_path and mode == "r" and not kwargs.get("encoding"):
            kwargs["encoding"] = "cp1252"
        return original_open(file, mode, *args, **kwargs)

    # Exercise real decoding with a deterministic Windows-style default locale.
    monkeypatch.setattr(builtins, "open", locale_open)


@pytest.mark.parametrize("field", ["iterations", "messages", "items", "jsonl"])
def test_utf8_session_counts_survive_legacy_locale(tmp_path, legacy_text_locale, field):
    values = ["丁 café 😀", "second"]
    suffix = ".jsonl" if field == "jsonl" else ".json"
    path = tmp_path / ("session" + suffix)
    if field == "jsonl":
        path.write_text("".join(json.dumps({"value": value}, ensure_ascii=False) + "\n" for value in values), encoding="utf-8")
    else:
        BaseJSONStore(path).save({field: values})
    before = path.read_bytes()

    sessions = list_json_sessions(tmp_path, suffix=suffix)

    assert len(sessions) == 1
    assert sessions[0].item_count == 2
    assert sessions[0].size_bytes == len(before)
    assert path.read_bytes() == before


@pytest.mark.parametrize("suffix", [".json", ".jsonl"])
@pytest.mark.parametrize("valid", [True, False])
def test_ascii_and_unreadable_files_keep_existing_behavior(tmp_path, legacy_text_locale, suffix, valid):
    path = tmp_path / ("session" + suffix)
    content = b'{"items":[1,2]}' if suffix == ".json" else b'{"value":1}\n{"value":2}\n'
    path.write_bytes(content if valid else b"\x81")
    before = path.read_bytes()
    sessions = list_json_sessions(tmp_path, suffix=suffix)
    assert len(sessions) == 1
    assert sessions[0].item_count == (2 if valid else 0)
    assert path.read_bytes() == before
