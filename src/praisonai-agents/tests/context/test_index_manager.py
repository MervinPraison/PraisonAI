"""
Tests for index manager.
"""

import pytest
import tempfile
import os
import time
from pathlib import Path


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        (Path(tmpdir) / "file1.py").write_text("print('hello')")
        (Path(tmpdir) / "file2.py").write_text("print('world')")
        yield tmpdir


class TestFileIndex:
    """Tests for FileIndex."""
    
    def test_index_creation(self, temp_workspace):
        """Should create empty index."""
        from praisonaiagents.context.fast.index_manager import FileIndex
        
        index = FileIndex(workspace_path=temp_workspace)
        
        assert len(index) == 0
        assert index.workspace_path == temp_workspace
    
    def test_index_update(self, temp_workspace):
        """Should update index for file."""
        from praisonaiagents.context.fast.index_manager import FileIndex
        
        index = FileIndex(workspace_path=temp_workspace)
        filepath = os.path.join(temp_workspace, "file1.py")
        
        index.update(filepath)
        
        assert len(index) == 1
        assert not index.needs_rescan(filepath)
    
    def test_needs_rescan_new_file(self, temp_workspace):
        """Should need rescan for new file."""
        from praisonaiagents.context.fast.index_manager import FileIndex
        
        index = FileIndex(workspace_path=temp_workspace)
        filepath = os.path.join(temp_workspace, "file1.py")
        
        assert index.needs_rescan(filepath) is True
    
    def test_needs_rescan_modified_file(self, temp_workspace):
        """Should need rescan for modified file."""
        from praisonaiagents.context.fast.index_manager import FileIndex
        
        index = FileIndex(workspace_path=temp_workspace)
        filepath = os.path.join(temp_workspace, "file1.py")
        
        index.update(filepath)
        assert index.needs_rescan(filepath) is False
        
        # Modify file
        time.sleep(0.01)  # Ensure mtime changes
        Path(filepath).write_text("print('modified')")
        
        assert index.needs_rescan(filepath) is True
    
    def test_save_and_load(self, temp_workspace):
        """Should save and load index."""
        from praisonaiagents.context.fast.index_manager import FileIndex
        
        # Create and save
        index = FileIndex(workspace_path=temp_workspace)
        index.update(os.path.join(temp_workspace, "file1.py"))
        assert index.save() is True
        
        # Load
        loaded = FileIndex.load(temp_workspace)
        assert loaded is not None
        assert len(loaded) == 1
    
    def test_load_or_create_existing(self, temp_workspace):
        """Should load existing index."""
        from praisonaiagents.context.fast.index_manager import FileIndex
        
        # Create and save
        index = FileIndex(workspace_path=temp_workspace)
        index.update(os.path.join(temp_workspace, "file1.py"))
        index.save()
        
        # Load or create
        loaded = FileIndex.load_or_create(temp_workspace)
        assert len(loaded) == 1
    
    def test_load_or_create_new(self, temp_workspace):
        """Should create new index if none exists."""
        from praisonaiagents.context.fast.index_manager import FileIndex
        
        # No existing index
        index = FileIndex.load_or_create(temp_workspace)
        assert len(index) == 0


class TestIndexWatcher:
    """Tests for IndexWatcher."""
    
    def test_watcher_availability(self):
        """Should check watchfiles availability."""
        from praisonaiagents.context.fast.index_manager import is_watchfiles_available
        
        result = is_watchfiles_available()
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
