"""
Test suite for GNAP (Git-Native Agent Protocol) Storage Backend.

Tests the implementation of StorageBackendProtocol using git for task persistence.
"""

import json
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
import pytest

from gnap_storage_backend import GNAPStorageBackend


class TestGNAPStorageBackend:
    """Test cases for GNAP storage backend."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = GNAPStorageBackend(
            repo_path=self.temp_dir,
            auto_commit=True
        )
    
    def teardown_method(self):
        """Clean up test environment."""
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_save_and_load(self):
        """Test basic save and load operations."""
        test_data = {
            "id": "task_001",
            "status": "pending",
            "agent": "test_agent",
            "description": "Test task"
        }
        
        # Save data
        self.backend.save("task_001", test_data)
        
        # Load data
        loaded_data = self.backend.load("task_001")
        
        assert loaded_data is not None
        assert loaded_data["id"] == "task_001"
        assert loaded_data["status"] == "pending"
        assert loaded_data["agent"] == "test_agent"
        
        # Ensure GNAP metadata is not included in loaded data
        assert "_gnap" not in loaded_data
    
    def test_exists(self):
        """Test exists method."""
        test_data = {"id": "task_002", "status": "pending"}
        
        # Should not exist initially
        assert not self.backend.exists("task_002")
        
        # Save and check exists
        self.backend.save("task_002", test_data)
        assert self.backend.exists("task_002")
    
    def test_delete(self):
        """Test delete operation."""
        test_data = {"id": "task_003", "status": "pending"}
        
        # Save data
        self.backend.save("task_003", test_data)
        assert self.backend.exists("task_003")
        
        # Delete data
        result = self.backend.delete("task_003")
        assert result is True
        assert not self.backend.exists("task_003")
        
        # Try deleting non-existent key
        result = self.backend.delete("nonexistent")
        assert result is False
    
    def test_list_keys(self):
        """Test listing keys."""
        # Initially empty
        keys = self.backend.list_keys()
        assert len(keys) == 0
        
        # Add some tasks
        test_tasks = [
            {"id": "task_a", "status": "pending"},
            {"id": "task_b", "status": "running"},
            {"id": "prefix_task_c", "status": "completed"}
        ]
        
        for i, task in enumerate(test_tasks):
            self.backend.save(f"task_{chr(97 + i)}", task)
        
        # Test listing all keys
        keys = self.backend.list_keys()
        assert len(keys) == 3
        assert "task_a" in keys
        assert "task_b" in keys
        
        # Test prefix filtering
        prefix_keys = self.backend.list_keys(prefix="task_")
        assert "task_a" in prefix_keys
        assert "task_b" in prefix_keys
    
    def test_gnap_folder_structure(self):
        """Test that .gnap folder structure is created correctly."""
        gnap_path = Path(self.temp_dir) / ".gnap"
        
        assert gnap_path.exists()
        assert (gnap_path / "tasks").exists()
        assert (gnap_path / "agents").exists()
        assert (gnap_path / "status").exists()
        assert (gnap_path / "config.json").exists()
        
        # Check config.json content
        with open(gnap_path / "config.json", "r") as f:
            config = json.load(f)
        
        assert config["version"] == "1.0"
        assert "created_at" in config
        assert config["description"] == "GNAP (Git-Native Agent Protocol) task storage"
    
    def test_git_initialization(self):
        """Test that git repository is initialized."""
        git_path = Path(self.temp_dir) / ".git"
        assert git_path.exists()
    
    def test_task_file_creation(self):
        """Test that task files are created in correct location."""
        test_data = {"id": "file_test", "status": "pending"}
        
        self.backend.save("file_test", test_data)
        
        task_file = Path(self.temp_dir) / ".gnap" / "tasks" / "file_test.json"
        assert task_file.exists()
        
        # Check file content includes GNAP metadata
        with open(task_file, "r") as f:
            saved_data = json.load(f)
        
        assert "_gnap" in saved_data
        assert saved_data["_gnap"]["key"] == "file_test"
        assert saved_data["_gnap"]["version"] == "1.0"
        assert "saved_at" in saved_data["_gnap"]
    
    def test_status_summary(self):
        """Test status summary functionality."""
        # Add tasks with different statuses
        tasks = [
            {"id": "task1", "status": "pending"},
            {"id": "task2", "status": "pending"},
            {"id": "task3", "status": "running"},
            {"id": "task4", "status": "completed"}
        ]
        
        for i, task in enumerate(tasks, 1):
            self.backend.save(f"task{i}", task)
        
        summary = self.backend.get_status_summary()
        
        assert summary["total_tasks"] == 4
        assert summary["status_breakdown"]["pending"] == 2
        assert summary["status_breakdown"]["running"] == 1
        assert summary["status_breakdown"]["completed"] == 1
        assert summary["auto_commit"] is True
        assert summary["git_initialized"] is True
    
    def test_git_history(self):
        """Test git history functionality."""
        # Save a task (should create commits)
        test_data = {"id": "history_test", "status": "pending"}
        self.backend.save("history_test", test_data)
        
        # Get history
        history = self.backend.get_git_history()
        
        assert len(history) >= 2  # At least init + save commits
        
        # Check recent commit
        recent_commit = history[0]
        assert "hash" in recent_commit
        assert "date" in recent_commit
        assert "message" in recent_commit
        assert "GNAP:" in recent_commit["message"]
    
    def test_key_sanitization(self):
        """Test that special characters in keys are handled."""
        test_data = {"id": "special_test", "status": "pending"}
        
        # Test key with special characters
        special_key = "task@#$%^&*()[]{}|;:,.<>?/~`"
        self.backend.save(special_key, test_data)
        
        # Should be able to load it back
        loaded = self.backend.load(special_key)
        assert loaded is not None
        assert loaded["id"] == "special_test"
        
        # Check that file was created with sanitized name
        task_file = Path(self.temp_dir) / ".gnap" / "tasks"
        task_files = list(task_file.glob("*.json"))
        assert len(task_files) == 1
        
        # Filename should be sanitized
        filename = task_files[0].name
        for char in "@#$%^&*()[]{}|;:,.<>?/~`":
            assert char not in filename
    
    def test_concurrent_access(self):
        """Test thread-safe operations."""
        import threading
        import time
        
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                for i in range(5):
                    key = f"worker_{worker_id}_task_{i}"
                    data = {"id": key, "worker": worker_id, "iteration": i}
                    self.backend.save(key, data)
                    
                    # Small delay to increase chance of concurrent access
                    time.sleep(0.01)
                    
                    loaded = self.backend.load(key)
                    if loaded:
                        results.append(loaded)
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads
        threads = []
        for worker_id in range(3):
            thread = threading.Thread(target=worker, args=(worker_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 15  # 3 workers * 5 tasks each
    
    def test_load_nonexistent(self):
        """Test loading non-existent key returns None."""
        result = self.backend.load("does_not_exist")
        assert result is None
    
    def test_factory_function(self):
        """Test the factory function."""
        from gnap_storage_backend import get_gnap_backend
        
        backend = get_gnap_backend(repo_path=self.temp_dir)
        assert isinstance(backend, GNAPStorageBackend)
        
        # Test basic operation
        test_data = {"test": "factory"}
        backend.save("factory_test", test_data)
        
        loaded = backend.load("factory_test")
        assert loaded["test"] == "factory"


def test_protocol_compliance():
    """Test that GNAPStorageBackend properly implements StorageBackendProtocol."""
    try:
        from praisonaiagents.storage.protocols import StorageBackendProtocol
        
        # Create instance
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = GNAPStorageBackend(repo_path=temp_dir)
            
            # Check protocol compliance
            assert isinstance(backend, StorageBackendProtocol)
            
            # Test all required methods exist and work
            test_data = {"test": "protocol"}
            backend.save("test_key", test_data)
            
            assert backend.exists("test_key")
            
            loaded = backend.load("test_key")
            assert loaded["test"] == "protocol"
            
            keys = backend.list_keys()
            assert "test_key" in keys
            
            deleted = backend.delete("test_key")
            assert deleted is True
            assert not backend.exists("test_key")
            
    except ImportError:
        # If praisonaiagents not available, skip protocol test
        pytest.skip("praisonaiagents package not available")


if __name__ == "__main__":
    # Run tests manually if not using pytest
    test_instance = TestGNAPStorageBackend()
    
    try:
        test_instance.setup_method()
        test_instance.test_save_and_load()
        print("✅ test_save_and_load passed")
        
        test_instance.test_exists()
        print("✅ test_exists passed")
        
        test_instance.test_delete()
        print("✅ test_delete passed")
        
        test_instance.test_list_keys()
        print("✅ test_list_keys passed")
        
        test_instance.test_gnap_folder_structure()
        print("✅ test_gnap_folder_structure passed")
        
        test_instance.test_git_initialization()
        print("✅ test_git_initialization passed")
        
        test_instance.test_status_summary()
        print("✅ test_status_summary passed")
        
        print("\n🎉 All tests passed! GNAP storage backend is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise
    finally:
        test_instance.teardown_method()