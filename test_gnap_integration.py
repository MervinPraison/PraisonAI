"""
Test GNAP Storage Backend Integration for PraisonAI-Tools.

Verifies that the GNAP storage backend correctly implements StorageBackendProtocol
and integrates with PraisonAI's storage system.
"""

import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add current directory to path for testing
sys.path.insert(0, str(Path(__file__).parent))

from gnap_module.storage_backend import GNAPStorageBackend, get_gnap_backend

def test_gnap_basic_functionality():
    """Test basic GNAP storage backend functionality."""
    print("Testing GNAP Storage Backend...")
    
    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")
        
        # Initialize GNAP backend
        backend = GNAPStorageBackend(
            repo_path=temp_dir,
            auto_commit=True
        )
        
        # Test save
        task_data = {
            "id": "task_001",
            "status": "pending",
            "agent": "researcher",
            "description": "Research AI trends",
            "priority": "high",
            "created_at": "2026-04-08T06:00:00Z"
        }
        
        print("✓ Saving task...")
        backend.save("task_001", task_data)
        
        # Test exists
        assert backend.exists("task_001"), "Task should exist after saving"
        print("✓ Task exists check passed")
        
        # Test load
        loaded_task = backend.load("task_001")
        assert loaded_task is not None, "Loaded task should not be None"
        assert loaded_task["id"] == "task_001", "Task ID should match"
        assert loaded_task["status"] == "pending", "Task status should match"
        print("✓ Task loaded successfully")
        
        # Test list keys
        keys = backend.list_keys()
        assert "task_001" in keys, "Task should be in key list"
        print("✓ Key listing works")
        
        # Test prefix search
        backend.save("task_002", {"id": "task_002", "status": "running"})
        backend.save("other_001", {"id": "other_001", "status": "completed"})
        
        task_keys = backend.list_keys(prefix="task_")
        assert len(task_keys) == 2, "Should find 2 tasks with 'task_' prefix"
        assert "task_001" in task_keys
        assert "task_002" in task_keys
        assert "other_001" not in task_keys
        print("✓ Prefix filtering works")
        
        # Test delete
        result = backend.delete("task_002")
        assert result is True, "Delete should return True for existing task"
        assert not backend.exists("task_002"), "Task should not exist after deletion"
        print("✓ Task deletion works")
        
        # Test GNAP folder structure
        gnap_path = Path(temp_dir) / ".gnap"
        assert gnap_path.exists(), ".gnap folder should exist"
        assert (gnap_path / "tasks").exists(), "tasks folder should exist"
        assert (gnap_path / "config.json").exists(), "config.json should exist"
        print("✓ GNAP folder structure created correctly")
        
        # Test git repository
        git_path = Path(temp_dir) / ".git"
        assert git_path.exists(), "Git repository should be initialized"
        print("✓ Git repository initialized")
        
        # Test status summary
        summary = backend.get_status_summary()
        assert summary["total_tasks"] == 2, "Should have 2 tasks remaining"
        assert summary["git_initialized"] is True
        print("✓ Status summary works")
        
        # Test git history
        history = backend.get_git_history()
        assert len(history) >= 1, "Should have at least one commit"
        print("✓ Git history retrieval works")
        
        print("\n🎉 All GNAP backend tests passed!")
        
        return True


def test_factory_function():
    """Test the factory function for backend creation."""
    print("\nTesting factory function...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        backend = get_gnap_backend(repo_path=temp_dir)
        assert isinstance(backend, GNAPStorageBackend)
        
        # Test basic operation
        test_data = {"test": "factory_function", "value": 42}
        backend.save("factory_test", test_data)
        
        loaded = backend.load("factory_test")
        assert loaded["test"] == "factory_function"
        assert loaded["value"] == 42
        
        print("✓ Factory function works correctly")
        
        return True


def test_protocol_compliance():
    """Test StorageBackendProtocol compliance."""
    print("\nTesting protocol compliance...")
    
    try:
        # Try importing the protocol
        from praisonaiagents.storage.protocols import StorageBackendProtocol
        
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = GNAPStorageBackend(repo_path=temp_dir)
            
            # Check if it implements the protocol
            assert isinstance(backend, StorageBackendProtocol)
            
            print("✓ GNAP backend implements StorageBackendProtocol")
            
    except ImportError:
        print("! praisonaiagents not available, skipping protocol compliance test")
        # Create mock protocol test
        backend = GNAPStorageBackend(repo_path=tempfile.mkdtemp())
        
        # Check required methods exist
        assert hasattr(backend, 'save')
        assert hasattr(backend, 'load') 
        assert hasattr(backend, 'delete')
        assert hasattr(backend, 'list_keys')
        assert hasattr(backend, 'exists')
        
        print("✓ GNAP backend has all required protocol methods")
        
        # Cleanup
        shutil.rmtree(backend.repo_path, ignore_errors=True)
        
    return True


def test_concurrent_access():
    """Test thread-safe operations."""
    print("\nTesting concurrent access...")
    
    import threading
    import time
    
    with tempfile.TemporaryDirectory() as temp_dir:
        backend = GNAPStorageBackend(repo_path=temp_dir, auto_commit=True)
        
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                for i in range(3):  # Reduced for faster testing
                    key = f"worker_{worker_id}_task_{i}"
                    data = {"worker_id": worker_id, "task_num": i, "data": f"test_data_{i}"}
                    
                    backend.save(key, data)
                    
                    # Small delay
                    time.sleep(0.01)
                    
                    loaded = backend.load(key)
                    if loaded:
                        results.append(loaded)
                        
            except Exception as e:
                errors.append(f"Worker {worker_id}: {str(e)}")
        
        # Create threads
        threads = []
        for worker_id in range(2):  # Reduced for faster testing
            thread = threading.Thread(target=worker, args=(worker_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 6, f"Expected 6 results, got {len(results)}"  # 2 workers * 3 tasks
        
        print("✓ Concurrent access works correctly")
        
        return True


def test_gnap_specific_features():
    """Test GNAP-specific features."""
    print("\nTesting GNAP-specific features...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        backend = GNAPStorageBackend(
            repo_path=temp_dir,
            auto_commit=True,
            commit_author="Test Agent",
            commit_email="test@gnap.ai"
        )
        
        # Test task with GNAP metadata
        task = {
            "id": "gnap_task_001",
            "status": "pending",
            "agent": "gnap_agent",
            "dependencies": ["task_000"],
            "payload": {"action": "research", "topic": "GNAP protocol"}
        }
        
        backend.save("gnap_task_001", task)
        
        # Verify .gnap folder structure
        gnap_path = Path(temp_dir) / ".gnap"
        task_file = gnap_path / "tasks" / "gnap_task_001.json"
        
        assert task_file.exists(), "Task file should exist"
        
        # Read raw task file to verify GNAP metadata
        import json
        with open(task_file, 'r') as f:
            raw_data = json.load(f)
        
        assert "_gnap" in raw_data, "GNAP metadata should be present in file"
        assert raw_data["_gnap"]["key"] == "gnap_task_001"
        assert raw_data["_gnap"]["version"] == "1.0"
        
        # But loaded data should not contain metadata
        loaded = backend.load("gnap_task_001")
        assert "_gnap" not in loaded, "Loaded data should not contain GNAP metadata"
        
        print("✓ GNAP metadata handling works correctly")
        
        # Test git history with specific task
        task_history = backend.get_git_history(key="gnap_task_001")
        assert len(task_history) >= 1, "Should have commit history for specific task"
        
        print("✓ Task-specific git history works")
        
        return True


if __name__ == "__main__":
    """Run all tests."""
    print("=" * 60)
    print("GNAP Storage Backend Integration Tests")
    print("=" * 60)
    
    try:
        test_gnap_basic_functionality()
        test_factory_function() 
        test_protocol_compliance()
        test_concurrent_access()
        test_gnap_specific_features()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED! GNAP storage backend is ready for integration.")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)