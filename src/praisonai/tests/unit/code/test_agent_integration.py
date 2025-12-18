"""
Integration tests for praisonai.code agent tools.
"""

import os
import tempfile


class TestAgentTools:
    """Tests for agent-compatible tool wrappers."""
    
    def test_set_and_get_workspace(self):
        """Test setting and getting workspace."""
        from praisonai.code import set_workspace, get_workspace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            assert get_workspace() == temp_dir
    
    def test_code_read_file(self):
        """Test code_read_file agent tool."""
        from praisonai.code import code_read_file, set_workspace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            
            # Create test file
            file_path = os.path.join(temp_dir, "test.py")
            with open(file_path, 'w') as f:
                f.write("def hello():\n    print('hello')\n")
            
            result = code_read_file("test.py")
            
            assert "File: test.py" in result
            assert "def hello():" in result
            assert "1 |" in result  # Line numbers
    
    def test_code_write_file(self):
        """Test code_write_file agent tool."""
        from praisonai.code import code_write_file, set_workspace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            
            result = code_write_file("new_file.py", "print('hello')")
            
            assert "Created" in result
            assert os.path.exists(os.path.join(temp_dir, "new_file.py"))
    
    def test_code_list_files(self):
        """Test code_list_files agent tool."""
        from praisonai.code import code_list_files, set_workspace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            
            # Create some files
            open(os.path.join(temp_dir, "file1.py"), 'w').close()
            open(os.path.join(temp_dir, "file2.py"), 'w').close()
            os.makedirs(os.path.join(temp_dir, "subdir"))
            
            result = code_list_files(".")
            
            assert "file1.py" in result
            assert "file2.py" in result
            assert "subdir" in result
    
    def test_code_apply_diff(self):
        """Test code_apply_diff agent tool."""
        from praisonai.code import code_apply_diff, set_workspace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            
            # Create test file
            file_path = os.path.join(temp_dir, "test.py")
            with open(file_path, 'w') as f:
                f.write("def old_function():\n    return 'old'\n")
            
            diff = """<<<<<<< SEARCH
:start_line:1
-------
def old_function():
    return 'old'
=======
def new_function():
    return 'new'
>>>>>>> REPLACE"""
            
            result = code_apply_diff("test.py", diff)
            
            assert "Successfully applied" in result
            
            # Verify file was modified
            with open(file_path, 'r') as f:
                content = f.read()
            assert "def new_function():" in content
    
    def test_code_search_replace(self):
        """Test code_search_replace agent tool."""
        from praisonai.code import code_search_replace, set_workspace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            
            # Create test file
            file_path = os.path.join(temp_dir, "test.py")
            with open(file_path, 'w') as f:
                f.write("old_name = 'value'\nprint(old_name)\n")
            
            result = code_search_replace("test.py", "old_name", "new_name")
            
            assert "Replaced" in result
            assert "2" in result  # 2 occurrences
    
    def test_code_execute_command(self):
        """Test code_execute_command agent tool."""
        from praisonai.code import code_execute_command, set_workspace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            
            result = code_execute_command("echo 'Hello from test'")
            
            assert "completed successfully" in result
            assert "Hello" in result
    
    def test_code_tools_list(self):
        """Test CODE_TOOLS list contains all tools."""
        from praisonai.code import CODE_TOOLS
        
        assert len(CODE_TOOLS) == 6
        
        tool_names = [t.__name__ for t in CODE_TOOLS]
        assert "code_read_file" in tool_names
        assert "code_write_file" in tool_names
        assert "code_list_files" in tool_names
        assert "code_apply_diff" in tool_names
        assert "code_search_replace" in tool_names
        assert "code_execute_command" in tool_names


class TestDiffHelpers:
    """Tests for diff helper functions."""
    
    def test_create_diff_block(self):
        """Test creating a diff block."""
        from praisonai.code import create_diff_block
        
        diff = create_diff_block(
            search_content="old content",
            replace_content="new content",
            start_line=10,
        )
        
        assert "<<<<<<< SEARCH" in diff
        assert ":start_line:10" in diff
        assert "old content" in diff
        assert "=======" in diff
        assert "new content" in diff
        assert ">>>>>>> REPLACE" in diff
    
    def test_create_multi_diff(self):
        """Test creating multiple diff blocks."""
        from praisonai.code import create_multi_diff
        
        blocks = [
            {'search': 'old1', 'replace': 'new1', 'start_line': 5},
            {'search': 'old2', 'replace': 'new2', 'start_line': 20},
        ]
        
        diff = create_multi_diff(blocks)
        
        # Should contain two SEARCH/REPLACE blocks
        assert diff.count("<<<<<<< SEARCH") == 2
        assert diff.count(">>>>>>> REPLACE") == 2
        assert "old1" in diff
        assert "new1" in diff
        assert "old2" in diff
        assert "new2" in diff


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""
    
    def test_read_modify_write_workflow(self):
        """Test a complete read-modify-write workflow."""
        from praisonai.code import (
            set_workspace, code_read_file, code_apply_diff, code_execute_command
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            set_workspace(temp_dir)
            
            # Create a Python file
            file_path = os.path.join(temp_dir, "calculator.py")
            with open(file_path, 'w') as f:
                f.write('''def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

if __name__ == "__main__":
    print(add(2, 3))
''')
            
            # Read the file
            content = code_read_file("calculator.py")
            assert "def add(a, b):" in content
            
            # Apply a diff to add a multiply function
            diff = '''<<<<<<< SEARCH
:start_line:4
-------
def subtract(a, b):
    return a - b
=======
def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
>>>>>>> REPLACE'''
            
            result = code_apply_diff("calculator.py", diff)
            assert "Successfully applied" in result
            
            # Verify the change
            content = code_read_file("calculator.py")
            assert "def multiply(a, b):" in content
            
            # Run the file to verify it's valid Python
            result = code_execute_command("python calculator.py")
            assert "5" in result  # add(2, 3) = 5
