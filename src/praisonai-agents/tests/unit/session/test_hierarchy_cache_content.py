"""Hierarchical caches must describe the bytes actually loaded, not later stats."""

import os

import pytest

from praisonaiagents.session.hierarchy import HierarchicalSessionStore
from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.store import FileLock


def warm_reader(tmp_path):
    reader = HierarchicalSessionStore(session_dir=str(tmp_path))
    assert reader.add_message("parent", "user", "first")
    assert [message.content for message in reader.get_extended_session("parent").messages] == ["first"]
    return reader


@pytest.mark.parametrize("offset", [0, -1_000_000_000])
def test_cross_instance_write_with_unchanged_or_older_mtime(tmp_path, offset):
    reader = warm_reader(tmp_path)
    path = tmp_path / "parent.json"
    stamp = path.stat()
    writer = HierarchicalSessionStore(session_dir=str(tmp_path))
    assert writer.add_message("parent", "user", "second")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + offset))

    assert [message.content for message in reader.get_extended_session("parent").messages] == ["first", "second"]


def test_same_size_in_place_change_with_unchanged_mtime(tmp_path):
    reader = warm_reader(tmp_path)
    path = tmp_path / "parent.json"
    stamp = path.stat()
    path.write_bytes(path.read_bytes().replace(b'"first"', b'"other"'))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert path.stat().st_size == stamp.st_size

    assert reader.get_extended_session("parent").messages[0].content == "other"


def test_unchanged_bytes_reuse_parsed_session(tmp_path, monkeypatch):
    reader = warm_reader(tmp_path)
    cached = reader.get_extended_session("parent")

    def unexpected_parse(*args):
        pytest.fail("Unchanged bytes should not be parsed again")

    monkeypatch.setattr(reader, "_load_session_from_disk", unexpected_parse)
    assert reader.get_extended_session("parent") is cached
    assert reader._is_cache_valid("parent")


def test_invalidation_after_validation_reloads_instead_of_raising(tmp_path, monkeypatch):
    reader = warm_reader(tmp_path)
    original = reader._is_cache_valid

    def invalidate_after_check(session_id):
        valid = original(session_id)
        reader.invalidate_cache(session_id)
        return valid

    monkeypatch.setattr(reader, "_is_cache_valid", invalidate_after_check)
    assert reader.get_extended_session("parent").messages[0].content == "first"


def test_write_after_base_read_does_not_certify_old_payload(tmp_path, monkeypatch):
    reader = warm_reader(tmp_path)
    writer = HierarchicalSessionStore(session_dir=str(tmp_path))
    original = DefaultSessionStore._read_session_fresh
    fired = False

    def interleaved_read(self, session_id):
        nonlocal fired
        session = original(self, session_id)
        if self is reader and not fired:
            fired = True
            assert writer.add_message(session_id, "user", "second")
        return session

    monkeypatch.setattr(DefaultSessionStore, "_read_session_fresh", interleaved_read)
    assert [message.content for message in reader.get_extended_session("parent", force_reload=True).messages] == ["first"]
    assert fired
    assert [message.content for message in reader.get_extended_session("parent").messages] == ["first", "second"]


def test_transient_read_fallback_retries_after_recovery(tmp_path, monkeypatch):
    reader = warm_reader(tmp_path)
    writer = HierarchicalSessionStore(session_dir=str(tmp_path))
    assert writer.add_message("parent", "user", "second")
    original = reader._load_session_from_disk

    def unavailable(*args):
        raise OSError("temporary read failure")

    monkeypatch.setattr(reader, "_load_session_from_disk", unavailable)
    assert [message.content for message in reader.get_extended_session("parent", force_reload=True).messages] == ["first"]
    monkeypatch.setattr(reader, "_load_session_from_disk", original)

    assert [message.content for message in reader.get_extended_session("parent").messages] == ["first", "second"]


def test_corrupt_bytes_with_unchanged_mtime_are_quarantined(tmp_path):
    reader = warm_reader(tmp_path)
    path = tmp_path / "parent.json"
    stamp = path.stat()
    corrupt = b'{"messages": ['
    path.write_bytes(corrupt)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    assert reader.get_extended_session("parent").messages == []
    quarantined = list(tmp_path.glob("parent.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == corrupt


def test_cached_read_under_file_lock_contention_recovers(tmp_path):
    reader = warm_reader(tmp_path)
    cached = reader.get_extended_session("parent")
    reader.lock_timeout = 0.01
    with FileLock(str(tmp_path / "parent.json"), 1):
        assert reader.get_extended_session("parent") is cached
        with pytest.raises(OSError, match="Failed to acquire file lock"):
            reader.get_extended_session("parent", force_reload=True)
        with pytest.raises(OSError, match="Failed to acquire file lock"):
            reader.add_message("parent", "user", "must not be written")
    writer = HierarchicalSessionStore(session_dir=str(tmp_path))
    assert writer.add_message("parent", "user", "second")
    assert len(reader.get_extended_session("parent").messages) == 2


def test_uncached_read_does_not_fabricate_success_under_contention(tmp_path):
    writer = warm_reader(tmp_path)
    reader = HierarchicalSessionStore(session_dir=str(tmp_path), lock_timeout=0.01)
    with FileLock(writer._get_session_path("parent"), 1):
        with pytest.raises(OSError, match="Failed to acquire file lock"):
            reader.get_extended_session("parent")


@pytest.mark.parametrize("write", ["save", "modify"])
def test_local_write_reuses_written_parsed_session(tmp_path, monkeypatch, write):
    reader = warm_reader(tmp_path)
    if write == "save":
        cached = reader.get_extended_session("parent")
        cached.title = "écriture\nsecond line"
        assert reader._save_extended_session(cached)
    else:
        assert reader.add_message("parent", "user", "écriture\nsecond line")
        cached = reader._extended_cache["parent"]

    def unexpected_parse(*args):
        pytest.fail("A successful local write should reuse its parsed object")

    monkeypatch.setattr(reader, "_load_session_from_disk", unexpected_parse)
    assert reader.get_extended_session("parent") is cached
    assert reader._is_cache_valid("parent")
