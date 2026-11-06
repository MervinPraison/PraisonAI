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


def test_plain_keys_keep_their_filename(tmp_path):
    b = FileBackend(str(tmp_path))
    b.save("session-123_abc", {"x": 1})
    assert (tmp_path / "session-123_abc.json").exists()
