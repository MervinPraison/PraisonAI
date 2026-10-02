"""Compression commits must serialize with peer short-term writers."""

import threading

import pytest

from praisonaiagents.memory.file_memory import FileMemory


@pytest.mark.parametrize("max_items", [0, 1])
def test_peer_add_after_compression_reload_is_preserved(tmp_path, monkeypatch, max_items):
    memory = FileMemory(user_id="shared", base_path=str(tmp_path))
    memory.add_short_term("old-one")
    memory.add_short_term("old-two")
    peer = FileMemory(user_id="shared", base_path=str(tmp_path / "."))
    reloaded = threading.Event()
    resume = threading.Event()
    writer_started = threading.Event()
    writer_done = threading.Event()
    summarizing = threading.Event()
    errors = []
    original_read = memory._read_json

    def paused_read(path, default):
        data = original_read(path, default)
        if path == memory.short_term_file and summarizing.is_set():
            reloaded.set()
            assert resume.wait(5)
        return data

    def summarize(prompt):
        summarizing.set()
        return "summary"

    def compress():
        try:
            memory.compress(llm_func=summarize, max_items=max_items)
        except BaseException as exc:
            errors.append(exc)

    def add():
        writer_started.set()
        try:
            peer.add_short_term("concurrent")
        except BaseException as exc:
            errors.append(exc)
        finally:
            writer_done.set()

    monkeypatch.setattr(memory, "_read_json", paused_read)
    compressor = threading.Thread(target=compress)
    writer = threading.Thread(target=add)
    compressor.start()
    try:
        assert reloaded.wait(5)
        writer.start()
        assert writer_started.wait(5)
        # On the old implementation the peer finishes in this gap. With a
        # shared lock it waits until the compression transaction commits.
        writer_done.wait(0.5)
    finally:
        resume.set()
        compressor.join(5)
        if writer.ident is not None:
            writer.join(5)
    assert not compressor.is_alive() and not writer.is_alive()
    assert errors == []
    reopened = FileMemory(user_id="shared", base_path=str(tmp_path))
    expected = ["concurrent"] + (["old-two"] if max_items else [])
    assert [item.content for item in reopened.get_short_term()] == expected


def test_peer_delete_does_not_restore_compressed_snapshot(tmp_path):
    memory = FileMemory(user_id="shared", base_path=str(tmp_path))
    memory.add_short_term("old-one")
    retained_id = memory.add_short_term("old-two")
    peer = FileMemory(user_id="shared", base_path=str(tmp_path))
    memory.compress(max_items=1)
    assert peer.delete_short_term(retained_id)
    reopened = FileMemory(user_id="shared", base_path=str(tmp_path))
    assert reopened.get_short_term() == []


def test_compression_snapshot_includes_prior_peer_addition(tmp_path):
    memory = FileMemory(user_id="shared", base_path=str(tmp_path))
    memory.add_short_term("old")
    peer = FileMemory(user_id="shared", base_path=str(tmp_path))
    peer.add_short_term("new")
    summary = memory.compress(max_items=1)
    assert "old" in summary
    reopened = FileMemory(user_id="shared", base_path=str(tmp_path))
    assert [item.content for item in reopened.get_short_term()] == ["new"]
