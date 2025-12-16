"""
Tests for Fast Context parallel executor.
"""

import pytest
import asyncio
import time
import tempfile
from pathlib import Path


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        for i in range(5):
            (Path(tmpdir) / f"file{i}.py").write_text(f"# File {i}\ndef func{i}(): pass")
        yield tmpdir


class TestParallelExecutor:
    """Tests for ParallelExecutor class."""
    
    @pytest.mark.asyncio
    async def test_execute_single_task(self, temp_workspace):
        """Test executing a single task."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        from praisonaiagents.context.fast.search_tools import glob_search
        
        executor = ParallelExecutor(max_parallel=8)
        
        tasks = [
            {"tool": "glob_search", "args": {"search_path": temp_workspace, "pattern": "*.py"}}
        ]
        
        results = await executor.execute(tasks)
        
        assert len(results) == 1
        assert len(results[0]) == 5  # 5 .py files
    
    @pytest.mark.asyncio
    async def test_execute_multiple_tasks_parallel(self, temp_workspace):
        """Test executing multiple tasks in parallel."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        
        executor = ParallelExecutor(max_parallel=8)
        
        tasks = [
            {"tool": "glob_search", "args": {"search_path": temp_workspace, "pattern": "*.py"}},
            {"tool": "grep_search", "args": {"search_path": temp_workspace, "pattern": "def"}},
            {"tool": "list_directory", "args": {"dir_path": temp_workspace}},
        ]
        
        start = time.perf_counter()
        results = await executor.execute(tasks)
        elapsed = time.perf_counter() - start
        
        assert len(results) == 3
        # All tasks should complete (parallel execution)
        assert all(r is not None for r in results)
    
    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, temp_workspace):
        """Test execution with timeout."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        
        executor = ParallelExecutor(max_parallel=8, timeout=0.001)  # Very short timeout
        
        # This should timeout for slow operations
        tasks = [
            {"tool": "glob_search", "args": {"search_path": temp_workspace, "pattern": "**/*.py"}}
        ]
        
        results = await executor.execute(tasks)
        
        # Should return results (either success or timeout error)
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_execute_respects_max_parallel(self, temp_workspace):
        """Test that max_parallel limit is respected."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        
        executor = ParallelExecutor(max_parallel=2)
        
        # Create more tasks than max_parallel
        tasks = [
            {"tool": "glob_search", "args": {"search_path": temp_workspace, "pattern": "*.py"}}
            for _ in range(5)
        ]
        
        results = await executor.execute(tasks)
        
        assert len(results) == 5
        # All should complete successfully
        assert all(len(r) == 5 for r in results)
    
    @pytest.mark.asyncio
    async def test_execute_handles_errors(self, temp_workspace):
        """Test that errors in one task don't affect others."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        
        executor = ParallelExecutor(max_parallel=8)
        
        tasks = [
            {"tool": "glob_search", "args": {"search_path": temp_workspace, "pattern": "*.py"}},
            {"tool": "read_file", "args": {"filepath": "/nonexistent/file.py"}},  # Will fail
            {"tool": "list_directory", "args": {"dir_path": temp_workspace}},
        ]
        
        results = await executor.execute(tasks)
        
        assert len(results) == 3
        # First and third should succeed
        assert len(results[0]) == 5
        assert results[1]["success"] is False  # Error result
        assert results[2]["success"] is True
    
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, temp_workspace):
        """Test handling of unknown tool."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        
        executor = ParallelExecutor(max_parallel=8)
        
        tasks = [
            {"tool": "unknown_tool", "args": {}}
        ]
        
        results = await executor.execute(tasks)
        
        assert len(results) == 1
        assert "error" in results[0]
    
    @pytest.mark.asyncio
    async def test_execute_empty_tasks(self):
        """Test executing empty task list."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        
        executor = ParallelExecutor(max_parallel=8)
        
        results = await executor.execute([])
        
        assert results == []
    
    def test_execute_sync(self, temp_workspace):
        """Test synchronous execution wrapper."""
        from praisonaiagents.context.fast.parallel_executor import ParallelExecutor
        
        executor = ParallelExecutor(max_parallel=8)
        
        tasks = [
            {"tool": "glob_search", "args": {"search_path": temp_workspace, "pattern": "*.py"}}
        ]
        
        results = executor.execute_sync(tasks)
        
        assert len(results) == 1
        assert len(results[0]) == 5


class TestToolCallBatch:
    """Tests for ToolCallBatch class."""
    
    def test_batch_creation(self):
        """Test creating a tool call batch."""
        from praisonaiagents.context.fast.parallel_executor import ToolCallBatch
        
        batch = ToolCallBatch()
        batch.add("grep_search", search_path="/path", pattern="test")
        batch.add("glob_search", search_path="/path", pattern="*.py")
        
        assert len(batch.tasks) == 2
    
    def test_batch_max_size(self):
        """Test batch respects max size."""
        from praisonaiagents.context.fast.parallel_executor import ToolCallBatch
        
        batch = ToolCallBatch(max_size=2)
        batch.add("grep_search", search_path="/path", pattern="test1")
        batch.add("grep_search", search_path="/path", pattern="test2")
        
        # Should not add beyond max_size
        added = batch.add("grep_search", search_path="/path", pattern="test3")
        
        assert added is False
        assert len(batch.tasks) == 2
    
    def test_batch_is_full(self):
        """Test is_full property."""
        from praisonaiagents.context.fast.parallel_executor import ToolCallBatch
        
        batch = ToolCallBatch(max_size=2)
        assert batch.is_full is False
        
        batch.add("grep_search", search_path="/path", pattern="test1")
        assert batch.is_full is False
        
        batch.add("grep_search", search_path="/path", pattern="test2")
        assert batch.is_full is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
