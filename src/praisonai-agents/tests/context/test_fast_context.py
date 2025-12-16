"""
Tests for FastContext high-level API.
"""

import pytest
import tempfile
import time
from pathlib import Path


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory structure
        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        
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
        
        auth_dir = src_dir / "auth"
        auth_dir.mkdir()
        
        (auth_dir / "handler.py").write_text("""
from typing import Optional

class AuthHandler:
    def __init__(self):
        self.token = None
    
    def authenticate(self, credentials: dict) -> bool:
        return True
    
    def logout(self):
        self.token = None
""")
        
        yield tmpdir


class TestFastContextInit:
    """Tests for FastContext initialization."""
    
    def test_default_initialization(self, temp_workspace):
        """Test default initialization."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        
        assert fc.workspace_path == temp_workspace
        assert fc.max_turns == 4
        assert fc.max_parallel == 8
        assert fc.model == "gpt-4o-mini"
        assert fc.cache_enabled is True
    
    def test_custom_initialization(self, temp_workspace):
        """Test custom initialization."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(
            workspace_path=temp_workspace,
            max_turns=3,
            max_parallel=4,
            model="claude-3-haiku-20240307",
            cache_enabled=False
        )
        
        assert fc.max_turns == 3
        assert fc.max_parallel == 4
        assert fc.model == "claude-3-haiku-20240307"
        assert fc.cache_enabled is False
    
    def test_context_manager(self, temp_workspace):
        """Test context manager usage."""
        from praisonaiagents.context.fast import FastContext
        
        with FastContext(workspace_path=temp_workspace) as fc:
            result = fc.search("def")
            assert result.total_files > 0


class TestFastContextSearch:
    """Tests for FastContext search functionality."""
    
    def test_search_basic(self, temp_workspace):
        """Test basic search."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        result = fc.search("authenticate")
        
        assert result.total_files > 0
        file_paths = [f.path for f in result.files]
        assert any("main.py" in p for p in file_paths)
    
    def test_search_with_patterns(self, temp_workspace):
        """Test search with include patterns."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        result = fc.search("def", include_patterns=["**/auth/*.py"])
        
        for f in result.files:
            assert "auth" in f.path
    
    def test_search_no_results(self, temp_workspace):
        """Test search with no matches."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        result = fc.search("nonexistent_xyz_123")
        
        assert result.total_files == 0


class TestFastContextCache:
    """Tests for FastContext caching."""
    
    def test_cache_hit(self, temp_workspace):
        """Test cache hit on repeated query."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace, cache_enabled=True)
        
        # First search
        result1 = fc.search("authenticate")
        assert result1.from_cache is False
        
        # Second search (should hit cache)
        result2 = fc.search("authenticate")
        assert result2.from_cache is True
    
    def test_cache_disabled(self, temp_workspace):
        """Test cache disabled."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace, cache_enabled=False)
        
        result1 = fc.search("authenticate")
        result2 = fc.search("authenticate")
        
        assert result1.from_cache is False
        assert result2.from_cache is False
    
    def test_clear_cache(self, temp_workspace):
        """Test clearing cache."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace, cache_enabled=True)
        
        fc.search("authenticate")
        fc.clear_cache()
        
        result = fc.search("authenticate")
        assert result.from_cache is False


class TestFastContextFiles:
    """Tests for FastContext file operations."""
    
    def test_search_files(self, temp_workspace):
        """Test searching for files."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        result = fc.search_files("**/*.py")
        
        assert result.total_files >= 3
    
    def test_read_context(self, temp_workspace):
        """Test reading file context."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        content = fc.read_context("src/main.py")
        
        assert content is not None
        assert "def main():" in content
    
    def test_read_context_with_lines(self, temp_workspace):
        """Test reading specific lines."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        content = fc.read_context("src/main.py", start_line=1, end_line=5, context_lines=0)
        
        assert content is not None
        lines = content.split("\n")
        assert len(lines) <= 5


class TestFastContextAgentIntegration:
    """Tests for FastContext agent integration."""
    
    def test_get_context_for_agent(self, temp_workspace):
        """Test getting formatted context for agent."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        context = fc.get_context_for_agent("authenticate")
        
        assert "Relevant Code Context" in context
        assert "authenticate" in context.lower()
    
    def test_get_context_for_agent_no_results(self, temp_workspace):
        """Test context for agent with no results."""
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(workspace_path=temp_workspace)
        context = fc.get_context_for_agent("nonexistent_xyz_123")
        
        assert "No relevant code found" in context


class TestFastSearchFunction:
    """Tests for fast_search convenience function."""
    
    def test_fast_search(self, temp_workspace):
        """Test fast_search function."""
        from praisonaiagents.context.fast.fast_context import fast_search
        
        result = fast_search("authenticate", workspace_path=temp_workspace)
        
        assert result.total_files > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
