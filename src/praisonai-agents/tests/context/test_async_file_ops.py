"""
Tests for async file operations.
"""

import pytest
import tempfile
import asyncio
from pathlib import Path


@pytest.fixture
def temp_file():
    """Create a temporary file with test content."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


class TestAsyncFileOps:
    """Tests for async file operations."""
    
    def test_aiofiles_availability_check(self):
        """Should check if aiofiles is available."""
        from praisonaiagents.context.fast.async_file_ops import is_aiofiles_available
        
        result = is_aiofiles_available()
        assert isinstance(result, bool)
    
    @pytest.mark.asyncio
    async def test_async_read_file(self, temp_file):
        """Should read file content async."""
        from praisonaiagents.context.fast.async_file_ops import async_read_file
        
        content = await async_read_file(temp_file)
        
        assert "Line 1" in content
        assert "Line 5" in content
    
    @pytest.mark.asyncio
    async def test_async_read_lines(self, temp_file):
        """Should read specific lines async."""
        from praisonaiagents.context.fast.async_file_ops import async_read_lines
        
        lines = await async_read_lines(temp_file, start_line=2, end_line=4)
        
        assert len(lines) == 3
        assert lines[0] == "Line 2"
        assert lines[2] == "Line 4"
    
    @pytest.mark.asyncio
    async def test_fallback_works_without_aiofiles(self, temp_file, monkeypatch):
        """Should fallback gracefully if aiofiles not available."""
        from praisonaiagents.context.fast import async_file_ops
        
        # Force aiofiles to be unavailable
        monkeypatch.setattr(async_file_ops, "_AIOFILES_AVAILABLE", False)
        
        content = await async_file_ops.async_read_file(temp_file)
        assert "Line 1" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
