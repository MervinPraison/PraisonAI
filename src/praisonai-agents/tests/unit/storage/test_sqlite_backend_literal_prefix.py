"""SQLite key enumeration uses literal, case-sensitive prefixes."""

import pytest

from praisonaiagents.storage.backends import SQLiteBackend


@pytest.mark.parametrize("prefix", ["task_", "task%", "Task", "", "ordinary", "键", "slash\\", "nul\x00"])
def test_list_keys_matches_literal_prefix(tmp_path, prefix):
    keys = ["task_one", "taskXone", "task%one", "TaskOne", "ordinary", "键一", "键二", "slash\\one", "slashXone", "nul\x00one", "nulXone"]
    store = SQLiteBackend(db_path=str(tmp_path / "storage.db"))
    try:
        for key in keys:
            store.save(key, {"key": key})
        assert store.list_keys(prefix) == sorted(key for key in keys if key.startswith(prefix))
        assert store.list_keys("missing") == []
    finally:
        store.close()
