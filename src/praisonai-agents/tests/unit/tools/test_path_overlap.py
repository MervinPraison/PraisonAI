"""
Tests for path overlap detection functionality.

Tests file path conflict detection and sequential execution decisions.
"""

import pytest
import pathlib
from praisonaiagents.tools.path_overlap import (
    extract_paths, paths_conflict, detect_path_conflicts, 
    has_write_conflicts, group_by_conflicts
)
from praisonaiagents.tools.call_executor import ToolCall


class TestPathExtraction:
    
    def test_write_tool_path_extraction(self):
        """Test extracting paths from write tools."""
        tool_call = ToolCall(
            function_name="write_file",
            arguments={"path": "/tmp/test.txt", "content": "hello"},
            tool_call_id="1"
        )
        
        paths = extract_paths(tool_call)
        assert len(paths) == 1
        assert paths[0].name == "test.txt"
    
    def test_read_tool_no_paths(self):
        """Test that read-only tools don't extract paths."""
        tool_call = ToolCall(
            function_name="read_file",  # Not a write tool
            arguments={"path": "/tmp/test.txt"},
            tool_call_id="1"
        )
        
        paths = extract_paths(tool_call)
        assert len(paths) == 0
    
    def test_multiple_path_args(self):
        """Test extracting multiple paths from one tool call."""
        tool_call = ToolCall(
            function_name="copy_file",
            arguments={"source": "/tmp/src.txt", "dest": "/tmp/dst.txt"},
            tool_call_id="1"
        )
        
        paths = extract_paths(tool_call)
        assert len(paths) == 2
        assert any(p.name == "src.txt" for p in paths)
        assert any(p.name == "dst.txt" for p in paths)
    
    def test_invalid_path_ignored(self):
        """Test that invalid paths are ignored."""
        tool_call = ToolCall(
            function_name="write_file",
            arguments={"path": "", "content": "hello"},  # Empty path
            tool_call_id="1"
        )
        
        paths = extract_paths(tool_call)
        assert len(paths) == 0
    
    def test_non_string_args_ignored(self):
        """Test that non-string path arguments are ignored.""" 
        tool_call = ToolCall(
            function_name="write_file",
            arguments={"path": 123, "content": "hello"},  # Non-string path
            tool_call_id="1"
        )
        
        paths = extract_paths(tool_call)
        assert len(paths) == 0


class TestPathConflicts:
    
    def test_same_path_conflicts(self):
        """Test that identical paths conflict."""
        path1 = pathlib.Path("/tmp/test.txt")
        path2 = pathlib.Path("/tmp/test.txt") 
        
        assert paths_conflict(path1, path2) is True
    
    def test_parent_child_conflicts(self):
        """Test that parent/child paths conflict."""
        parent = pathlib.Path("/tmp")
        child = pathlib.Path("/tmp/subdir/file.txt")
        
        assert paths_conflict(parent, child) is True
        assert paths_conflict(child, parent) is True
    
    def test_sibling_paths_no_conflict(self):
        """Test that sibling paths don't conflict."""
        path1 = pathlib.Path("/tmp/file1.txt")
        path2 = pathlib.Path("/tmp/file2.txt")
        
        assert paths_conflict(path1, path2) is False
    
    def test_different_trees_no_conflict(self):
        """Test that paths in different directory trees don't conflict."""
        path1 = pathlib.Path("/tmp/dir1/file.txt")
        path2 = pathlib.Path("/var/dir2/file.txt")
        
        assert paths_conflict(path1, path2) is False
    
    def test_subdirectory_conflicts(self):
        """Test that subdirectory operations conflict."""
        dir_path = pathlib.Path("/tmp/mydir")
        file_in_dir = pathlib.Path("/tmp/mydir/file.txt")
        
        assert paths_conflict(dir_path, file_in_dir) is True


class TestConflictDetection:
    
    def test_no_conflicts_multiple_reads(self):
        """Test that multiple read operations don't conflict."""
        tool_calls = [
            ToolCall("read_file", {"path": "/tmp/file1.txt"}, "1"),
            ToolCall("read_file", {"path": "/tmp/file2.txt"}, "2"),
        ]
        
        assert detect_path_conflicts(tool_calls) is False
    
    def test_no_conflicts_different_paths(self):
        """Test that writes to different paths don't conflict."""
        tool_calls = [
            ToolCall("write_file", {"path": "/tmp/file1.txt", "content": "a"}, "1"),
            ToolCall("write_file", {"path": "/tmp/file2.txt", "content": "b"}, "2"),
        ]
        
        assert detect_path_conflicts(tool_calls) is False
    
    def test_conflicts_same_file(self):
        """Test that writes to the same file conflict."""
        tool_calls = [
            ToolCall("write_file", {"path": "/tmp/test.txt", "content": "a"}, "1"),
            ToolCall("edit_file", {"path": "/tmp/test.txt", "changes": "b"}, "2"),
        ]
        
        assert detect_path_conflicts(tool_calls) is True
    
    def test_conflicts_parent_child(self):
        """Test that parent/child directory operations conflict."""
        tool_calls = [
            ToolCall("mkdir", {"path": "/tmp/mydir"}, "1"),
            ToolCall("write_file", {"path": "/tmp/mydir/file.txt", "content": "x"}, "2"),
        ]
        
        assert detect_path_conflicts(tool_calls) is True
    
    def test_single_tool_no_conflict(self):
        """Test that single tool call never conflicts."""
        tool_calls = [
            ToolCall("write_file", {"path": "/tmp/test.txt", "content": "a"}, "1"),
        ]
        
        assert detect_path_conflicts(tool_calls) is False
    
    def test_empty_list_no_conflict(self):
        """Test that empty list has no conflicts."""
        assert detect_path_conflicts([]) is False


class TestWriteConflicts:
    
    def test_has_write_conflicts_delegates_to_detect(self):
        """Test that has_write_conflicts properly delegates."""
        tool_calls = [
            ToolCall("write_file", {"path": "/tmp/test.txt", "content": "a"}, "1"),
            ToolCall("edit_file", {"path": "/tmp/test.txt", "changes": "b"}, "2"),
        ]
        
        # Both functions should give same result
        assert has_write_conflicts(tool_calls) == detect_path_conflicts(tool_calls)
        assert has_write_conflicts(tool_calls) is True


class TestConflictGrouping:
    
    def test_group_no_conflicts(self):
        """Test grouping when no conflicts exist."""
        tool_calls = [
            ToolCall("write_file", {"path": "/tmp/file1.txt"}, "1"),
            ToolCall("write_file", {"path": "/tmp/file2.txt"}, "2"), 
            ToolCall("write_file", {"path": "/tmp/file3.txt"}, "3"),
        ]
        
        groups = group_by_conflicts(tool_calls)
        assert len(groups) == 1  # All can run together
        assert len(groups[0]) == 3
    
    def test_group_with_conflicts(self):
        """Test grouping when conflicts exist."""
        tool_calls = [
            ToolCall("write_file", {"path": "/tmp/test.txt", "content": "a"}, "1"),
            ToolCall("write_file", {"path": "/tmp/other.txt", "content": "b"}, "2"),
            ToolCall("edit_file", {"path": "/tmp/test.txt", "changes": "c"}, "3"),
        ]
        
        groups = group_by_conflicts(tool_calls)
        
        # Should be split into groups: tool1+tool2 can run together, tool3 separate
        assert len(groups) == 2
        
        # Find the group sizes
        group_sizes = [len(g) for g in groups]
        group_sizes.sort()
        assert group_sizes == [1, 2]
    
    def test_group_single_tool(self):
        """Test grouping with single tool."""
        tool_calls = [
            ToolCall("write_file", {"path": "/tmp/test.txt"}, "1"),
        ]
        
        groups = group_by_conflicts(tool_calls)
        assert len(groups) == 1
        assert len(groups[0]) == 1
    
    def test_group_empty_list(self):
        """Test grouping with empty list."""
        groups = group_by_conflicts([])
        assert groups == []


class TestPathArgNames:
    
    def test_various_path_arg_names(self):
        """Test that various path argument names are recognized."""
        path_args = ["path", "file_path", "filepath", "dest", "target", 
                    "source", "output", "filename", "directory"]
        
        for arg_name in path_args:
            tool_call = ToolCall(
                function_name="write_file",
                arguments={arg_name: "/tmp/test.txt"},
                tool_call_id="1"
            )
            
            paths = extract_paths(tool_call)
            assert len(paths) == 1, f"Failed for arg name: {arg_name}"


class TestWriteToolNames:
    
    def test_various_write_tool_names(self):
        """Test that various write tool names are recognized."""
        write_tools = ["write_file", "edit_file", "create_file", "delete_file",
                      "mkdir", "save_file", "file_write", "file_edit"]
        
        for tool_name in write_tools:
            tool_call = ToolCall(
                function_name=tool_name,
                arguments={"path": "/tmp/test.txt"},
                tool_call_id="1"
            )
            
            paths = extract_paths(tool_call)
            assert len(paths) == 1, f"Failed for tool: {tool_name}"