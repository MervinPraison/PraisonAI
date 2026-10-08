"""
Tests for storage backends (FileBackend, SQLiteBackend).

Tests cover:
- Basic CRUD operations
- Thread safety
- Protocol compliance
- Backend switching
"""

import threading
from pathlib import Path

import pytest

from praisonaiagents.storage.backends import FileBackend, SQLiteBackend, get_backend
from praisonaiagents.storage.protocols import StorageBackendProtocol


class TestFileBackend:
    """Tests for FileBackend."""
    
    def test_file_backend_creation(self, tmp_path):
        """Test FileBackend can be created."""
        backend = FileBackend(storage_dir=str(tmp_path))
        assert backend.storage_dir == tmp_path
        assert backend.suffix == ".json"
    
    def test_file_backend_save_and_load(self, tmp_path):
        """Test save and load operations."""
        backend = FileBackend(storage_dir=str(tmp_path))
        
        data = {"key": "value", "number": 42}
        backend.save("test_key", data)
        
        loaded = backend.load("test_key")
        assert loaded == data

    def test_file_backend_load_invalid_utf8_returns_none(self, tmp_path, caplog):
        """Undecodable bytes should warn and return None, not raise (Issue #5566)."""
        import logging

        backend = FileBackend(storage_dir=str(tmp_path))

        for idx, raw in enumerate((b"\xff", b"\xe4\xb8", b"\xed\xa0\x80")):
            key = f"bad_{idx}"
            backend.save(key, {"message": "original"})
            file_path = Path(tmp_path) / f"{key}.json"
            file_path.write_bytes(raw)

            with caplog.at_level(logging.WARNING, logger="praisonaiagents.storage.backends"):
                caplog.clear()
                assert backend.load(key) is None
                # A warning is emitted identifying the failed key
                assert any(
                    rec.levelno == logging.WARNING and f"Failed to load {key}" in rec.getMessage()
                    for rec in caplog.records
                )
            # Original bytes are preserved (load is non-destructive)
            assert file_path.read_bytes() == raw

        # Valid neighboring keys still load
        backend.save("good", {"key": "value"})
        assert backend.load("good") == {"key": "value"}

    def test_file_backend_exists(self, tmp_path):
        """Test exists check."""
        backend = FileBackend(storage_dir=str(tmp_path))
        
        assert not backend.exists("nonexistent")
        
        backend.save("test_key", {"data": "value"})
        assert backend.exists("test_key")
    
    def test_file_backend_delete(self, tmp_path):
        """Test delete operation."""
        backend = FileBackend(storage_dir=str(tmp_path))
        
        backend.save("test_key", {"data": "value"})
        assert backend.exists("test_key")
        
        result = backend.delete("test_key")
        assert result is True
        assert not backend.exists("test_key")
        
        # Delete nonexistent
        result = backend.delete("nonexistent")
        assert result is False
    
    def test_file_backend_list_keys(self, tmp_path):
        """Test listing keys."""
        backend = FileBackend(storage_dir=str(tmp_path))
        
        backend.save("key1", {"data": 1})
        backend.save("key2", {"data": 2})
        backend.save("other", {"data": 3})
        
        all_keys = backend.list_keys()
        assert len(all_keys) == 3
        assert "key1" in all_keys
        assert "key2" in all_keys
        assert "other" in all_keys
        
        # With prefix
        filtered = backend.list_keys(prefix="key")
        assert len(filtered) == 2
        assert "key1" in filtered
        assert "key2" in filtered
    
    def test_file_backend_clear(self, tmp_path):
        """Test clearing all data."""
        backend = FileBackend(storage_dir=str(tmp_path))
        
        backend.save("key1", {"data": 1})
        backend.save("key2", {"data": 2})
        
        count = backend.clear()
        assert count == 2
        assert len(backend.list_keys()) == 0
    
    def test_file_backend_thread_safety(self, tmp_path):
        """Test thread-safe operations."""
        backend = FileBackend(storage_dir=str(tmp_path))
        errors = []
        
        def writer(n):
            try:
                for i in range(10):
                    backend.save(f"key_{n}_{i}", {"thread": n, "iteration": i})
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(backend.list_keys()) == 50
    
    def test_file_backend_protocol_compliance(self, tmp_path):
        """Test FileBackend implements StorageBackendProtocol."""
        backend = FileBackend(storage_dir=str(tmp_path))
        assert isinstance(backend, StorageBackendProtocol)

    @pytest.mark.parametrize("pretty", [True, False])
    def test_file_backend_save_cleans_tmp_on_serialization_error(self, tmp_path, pretty):
        """Serialization failures must not leave partial .tmp staging files."""
        backend = FileBackend(storage_dir=str(tmp_path), pretty=pretty)
        backend.save("good", {"value": 1})

        circular = {}
        circular["self"] = circular
        with pytest.raises(ValueError):
            backend.save("circular", circular)

        with pytest.raises(TypeError):
            backend.save("tuple_key", {("a", "b"): 1})

        with pytest.raises((ValueError, TypeError)):
            backend.save("good", circular)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []
        assert backend.load("good") == {"value": 1}
        assert not backend.exists("circular")
        assert not backend.exists("tuple_key")


class TestSQLiteBackend:
    """Tests for SQLiteBackend."""
    
    def test_sqlite_backend_creation(self, tmp_path):
        """Test SQLiteBackend can be created."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        assert Path(backend.db_path) == db_path
    
    def test_sqlite_backend_save_and_load(self, tmp_path):
        """Test save and load operations."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        
        data = {"key": "value", "number": 42}
        backend.save("test_key", data)
        
        loaded = backend.load("test_key")
        assert loaded == data
    
    def test_sqlite_backend_exists(self, tmp_path):
        """Test exists check."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        
        assert not backend.exists("nonexistent")
        
        backend.save("test_key", {"data": "value"})
        assert backend.exists("test_key")
    
    def test_sqlite_backend_delete(self, tmp_path):
        """Test delete operation."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        
        backend.save("test_key", {"data": "value"})
        assert backend.exists("test_key")
        
        result = backend.delete("test_key")
        assert result is True
        assert not backend.exists("test_key")
        
        # Delete nonexistent
        result = backend.delete("nonexistent")
        assert result is False
    
    def test_sqlite_backend_list_keys(self, tmp_path):
        """Test listing keys."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        
        backend.save("key1", {"data": 1})
        backend.save("key2", {"data": 2})
        backend.save("other", {"data": 3})
        
        all_keys = backend.list_keys()
        assert len(all_keys) == 3
        assert "key1" in all_keys
        assert "key2" in all_keys
        assert "other" in all_keys
        
        # With prefix
        filtered = backend.list_keys(prefix="key")
        assert len(filtered) == 2
        assert "key1" in filtered
        assert "key2" in filtered
    
    def test_sqlite_backend_clear(self, tmp_path):
        """Test clearing all data."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        
        backend.save("key1", {"data": 1})
        backend.save("key2", {"data": 2})
        
        count = backend.clear()
        assert count == 2
        assert len(backend.list_keys()) == 0
    
    def test_sqlite_backend_upsert(self, tmp_path):
        """Test that save updates existing keys."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        
        backend.save("key1", {"version": 1})
        backend.save("key1", {"version": 2})
        
        loaded = backend.load("key1")
        assert loaded["version"] == 2
        assert len(backend.list_keys()) == 1
    
    def test_sqlite_backend_thread_safety(self, tmp_path):
        """Test thread-safe operations."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        errors = []
        
        def writer(n):
            try:
                for i in range(10):
                    backend.save(f"key_{n}_{i}", {"thread": n, "iteration": i})
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(backend.list_keys()) == 50
    
    def test_sqlite_backend_protocol_compliance(self, tmp_path):
        """Test SQLiteBackend implements StorageBackendProtocol."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        assert isinstance(backend, StorageBackendProtocol)
    
    def test_sqlite_backend_close(self, tmp_path):
        """Test closing the backend."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        
        backend.save("key1", {"data": 1})
        backend.close()
        
        # Should be able to reopen
        backend2 = SQLiteBackend(db_path=str(db_path))
        loaded = backend2.load("key1")
        assert loaded["data"] == 1
    
    def test_sqlite_backend_schema_failure_closes_connection(self, tmp_path):
        """Schema init failure must close the opened connection and re-raise."""
        import sqlite3

        db_path = tmp_path / "test.db"

        # Pre-create a conflicting table WITHOUT the expected ``key`` column so
        # that index creation in _create_table() raises. The connection is
        # opened during __init__; the cleanup path must close it and re-raise.
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE praison_storage (other TEXT)")
        conn.commit()
        conn.close()

        captured = {}
        original_create = SQLiteBackend._create_table

        def tracking_create(self):
            captured["backend"] = self
            return original_create(self)

        SQLiteBackend._create_table = tracking_create
        try:
            with pytest.raises(sqlite3.OperationalError):
                SQLiteBackend(db_path=str(db_path))
        finally:
            SQLiteBackend._create_table = original_create

        backend = captured["backend"]
        # Connection must have been closed by the cleanup path.
        assert getattr(backend._local, "conn", None) is None

        # Existing data/table must survive untouched (no removal/replacement).
        verify = sqlite3.connect(str(db_path))
        tables = verify.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='praison_storage'"
        ).fetchall()
        verify.close()
        assert tables == [("praison_storage",)]

    @pytest.mark.parametrize("table_name", ["select", "123", "9table", "praison_storage"])
    def test_sqlite_backend_keyword_and_digit_table_names(self, tmp_path, table_name):
        """Validator-accepted names that are SQL keywords or start with a digit
        must work across schema creation and all CRUD operations (Issue #5569)."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path), table_name=table_name)

        # save / upsert
        backend.save("key1", {"version": 1})
        backend.save("key1", {"version": 2})
        assert backend.load("key1")["version"] == 2

        # exists
        assert backend.exists("key1")
        assert not backend.exists("missing")

        # list_keys (full + prefix)
        backend.save("key2", {"data": 2})
        backend.save("other", {"data": 3})
        assert backend.list_keys() == ["key1", "key2", "other"]
        assert backend.list_keys(prefix="key") == ["key1", "key2"]

        # delete
        assert backend.delete("other") is True
        assert not backend.exists("other")

        # clear
        assert backend.clear() == 2
        assert backend.list_keys() == []

    def test_sqlite_backend_reopen_with_auto_create_false(self, tmp_path):
        """A keyword table name persists and reopens with auto_create=False."""
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path), table_name="select")
        backend.save("key1", {"data": 1})
        backend.close()

        backend2 = SQLiteBackend(
            db_path=str(db_path), table_name="select", auto_create=False
        )
        assert backend2.load("key1")["data"] == 1

    def test_sqlite_backend_separate_tables_same_db(self, tmp_path):
        """Quoted identifiers keep distinct tables isolated in one DB file."""
        db_path = tmp_path / "test.db"
        t1 = SQLiteBackend(db_path=str(db_path), table_name="select")
        t2 = SQLiteBackend(db_path=str(db_path), table_name="praison_storage")

        t1.save("shared", {"from": "select"})
        t2.save("shared", {"from": "praison_storage"})

        assert t1.load("shared")["from"] == "select"
        assert t2.load("shared")["from"] == "praison_storage"

    def test_sqlite_backend_invalid_table_name_rejected(self, tmp_path):
        """Names with disallowed characters are still rejected by the validator."""
        db_path = tmp_path / "test.db"
        with pytest.raises(ValueError):
            SQLiteBackend(db_path=str(db_path), table_name="bad name")
        with pytest.raises(ValueError):
            SQLiteBackend(db_path=str(db_path), table_name='drop";')


class TestGetBackend:
    """Tests for get_backend factory function."""
    
    def test_get_file_backend(self, tmp_path):
        """Test getting file backend."""
        backend = get_backend("file", storage_dir=str(tmp_path))
        assert isinstance(backend, FileBackend)
    
    def test_get_sqlite_backend(self, tmp_path):
        """Test getting sqlite backend."""
        db_path = tmp_path / "test.db"
        backend = get_backend("sqlite", db_path=str(db_path))
        assert isinstance(backend, SQLiteBackend)
    
    def test_get_unknown_backend(self):
        """Test getting unknown backend raises error."""
        try:
            get_backend("unknown")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unknown backend type" in str(e)


class TestBaseJSONStoreWithBackend:
    """Tests for BaseJSONStore with different backends."""
    
    def test_base_json_store_with_file_backend(self, tmp_path):
        """Test BaseJSONStore with FileBackend."""
        from praisonaiagents.storage.base import BaseJSONStore
        
        backend = FileBackend(storage_dir=str(tmp_path))
        store = BaseJSONStore(
            storage_path=tmp_path / "test.json",
            backend=backend,
        )
        
        store.save({"items": [1, 2, 3]})
        loaded = store.load()
        assert loaded["items"] == [1, 2, 3]
    
    def test_base_json_store_with_sqlite_backend(self, tmp_path):
        """Test BaseJSONStore with SQLiteBackend."""
        from praisonaiagents.storage.base import BaseJSONStore
        
        db_path = tmp_path / "test.db"
        backend = SQLiteBackend(db_path=str(db_path))
        store = BaseJSONStore(
            storage_path=tmp_path / "test.json",
            backend=backend,
        )
        
        store.save({"items": [1, 2, 3]})
        loaded = store.load()
        assert loaded["items"] == [1, 2, 3]
    
    def test_base_json_store_backend_switching(self, tmp_path):
        """Test switching between backends preserves data."""
        from praisonaiagents.storage.base import BaseJSONStore
        
        # Save with file backend
        file_backend = FileBackend(storage_dir=str(tmp_path / "files"))
        store1 = BaseJSONStore(
            storage_path=tmp_path / "test.json",
            backend=file_backend,
        )
        store1.save({"data": "from_file"})
        
        # Save with sqlite backend
        db_path = tmp_path / "test.db"
        sqlite_backend = SQLiteBackend(db_path=str(db_path))
        store2 = BaseJSONStore(
            storage_path=tmp_path / "test.json",
            backend=sqlite_backend,
        )
        store2.save({"data": "from_sqlite"})
        
        # Verify each backend has its own data
        loaded1 = store1.load()
        loaded2 = store2.load()
        
        assert loaded1["data"] == "from_file"
        assert loaded2["data"] == "from_sqlite"
