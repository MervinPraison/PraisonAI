"""Accepted table identifiers work throughout the SQLite backend API."""

import pytest

from praisonaiagents.storage.backends import SQLiteBackend


@pytest.mark.parametrize("name", ["select", "123", "9table", "praison_storage"])
def test_accepted_table_name_supports_crud_and_reopen(tmp_path, name):
    path = str(tmp_path / "store.db")
    # Retain the object even if construction raises, so its opened connection
    # can be closed before Windows temporary-directory teardown.
    backend = SQLiteBackend.__new__(SQLiteBackend)
    neighbor = None
    try:
        backend.__init__(db_path=path, table_name=name)
        assert backend.table_name == name
        neighbor = SQLiteBackend(db_path=path, table_name="neighbor")
        neighbor.save("untouched", {"value": "neighbor"})
        assert not backend.exists("missing")
        assert backend.load("missing") is None
        backend.save("alpha", {"value": 1})
        backend.save("beta", {"value": 2})
        backend.save("alpha", {"value": 3})
        assert backend.exists("alpha")
        assert backend.load("alpha") == {"value": 3}
        assert backend.list_keys() == ["alpha", "beta"]
        assert backend.list_keys("al") == ["alpha"]
        backend.close()
        backend = SQLiteBackend(db_path=path, table_name=name, auto_create=False)
        assert backend.load("alpha") == {"value": 3}
        assert backend.delete("alpha")
        assert not backend.delete("alpha")
        assert backend.clear() == 1
        assert backend.clear() == 0
        assert backend.list_keys() == []
        assert neighbor.load("untouched") == {"value": "neighbor"}
    finally:
        backend.close()
        if neighbor is not None:
            neighbor.close()


@pytest.mark.parametrize("name", ["table\n", "tab\nle", "\ntable", "select ", " select", "ta ble"])
def test_rejects_whitespace_in_table_name(tmp_path, name):
    path = str(tmp_path / "store.db")
    with pytest.raises(ValueError):
        SQLiteBackend(db_path=path, table_name=name)
