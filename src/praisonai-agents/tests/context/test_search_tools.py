"""
Tests for Fast Context search tools.
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
        
        # Create Python files
        (src_dir / "main.py").write_text("""
def main():
    print("Hello, World!")
    authenticate_user()

def authenticate_user():
    # Authentication logic here
    pass

class UserService:
    def login(self, username, password):
        return True
""")
        
        (src_dir / "utils.py").write_text("""
import os

def get_config():
    return {"debug": True}

def validate_input(data):
    if not data:
        raise ValueError("Empty data")
    return True
""")
        
        # Create subdirectory
        auth_dir = src_dir / "auth"
        auth_dir.mkdir()
        
        (auth_dir / "handler.py").write_text("""
from typing import Optional

class AuthHandler:
    def __init__(self):
        self.token = None
    
    def authenticate(self, credentials: dict) -> bool:
        # Authenticate user
        return True
    
    def logout(self):
        self.token = None
""")
        
        # Create a .gitignore
        (Path(tmpdir) / ".gitignore").write_text("""
__pycache__/
*.pyc
.env
""")
        
        # Create ignored directory
        cache_dir = Path(tmpdir) / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.pyc").write_text("cached content")
        
        yield tmpdir


class TestGrepSearch:
    """Tests for grep_search function."""
    
    def test_grep_simple_pattern(self, temp_workspace):
        """Test grep with simple pattern."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "authenticate")
        
        assert len(results) > 0
        # Should find in main.py and handler.py
        paths = [r["path"] for r in results]
        assert any("main.py" in p for p in paths)
        assert any("handler.py" in p for p in paths)
    
    def test_grep_regex_pattern(self, temp_workspace):
        """Test grep with regex pattern."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, r"def \w+\(", is_regex=True)
        
        assert len(results) > 0
        # Should find function definitions
    
    def test_grep_case_insensitive(self, temp_workspace):
        """Test grep case insensitive search."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "AUTHENTICATE", case_sensitive=False)
        
        assert len(results) > 0
    
    def test_grep_case_sensitive(self, temp_workspace):
        """Test grep case sensitive search."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "AUTHENTICATE", case_sensitive=True)
        
        assert len(results) == 0  # No uppercase AUTHENTICATE exists
    
    def test_grep_with_file_pattern(self, temp_workspace):
        """Test grep with file pattern filter."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "def", include_patterns=["*.py"])
        
        assert len(results) > 0
        # All results should be .py files
        for r in results:
            assert r["path"].endswith(".py")
    
    def test_grep_with_exclude_pattern(self, temp_workspace):
        """Test grep with exclude pattern."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "def", exclude_patterns=["**/auth/*"])
        
        # Should not include auth directory files
        for r in results:
            assert "auth" not in r["path"]
    
    def test_grep_max_results(self, temp_workspace):
        """Test grep with max results limit."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "def", max_results=2)
        
        assert len(results) <= 2
    
    def test_grep_no_matches(self, temp_workspace):
        """Test grep with no matches."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "nonexistent_pattern_xyz")
        
        assert len(results) == 0
    
    def test_grep_respects_gitignore(self, temp_workspace):
        """Test grep respects .gitignore patterns."""
        from praisonaiagents.context.fast.search_tools import grep_search
        
        results = grep_search(temp_workspace, "cached", respect_gitignore=True)
        
        # Should not find content in __pycache__
        for r in results:
            assert "__pycache__" not in r["path"]


class TestGlobSearch:
    """Tests for glob_search function."""
    
    def test_glob_all_python_files(self, temp_workspace):
        """Test glob to find all Python files."""
        from praisonaiagents.context.fast.search_tools import glob_search
        
        results = glob_search(temp_workspace, "**/*.py")
        
        assert len(results) >= 3  # main.py, utils.py, handler.py
        for r in results:
            assert r["path"].endswith(".py")
    
    def test_glob_specific_directory(self, temp_workspace):
        """Test glob in specific directory."""
        from praisonaiagents.context.fast.search_tools import glob_search
        
        results = glob_search(temp_workspace, "src/auth/*.py")
        
        assert len(results) == 1
        assert "handler.py" in results[0]["path"]
    
    def test_glob_by_name(self, temp_workspace):
        """Test glob by filename."""
        from praisonaiagents.context.fast.search_tools import glob_search
        
        results = glob_search(temp_workspace, "**/main.py")
        
        assert len(results) == 1
        assert "main.py" in results[0]["path"]
    
    def test_glob_no_matches(self, temp_workspace):
        """Test glob with no matches."""
        from praisonaiagents.context.fast.search_tools import glob_search
        
        results = glob_search(temp_workspace, "**/*.java")
        
        assert len(results) == 0
    
    def test_glob_max_results(self, temp_workspace):
        """Test glob with max results."""
        from praisonaiagents.context.fast.search_tools import glob_search
        
        results = glob_search(temp_workspace, "**/*.py", max_results=2)
        
        assert len(results) <= 2
    
    def test_glob_respects_gitignore(self, temp_workspace):
        """Test glob respects .gitignore."""
        from praisonaiagents.context.fast.search_tools import glob_search
        
        results = glob_search(temp_workspace, "**/*.pyc", respect_gitignore=True)
        
        assert len(results) == 0  # .pyc is in .gitignore


class TestReadFile:
    """Tests for read_file function."""
    
    def test_read_entire_file(self, temp_workspace):
        """Test reading entire file."""
        from praisonaiagents.context.fast.search_tools import read_file
        
        result = read_file(os.path.join(temp_workspace, "src", "main.py"))
        
        assert result["success"] is True
        assert "def main():" in result["content"]
        assert result["total_lines"] > 0
    
    def test_read_file_with_line_range(self, temp_workspace):
        """Test reading specific line range."""
        from praisonaiagents.context.fast.search_tools import read_file
        
        result = read_file(
            os.path.join(temp_workspace, "src", "main.py"),
            start_line=1,
            end_line=3
        )
        
        assert result["success"] is True
        assert result["start_line"] == 1
        assert result["end_line"] == 3
        lines = result["content"].split("\n")
        assert len(lines) <= 3
    
    def test_read_nonexistent_file(self, temp_workspace):
        """Test reading nonexistent file."""
        from praisonaiagents.context.fast.search_tools import read_file
        
        result = read_file(os.path.join(temp_workspace, "nonexistent.py"))
        
        assert result["success"] is False
        assert "error" in result
    
    def test_read_file_with_context(self, temp_workspace):
        """Test reading with context lines."""
        from praisonaiagents.context.fast.search_tools import read_file
        
        result = read_file(
            os.path.join(temp_workspace, "src", "main.py"),
            start_line=5,
            end_line=5,
            context_lines=2
        )
        
        assert result["success"] is True
        # Should include 2 lines before and after line 5


class TestListDirectory:
    """Tests for list_directory function."""
    
    def test_list_directory(self, temp_workspace):
        """Test listing directory contents."""
        from praisonaiagents.context.fast.search_tools import list_directory
        
        result = list_directory(temp_workspace)
        
        assert result["success"] is True
        assert len(result["entries"]) > 0
        
        # Should contain src directory
        names = [e["name"] for e in result["entries"]]
        assert "src" in names
    
    def test_list_directory_recursive(self, temp_workspace):
        """Test listing directory recursively."""
        from praisonaiagents.context.fast.search_tools import list_directory
        
        result = list_directory(temp_workspace, recursive=True)
        
        assert result["success"] is True
        # Should find files in subdirectories
        paths = [e["path"] for e in result["entries"]]
        assert any("main.py" in p for p in paths)
        assert any("handler.py" in p for p in paths)
    
    def test_list_directory_max_depth(self, temp_workspace):
        """Test listing with max depth."""
        from praisonaiagents.context.fast.search_tools import list_directory
        
        result = list_directory(temp_workspace, recursive=True, max_depth=1)
        
        assert result["success"] is True
        # Should not find files in auth subdirectory (depth 2)
        paths = [e["path"] for e in result["entries"]]
        assert not any("handler.py" in p for p in paths)
    
    def test_list_nonexistent_directory(self, temp_workspace):
        """Test listing nonexistent directory."""
        from praisonaiagents.context.fast.search_tools import list_directory
        
        result = list_directory(os.path.join(temp_workspace, "nonexistent"))
        
        assert result["success"] is False
    
    def test_list_directory_respects_gitignore(self, temp_workspace):
        """Test listing respects .gitignore."""
        from praisonaiagents.context.fast.search_tools import list_directory
        
        result = list_directory(temp_workspace, recursive=True, respect_gitignore=True)
        
        # Should not include __pycache__
        paths = [e["path"] for e in result["entries"]]
        assert not any("__pycache__" in p for p in paths)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
