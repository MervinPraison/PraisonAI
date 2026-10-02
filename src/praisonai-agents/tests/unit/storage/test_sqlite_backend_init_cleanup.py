"""A failed backend constructor releases its real SQLite connection."""

import sqlite3

import pytest

from praisonaiagents.storage import sqlite as connector
from praisonaiagents.storage.backends import SQLiteBackend


@pytest.mark.parametrize("failure", ["reserved_name", "incompatible_schema"])
def test_constructor_closes_connection_after_schema_failure(tmp_path, monkeypatch, failure):
    path = str(tmp_path / "store.db")
    with sqlite3.connect(path) as seed:
        seed.execute("CREATE TABLE preserved (value TEXT)")
        seed.execute("INSERT INTO preserved VALUES ('original')")
        if failure == "incompatible_schema":
            seed.execute("CREATE TABLE praison_storage (wrong_column TEXT)")
    seed.close()
    opened = []
    original = connector.connect

    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(connector, "connect", connect)
    try:
        name = "sqlite_private" if failure == "reserved_name" else "praison_storage"
        with pytest.raises(sqlite3.OperationalError) as error:
            SQLiteBackend(db_path=path, table_name=name)
        expected = "reserved" if failure == "reserved_name" else "no such column"
        assert expected in str(error.value)
        assert len(opened) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            opened[0].execute("SELECT 1")
        with sqlite3.connect(path) as check:
            assert check.execute("SELECT value FROM preserved").fetchall() == [("original",)]
        check.close()
    finally:
        for conn in opened:
            conn.close()


def test_successful_constructor_keeps_connection_usable(tmp_path):
    backend = SQLiteBackend(db_path=str(tmp_path / "store.db"))
    try:
        backend.save("key", {"value": 1})
        assert backend.load("key") == {"value": 1}
    finally:
        backend.close()
