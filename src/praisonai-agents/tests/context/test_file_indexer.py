"""
Tests for File Indexer.
"""

import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory structure
        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        
        (src_dir / "main.py").write_text("def main(): pass")
        (src_dir / "utils.py").write_text("def util(): pass")
        (src_dir / "config.json").write_text('{"key": "value"}')
        
        auth_dir = src_dir / "auth"
        auth_dir.mkdir()
        (auth_dir / "handler.py").write_text("class Handler: pass")
        
        # Create .gitignore
        (Path(tmpdir) / ".gitignore").write_text("__pycache__/\n*.pyc\n")
        
        # Create ignored directory
        cache_dir = Path(tmpdir) / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.pyc").write_text("cached")
        
        yield tmpdir


class TestFileIndexerInit:
    """Tests for FileIndexer initialization."""
    
    def test_default_initialization(self, temp_workspace):
        """Test default initialization."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        
        assert indexer.workspace_path == temp_workspace
        assert indexer.respect_gitignore is True
        assert indexer.total_files == 0
    
    def test_custom_extensions(self, temp_workspace):
        """Test custom extensions."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(
            workspace_path=temp_workspace,
            extensions={".py"}
        )
        
        assert indexer.extensions == {".py"}


class TestFileIndexerIndex:
    """Tests for FileIndexer indexing."""
    
    def test_index_files(self, temp_workspace):
        """Test indexing files."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        count = indexer.index()
        
        assert count >= 3  # At least main.py, utils.py, handler.py
        assert indexer.total_files >= 3
    
    def test_index_respects_gitignore(self, temp_workspace):
        """Test that indexing respects .gitignore."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace, respect_gitignore=True)
        indexer.index()
        
        # Should not include __pycache__ files
        for path in indexer.files:
            assert "__pycache__" not in path
            assert not path.endswith(".pyc")
    
    def test_index_by_extension(self, temp_workspace):
        """Test indexing organizes by extension."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        assert ".py" in indexer.by_extension
        assert len(indexer.by_extension[".py"]) >= 3
    
    def test_index_with_extension_filter(self, temp_workspace):
        """Test indexing with extension filter."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace, extensions={".py"})
        indexer.index()
        
        # Should only have .py files
        for path in indexer.files:
            assert path.endswith(".py")


class TestFileIndexerFind:
    """Tests for FileIndexer find methods."""
    
    def test_find_by_pattern(self, temp_workspace):
        """Test finding files by pattern."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        results = indexer.find_by_pattern("**/*.py")
        
        assert len(results) >= 3
        for info in results:
            assert info.path.endswith(".py")
    
    def test_find_by_extension(self, temp_workspace):
        """Test finding files by extension."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        results = indexer.find_by_extension(".py")
        
        assert len(results) >= 3
    
    def test_find_by_extension_without_dot(self, temp_workspace):
        """Test finding files by extension without dot."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        results = indexer.find_by_extension("py")
        
        assert len(results) >= 3
    
    def test_find_by_name_exact(self, temp_workspace):
        """Test finding files by exact name."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        results = indexer.find_by_name("main.py", exact=True)
        
        assert len(results) == 1
        assert results[0].path.endswith("main.py")
    
    def test_find_by_name_partial(self, temp_workspace):
        """Test finding files by partial name."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        results = indexer.find_by_name("handler")
        
        assert len(results) >= 1
        assert any("handler" in r.path for r in results)
    
    def test_get_file(self, temp_workspace):
        """Test getting file by path."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        # Find a file first
        results = indexer.find_by_name("main.py", exact=True)
        assert len(results) > 0
        
        # Get by path
        file_info = indexer.get_file(results[0].path)
        assert file_info is not None
        assert file_info.path == results[0].path


class TestFileIndexerStats:
    """Tests for FileIndexer statistics."""
    
    def test_get_stats(self, temp_workspace):
        """Test getting index statistics."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        stats = indexer.get_stats()
        
        assert stats["total_files"] >= 3
        assert stats["total_size_bytes"] > 0
        assert ".py" in stats["extensions"]
    
    def test_is_stale(self, temp_workspace):
        """Test stale check."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        
        # Before indexing, should be stale
        assert indexer.is_stale() is True
        
        indexer.index()
        
        # After indexing, should not be stale
        assert indexer.is_stale(max_age=60.0) is False


class TestFileIndexerPersistence:
    """Tests for FileIndexer save/load."""
    
    def test_save_and_load(self, temp_workspace):
        """Test saving and loading index."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        # Save index
        index_path = os.path.join(temp_workspace, ".fast_context_index.json")
        indexer.save_index(index_path)
        
        assert os.path.exists(index_path)
        
        # Load into new indexer
        indexer2 = FileIndexer(workspace_path=temp_workspace)
        loaded = indexer2.load_index(index_path)
        
        assert loaded is True
        assert indexer2.total_files == indexer.total_files
    
    def test_load_wrong_workspace(self, temp_workspace):
        """Test loading index from wrong workspace."""
        from praisonaiagents.context.fast.indexer import FileIndexer
        
        indexer = FileIndexer(workspace_path=temp_workspace)
        indexer.index()
        
        index_path = os.path.join(temp_workspace, ".fast_context_index.json")
        indexer.save_index(index_path)
        
        # Try to load with different workspace
        indexer2 = FileIndexer(workspace_path="/different/path")
        loaded = indexer2.load_index(index_path)
        
        assert loaded is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
