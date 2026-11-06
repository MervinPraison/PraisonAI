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
