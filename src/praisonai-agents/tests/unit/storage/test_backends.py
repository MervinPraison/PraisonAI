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
