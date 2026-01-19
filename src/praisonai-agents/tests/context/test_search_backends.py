"""
Tests for FastContext search backends.

Tests the SearchBackend protocol and implementations:
- PythonSearchBackend (always available)
- RipgrepBackend (optional, with fallback)
"""

import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
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
        
        yield tmpdir


class TestSearchBackendProtocol:
    """Tests for SearchBackend protocol."""
    
    def test_python_backend_always_available(self):
        """Python backend should always be available."""
        from praisonaiagents.context.fast.search_backends import PythonSearchBackend
        
        backend = PythonSearchBackend()
        assert backend.is_available() is True
    
    def test_python_backend_grep(self, temp_workspace):
        """Python backend grep should find matches."""
        from praisonaiagents.context.fast.search_backends import PythonSearchBackend
        
        backend = PythonSearchBackend()
        results = backend.grep(temp_workspace, "authenticate")
        
        assert len(results) > 0
        assert any("main.py" in r.get("path", "") for r in results)
    
    def test_python_backend_glob(self, temp_workspace):
        """Python backend glob should find files."""
        from praisonaiagents.context.fast.search_backends import PythonSearchBackend
        
        backend = PythonSearchBackend()
        results = backend.glob(temp_workspace, "**/*.py")
        
        assert len(results) >= 2


class TestRipgrepBackend:
    """Tests for RipgrepBackend."""
    
    def test_ripgrep_availability_check(self):
        """RipgrepBackend should check if rg is installed."""
        from praisonaiagents.context.fast.search_backends import RipgrepBackend
        
        backend = RipgrepBackend()
        # Should return bool without error
        result = backend.is_available()
        assert isinstance(result, bool)
    
    def test_ripgrep_fallback_to_python(self, temp_workspace, monkeypatch):
        """When ripgrep not available, should fallback to Python backend."""
        from praisonaiagents.context.fast.search_backends import RipgrepBackend, get_search_backend
        
        # Force ripgrep to be unavailable
        monkeypatch.setattr("shutil.which", lambda x: None)
        
        backend = RipgrepBackend()
        assert backend.is_available() is False
        
        # Auto backend should fallback to python
        auto_backend = get_search_backend("auto")
        assert auto_backend.is_available() is True


class TestBackendSelection:
    """Tests for backend selection logic."""
    
    def test_get_python_backend(self):
        """Should return Python backend when requested."""
        from praisonaiagents.context.fast.search_backends import get_search_backend
        
        backend = get_search_backend("python")
        assert backend.is_available() is True
    
    def test_get_auto_backend(self):
        """Auto should return best available backend."""
        from praisonaiagents.context.fast.search_backends import get_search_backend
        
        backend = get_search_backend("auto")
        # Should always return a working backend
        assert backend.is_available() is True
    
    def test_invalid_backend_raises(self):
        """Invalid backend name should raise ValueError."""
        from praisonaiagents.context.fast.search_backends import get_search_backend
        
        with pytest.raises(ValueError):
            get_search_backend("invalid_backend")


class TestSmartBackend:
    """Tests for SmartBackend auto-selection based on codebase size."""
    
    def test_smart_backend_available(self):
        """SmartBackend should always be available."""
        from praisonaiagents.context.fast.search_backends import SmartBackend
        
        backend = SmartBackend()
        assert backend.is_available() is True
    
    def test_small_workspace_uses_python(self, temp_workspace):
        """Small workspace (<500 files) should use Python backend."""
        from praisonaiagents.context.fast.search_backends import SmartBackend
        
        backend = SmartBackend(workspace_path=temp_workspace)
        # Force check by doing a search
        results = backend.grep(temp_workspace, "def")
        
        # Should have results and used Python (fast)
        assert len(results) > 0
        # Check internal state - should not have selected ripgrep
        assert backend._use_ripgrep is False
    
    def test_count_files_fast(self, temp_workspace):
        """Helper should count files quickly with limit."""
        from praisonaiagents.context.fast.search_backends import _count_files_fast
        
        count = _count_files_fast(temp_workspace, limit=100)
        assert count >= 2  # We created at least 2 files
        assert count < 100  # Should be below limit
    
    def test_count_files_fast_skips_gitignore_dirs(self):
        """Should skip .git, node_modules, etc."""
        from praisonaiagents.context.fast.search_backends import _count_files_fast
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files in regular dir
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src", "file.py").write_text("code")
            
            # Create files in ignored dir
            Path(tmpdir, "node_modules").mkdir()
            Path(tmpdir, "node_modules", "pkg").mkdir()
            for i in range(10):
                Path(tmpdir, "node_modules", "pkg", f"file{i}.js").write_text("code")
            
            count = _count_files_fast(tmpdir)
            # Should only count src/file.py, not node_modules files
            assert count == 1
    
    def test_threshold_constant(self):
        """Threshold should be 500 files based on profiling."""
        from praisonaiagents.context.fast.search_backends import RIPGREP_FILE_THRESHOLD
        
        assert RIPGREP_FILE_THRESHOLD == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
