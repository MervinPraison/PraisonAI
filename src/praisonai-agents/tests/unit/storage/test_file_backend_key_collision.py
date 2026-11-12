"""FileBackend must map distinct keys to distinct files (Issue #6266)."""
from praisonaiagents.storage.backends import FileBackend


def test_distinct_keys_do_not_share_a_file(tmp_path):
    b = FileBackend(str(tmp_path))
    b.save("alice@corp.com", {"secret": "A"})
    b.save("alice_corp.com", {"secret": "B"})

    assert b.load("alice@corp.com") == {"secret": "A"}
    assert b.load("alice_corp.com") == {"secret": "B"}
    assert b.list_keys() == ["alice@corp.com", "alice_corp.com"]

    assert b.delete("alice_corp.com")
    assert b.load("alice@corp.com") == {"secret": "A"}


def test_keys_cannot_escape_storage_dir(tmp_path):
    store = tmp_path / "store"
    b = FileBackend(str(store))
    b.save("../evil", {"x": 1})
    assert not (tmp_path / "evil.json").exists()
    assert b.list_keys() == ["../evil"]
    assert b.load("../evil") == {"x": 1}


def test_listed_long_key_is_not_an_alias(tmp_path):
    b = FileBackend(str(tmp_path))
    long_key = "a" * 200
    b.save(long_key, {"v": "A"})
    assert b.list_keys() == [long_key]
    from praisonaiagents.utils.atomic_io import safe_join
    import os
    alias = os.path.basename(safe_join(str(tmp_path), long_key, ".json"))[:-5]
    b.save(alias, {"v": "B"})
    assert b.load(long_key) == {"v": "A"}


def test_over_long_keys_save_and_round_trip(tmp_path):
    b = FileBackend(str(tmp_path))
    k1, k2 = "a" * 249 + "/", "a" * 249 + "?"
    b.save(k1, {"v": 1})
    b.save(k2, {"v": 2})
    assert all(len(p.name.encode()) <= 255 for p in tmp_path.iterdir())
    assert b.load(k1) == {"v": 1} and b.load(k2) == {"v": 2}
    listed = b.list_keys()
    assert len(listed) == 2
    assert sorted(b.load(k)["v"] for k in listed) == [1, 2]
    # The listed form keeps a readable prefix, so prefix searches find it.
    assert sorted(b.list_keys(prefix="aaaa")) == sorted(listed)
    assert all(k.startswith("a" * 100) for k in listed)
    # A literal key can never reach the hashed file form.
    b.save("%~" + "0" * 64 + "x", {"v": 3})
    assert b.load(k1) == {"v": 1}


def test_empty_suffix_dotted_keys_list_and_clear(tmp_path):
    b = FileBackend(str(tmp_path), suffix="")
    b.save("a.b", {"x": 1})
    assert b.list_keys() == ["a.b"]
    assert b.load("a.b") == {"x": 1}
    assert b.clear() == 1
    assert not any(tmp_path.iterdir())


def test_plain_keys_keep_their_filename(tmp_path):
    b = FileBackend(str(tmp_path))
    b.save("session-123_abc", {"x": 1})
    assert (tmp_path / "session-123_abc.json").exists()


def test_over_long_dotted_keys_round_trip_with_empty_suffix(tmp_path):
    for suffix in ("", ".json"):
        b = FileBackend(str(tmp_path / (suffix or "none")), suffix=suffix)
        key = ".x." + "é.?" * 120
        b.save(key, {"v": 1})
        (listed,) = b.list_keys(prefix=".x.")
        assert b.load(listed) == {"v": 1}
        assert b.clear() == 1


def test_legacy_named_records_stay_readable_and_migrate(tmp_path):
    # Files written by the pre-#6266 sanitiser ("@", ":", "." -> "_").
    (tmp_path / "alice_example_com.json").write_text('{"v": "A"}', encoding="utf-8")
    (tmp_path / "team_session_1.json").write_text('{"v": "T"}', encoding="utf-8")
    b = FileBackend(str(tmp_path))

    assert b.load("alice@example.com") == {"v": "A"}
    assert b.exists("team:session.1")
    assert b.load("team:session.1") == {"v": "T"}

    b.save("alice@example.com", {"v": "A2"})
    assert not (tmp_path / "alice_example_com.json").exists()
    assert b.load("alice@example.com") == {"v": "A2"}
    assert b.list_keys() == ["alice@example.com", "team_session_1"]

    assert b.delete("team:session.1")
    assert not b.exists("team:session.1")
    assert b.list_keys() == ["alice@example.com"]


def test_new_record_wins_over_legacy_file(tmp_path):
    b = FileBackend(str(tmp_path))
    b.save("a@b", {"v": "new"})
    (tmp_path / "a_b.json").write_text('{"v": "legacy"}', encoding="utf-8")
    assert b.load("a@b") == {"v": "new"}
    # With a new-format file present, save does not touch the legacy name.
    b.save("a@b", {"v": "new2"})
    assert b.load("a_b") == {"v": "legacy"}
    assert b.load("a@b") == {"v": "new2"}
    # Deleting the new record must not re-expose the legacy file.
    assert b.delete("a@b")
    assert not b.exists("a@b")
    assert b.load("a@b") is None
    assert b.load("a_b") == {"v": "legacy"}
    assert FileBackend(str(tmp_path)).load("a@b") is None
    assert b.list_keys() == ["a_b"]
    assert b.clear() == 1
    assert not any(tmp_path.iterdir())


def test_saving_one_key_never_deletes_another_keys_record(tmp_path):
    for first, second in (("a_b", "a@b"), ("a@b", "a_b")):
        d = tmp_path / first.replace("@", "at")
        b = FileBackend(str(d))
        b.save(first, {"v": first})
        b.save(second, {"v": second})
        assert FileBackend(str(d)).load(first) == {"v": first}
        assert FileBackend(str(d)).load(second) == {"v": second}


def test_deletion_markers_are_per_suffix_and_clear_is_robust(tmp_path):
    j, t = FileBackend(str(tmp_path)), FileBackend(str(tmp_path), suffix=".txt")
    j.save("a@b", {"v": "j"})
    (tmp_path / "a_b.json").write_text('{"v": "jl"}', encoding="utf-8")
    (tmp_path / "a_b.txt").write_text('{"v": "tl"}', encoding="utf-8")
    assert j.delete("a@b")
    assert j.load("a@b") is None
    assert t.load("a@b") == {"v": "tl"}  # the .json marker does not block .txt
    t.save("a@b", {"v": "t"})
    assert t.delete("a@b")
    (tmp_path / ".cache.deleted").mkdir()  # not a marker: clear() must not stop
    assert t.clear() == 0
    assert j.load("a@b") is None  # clearing .txt kept the .json marker
    assert j.clear() == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == [".cache.deleted"]
