"""
Unit tests for GNAP plugin.

Tests core functionality without requiring LLM calls.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

# Import the GNAP components
import sys
import os
sys.path.append(os.path.dirname(__file__))

from gnap_plugin import GnapPlugin
from gnap_storage import GNAPStorageBackend


class TestGNAPPlugin:
    """Test the GNAP plugin functionality."""
    
    @pytest.fixture
    def temp_repo(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def mock_git(self):
        """Mock GitPython to avoid real git operations."""
        with patch('gnap_plugin.GitPython') as mock_git:
            mock_repo = Mock()
            mock_repo.iter_commits.return_value = []
            mock_repo.active_branch.name = "main"
            mock_repo.index = Mock()
            mock_repo.index.add = Mock()
            mock_repo.index.commit = Mock()
            mock_repo.index.diff.return_value = ["mock_change"]
            mock_git.Repo.return_value = mock_repo
            mock_git.Repo.init.return_value = mock_repo
            mock_git.InvalidGitRepositoryError = Exception
            yield mock_git
    
    def test_plugin_properties(self, temp_repo, mock_git):
        """Test plugin protocol properties."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        
        assert plugin.name == "gnap"
        assert plugin.version == "1.0.0"
    
    def test_plugin_lifecycle(self, temp_repo, mock_git):
        """Test plugin initialization and shutdown."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        
        # Test initialization
        plugin.on_init({})
        assert plugin._initialized is True
        
        # Test shutdown
        plugin.on_shutdown()
        # Should not raise an exception
    
    def test_storage_backend_save_load(self, temp_repo, mock_git):
        """Test basic save and load operations."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        plugin.on_init({})
        
        # Test save
        test_data = {"status": "completed", "result": "success"}
        plugin.save("test_task", test_data)
        
        # Verify file was created
        task_file = temp_repo / ".gnap" / "tasks" / "test_task.json"
        assert task_file.exists()
        
        # Verify content
        with open(task_file) as f:
            saved_data = json.load(f)
        
        assert "_gnap" in saved_data
        assert saved_data["status"] == "completed"
        assert saved_data["result"] == "success"
        
        # Test load
        loaded_data = plugin.load("test_task")
        assert loaded_data["status"] == "completed"
        assert loaded_data["result"] == "success"
        assert "_gnap" not in loaded_data  # Metadata should be stripped
    
    def test_storage_backend_delete(self, temp_repo, mock_git):
        """Test delete operation."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        plugin.on_init({})
        
        # Save a task first
        plugin.save("delete_me", {"status": "pending"})
        assert plugin.exists("delete_me")
        
        # Delete the task
        result = plugin.delete("delete_me")
        assert result is True
        assert not plugin.exists("delete_me")
        
        # Try to delete non-existent task
        result = plugin.delete("not_found")
        assert result is False
    
    def test_storage_backend_list_keys(self, temp_repo, mock_git):
        """Test listing keys with prefix filtering."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        plugin.on_init({})
        
        # Save multiple tasks
        tasks = {
            "research_001": {"status": "completed"},
            "research_002": {"status": "pending"}, 
            "analysis_001": {"status": "running"},
            "analysis_002": {"status": "completed"}
        }
        
        for task_id, data in tasks.items():
            plugin.save(task_id, data)
        
        # Test list all
        all_keys = plugin.list_keys()
        assert len(all_keys) == 4
        assert "research_001" in all_keys
        assert "analysis_002" in all_keys
        
        # Test prefix filtering
        research_keys = plugin.list_keys(prefix="research_")
        assert len(research_keys) == 2
        assert "research_001" in research_keys
        assert "research_002" in research_keys
        
        analysis_keys = plugin.list_keys(prefix="analysis_")
        assert len(analysis_keys) == 2
        assert "analysis_001" in analysis_keys
        assert "analysis_002" in analysis_keys
    
    def test_storage_backend_exists(self, temp_repo, mock_git):
        """Test existence checking."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        plugin.on_init({})
        
        # Check non-existent task
        assert not plugin.exists("not_found")
        
        # Save a task and check it exists
        plugin.save("exists_test", {"data": "test"})
        assert plugin.exists("exists_test")
    
    def test_status_summary(self, temp_repo, mock_git):
        """Test status summary generation."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        plugin.on_init({})
        
        # Save tasks with different statuses
        tasks = {
            "task1": {"status": "completed", "agent": "researcher"},
            "task2": {"status": "pending", "agent": "writer"},
            "task3": {"status": "completed", "agent": "researcher"},
            "task4": {"status": "failed", "agent": "analyzer"}
        }
        
        for task_id, data in tasks.items():
            plugin.save(task_id, data)
        
        # Get status summary
        summary = plugin.get_status_summary()
        
        assert summary["total_tasks"] == 4
        assert summary["by_status"]["completed"] == 2
        assert summary["by_status"]["pending"] == 1
        assert summary["by_status"]["failed"] == 1
        
        # Check agent counts
        assert "researcher" in summary["by_agent"]
        assert "writer" in summary["by_agent"]
        assert "analyzer" in summary["by_agent"]
        
        # Check recent activity
        assert len(summary["recent_activity"]) == 4
    
    def test_gnap_storage_backend_alias(self, temp_repo, mock_git):
        """Test GNAPStorageBackend as standalone class."""
        backend = GNAPStorageBackend(repo_path=str(temp_repo))
        backend.on_init({})
        
        # Should work exactly like GnapPlugin
        backend.save("alias_test", {"data": "test"})
        loaded = backend.load("alias_test")
        
        assert loaded["data"] == "test"
        assert backend.exists("alias_test")
    
    def test_lazy_git_import(self, temp_repo):
        """Test that GitPython is imported lazily."""
        # Create plugin without initializing
        plugin = GnapPlugin(repo_path=str(temp_repo))
        
        # GitPython should not be imported yet
        assert 'git' not in sys.modules or sys.modules.get('git') is None
        
        # Mock the import to fail
        with patch('builtins.__import__', side_effect=ImportError("GitPython not found")):
            with pytest.raises(ImportError, match="GitPython is required"):
                plugin.on_init({})
    
    def test_auto_commit_environment_variable(self, temp_repo, mock_git):
        """Test auto-commit behavior controlled by environment variable."""
        plugin = GnapPlugin(repo_path=str(temp_repo))
        plugin.on_init({})
        
        # Test with auto-commit enabled (default)
        with patch.dict(os.environ, {"GNAP_AUTO_COMMIT": "true"}):
            plugin.save("auto_commit_test", {"data": "test"})
            # Should call commit (mocked)
            plugin._repo.index.commit.assert_called()
        
        # Reset mock
        plugin._repo.index.commit.reset_mock()
        
        # Test with auto-commit disabled
        with patch.dict(os.environ, {"GNAP_AUTO_COMMIT": "false"}):
            plugin.save("no_auto_commit_test", {"data": "test"})
            # Should not call commit
            plugin._repo.index.commit.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])