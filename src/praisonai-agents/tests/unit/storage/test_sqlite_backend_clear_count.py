"""clear reports the rows its DELETE removes, including committed peer changes."""

import pytest

from praisonaiagents.storage.backends import SQLiteBackend


@pytest.mark.parametrize("change", ["insert", "delete", "none", "empty"])
def test_clear_counts_its_delete_with_a_second_connection(tmp_path, monkeypatch, change):
    path = str(tmp_path / "store.db")
    backend = SQLiteBackend(db_path=path)
    peer = SQLiteBackend(db_path=path)
    deleted_keys = []
    try:
        if change != "empty":
            backend.save("first", {"value": 1})
            backend.save("second", {"value": 2})
        conn = backend._get_conn()

        class Cursor:
            def __init__(self):
                self.cursor = conn.cursor()

            def execute(self, sql, *args):
                if sql.startswith("DELETE FROM"):
                    if change == "insert":
                        peer.save("late", {"value": 3})
                    elif change == "delete":
                        assert peer.delete("first")
                    deleted_keys.extend(peer.list_keys())
                return self.cursor.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self.cursor, name)

        class Connection:
            def cursor(self):
                return Cursor()

            def commit(self):
                conn.commit()

        monkeypatch.setattr(backend, "_get_conn", lambda: Connection())
        assert backend.clear() == len(deleted_keys)
        assert len(deleted_keys) == {"insert": 3, "delete": 1, "none": 2, "empty": 0}[change]
        assert peer.list_keys() == []
    finally:
        backend.close()
        peer.close()
