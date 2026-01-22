"""
Tests for BaseJSONStore and BaseSessionInfo.

TDD: Tests for the DRY storage base implementation.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime

from praisonaiagents.storage.base import (
    BaseJSONStore,
    FileLock,
    list_json_sessions,
    cleanup_old_sessions,
)
from praisonaiagents.storage.models import BaseSessionInfo


class TestBaseSessionInfo:
    """Tests for BaseSessionInfo dataclass."""
    
    def test_session_info_creation(self):
        """Test creating a BaseSessionInfo."""
        info = BaseSessionInfo(
            session_id="test-123",
            path=Path("/tmp/test.json"),
            size_bytes=1024,
            created_at=datetime(2024, 1, 1),
            modified_at=datetime(2024, 1, 2),
            item_count=10,
        )
        
        assert info.session_id == "test-123"
        assert info.path == Path("/tmp/test.json")
        assert info.size_bytes == 1024
        assert info.item_count == 10
    
    def test_session_info_defaults(self):
        """Test BaseSessionInfo default values."""
        info = BaseSessionInfo(
            session_id="test",
            path=Path("/tmp/test.json"),
        )
        
        assert info.size_bytes == 0
        assert info.item_count == 0
        assert info.created_at is not None
        assert info.modified_at is not None
    
    def test_session_info_to_dict(self):
        """Test BaseSessionInfo.to_dict()."""
        info = BaseSessionInfo(
            session_id="test-123",
            path=Path("/tmp/test.json"),
            size_bytes=1024,
            item_count=5,
        )
        
        d = info.to_dict()
        
        assert d["session_id"] == "test-123"
        assert d["path"] == "/tmp/test.json"
        assert d["size_bytes"] == 1024
        assert d["item_count"] == 5
        assert "created_at" in d
        assert "modified_at" in d
    
    def test_session_info_from_dict(self):
        """Test BaseSessionInfo.from_dict()."""
        data = {
            "session_id": "test-123",
            "path": "/tmp/test.json",
            "size_bytes": 2048,
            "created_at": "2024-01-01T00:00:00",
            "modified_at": "2024-01-02T00:00:00",
            "item_count": 15,
        }
        
        info = BaseSessionInfo.from_dict(data)
        
        assert info.session_id == "test-123"
        assert info.path == Path("/tmp/test.json")
        assert info.size_bytes == 2048
        assert info.item_count == 15
    
    def test_session_info_from_path(self):
        """Test BaseSessionInfo.from_path()."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{"test": "data"}')
            temp_path = Path(f.name)
        
        try:
            info = BaseSessionInfo.from_path(temp_path)
            
            assert info.session_id == temp_path.stem
            assert info.path == temp_path
            assert info.size_bytes > 0
        finally:
            temp_path.unlink()


class TestFileLock:
    """Tests for FileLock."""
    
    def test_file_lock_acquire_release(self):
        """Test acquiring and releasing a file lock."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            lock_path = Path(str(temp_path) + ".lock")
            
            with FileLock(temp_path):
                # Lock should exist while held
                assert lock_path.exists()
            
            # Lock should be released
            assert not lock_path.exists()
        finally:
            temp_path.unlink()
    
    def test_file_lock_context_manager(self):
        """Test FileLock as context manager."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            with FileLock(temp_path) as lock:
                assert lock is not None
        finally:
            temp_path.unlink()


class TestBaseJSONStore:
    """Tests for BaseJSONStore."""
    
    def test_store_creation(self):
        """Test creating a BaseJSONStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            store = BaseJSONStore(store_path)
            
            assert store.storage_path == store_path
            assert store._data == {}
    
    def test_store_save_and_load(self):
        """Test saving and loading data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            store = BaseJSONStore(store_path)
            
            # Save data
            store.save({"key": "value", "count": 42})
            
            # Create new store and load
            store2 = BaseJSONStore(store_path)
            data = store2.load()
            
            assert data["key"] == "value"
            assert data["count"] == 42
    
    def test_store_exists(self):
        """Test exists() method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            
            store = BaseJSONStore(store_path, create_if_missing=True)
            assert not store.exists()  # File not created until save
            
            store.save({"test": True})
            assert store.exists()
    
    def test_store_clear(self):
        """Test clear() method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            store = BaseJSONStore(store_path)
            
            store.save({"key": "value"})
            store.clear()
            
            data = store.load()
            assert data == {}
    
    def test_store_delete(self):
        """Test delete() method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            store = BaseJSONStore(store_path)
            
            store.save({"key": "value"})
            assert store.exists()
            
            result = store.delete()
            assert result is True
            assert not store.exists()
    
    def test_store_thread_safety(self):
        """Test thread-safe operations."""
        import threading
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            store = BaseJSONStore(store_path)
            
            results = []
            
            def writer(n):
                for i in range(10):
                    with store._lock:
                        store._data[f"key_{n}_{i}"] = i
                        store._save()
                results.append(n)
            
            threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            assert len(results) == 3
    
    def test_store_custom_default_data(self):
        """Test subclass with custom default data."""
        class CustomStore(BaseJSONStore):
            def _default_data(self):
                return {"items": [], "version": 1}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            store = CustomStore(store_path)
            
            assert store._data == {"items": [], "version": 1}


class TestListJsonSessions:
    """Tests for list_json_sessions utility."""
    
    def test_list_empty_directory(self):
        """Test listing empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = list_json_sessions(Path(tmpdir))
            assert sessions == []
    
    def test_list_sessions(self):
        """Test listing sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create some session files
            for i in range(3):
                path = tmpdir / f"session_{i}.json"
                path.write_text(json.dumps({"iterations": [1, 2, 3]}))
            
            sessions = list_json_sessions(tmpdir)
            
            assert len(sessions) == 3
            for session in sessions:
                assert session.session_id.startswith("session_")
                assert session.item_count == 3
    
    def test_list_sessions_limit(self):
        """Test listing with limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            for i in range(10):
                path = tmpdir / f"session_{i}.json"
                path.write_text("{}")
            
            sessions = list_json_sessions(tmpdir, limit=5)
            
            assert len(sessions) == 5
    
    def test_list_jsonl_sessions(self):
        """Test listing JSONL sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            path = tmpdir / "trace.jsonl"
            path.write_text('{"event": 1}\n{"event": 2}\n{"event": 3}\n')
            
            sessions = list_json_sessions(tmpdir, suffix=".jsonl")
            
            assert len(sessions) == 1
            assert sessions[0].item_count == 3


class TestCleanupOldSessions:
    """Tests for cleanup_old_sessions utility."""
    
    def test_cleanup_empty_directory(self):
        """Test cleanup on empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            deleted = cleanup_old_sessions(Path(tmpdir))
            assert deleted == 0
    
    def test_cleanup_nonexistent_directory(self):
        """Test cleanup on nonexistent directory."""
        deleted = cleanup_old_sessions(Path("/nonexistent/path"))
        assert deleted == 0


class TestProtocolCompliance:
    """Test that storage classes comply with protocols."""
    
    def test_session_info_protocol_compliance(self):
        """Test that BaseSessionInfo complies with SessionInfoProtocol."""
        from praisonaiagents.storage.protocols import SessionInfoProtocol
        
        info = BaseSessionInfo(
            session_id="test",
            path=Path("/tmp/test.json"),
        )
        
        # Check required attributes
        assert hasattr(info, 'session_id')
        assert hasattr(info, 'path')
        assert hasattr(info, 'size_bytes')
        assert hasattr(info, 'created_at')
        assert hasattr(info, 'modified_at')
        assert hasattr(info, 'to_dict')
        
        # Check it's runtime checkable
        assert isinstance(info, SessionInfoProtocol)
    
    def test_json_store_protocol_compliance(self):
        """Test that BaseJSONStore complies with JSONStoreProtocol."""
        from praisonaiagents.storage.protocols import JSONStoreProtocol
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "test.json"
            store = BaseJSONStore(store_path)
            
            # Check required attributes
            assert hasattr(store, 'storage_path')
            assert hasattr(store, 'load')
            assert hasattr(store, 'save')
            assert hasattr(store, 'exists')
            
            # Check it's runtime checkable
            assert isinstance(store, JSONStoreProtocol)
