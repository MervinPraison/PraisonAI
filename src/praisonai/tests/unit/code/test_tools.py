"""
Tests for praisonai.code.tools module.
"""

import os
import tempfile


class TestReadFile:
    """Tests for read_file tool."""
    
    def test_read_entire_file(self):
        """Test reading entire file."""
        from praisonai.code.tools.read_file import read_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("line1\nline2\nline3")
            
            result = read_file(file_path, add_line_nums=False)
            
            assert result['success'] is True
            assert result['content'] == "line1\nline2\nline3"
            assert result['total_lines'] == 3
    
    def test_read_with_line_numbers(self):
        """Test reading with line numbers."""
        from praisonai.code.tools.read_file import read_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("line1\nline2\nline3")
            
            result = read_file(file_path, add_line_nums=True)
            
            assert result['success'] is True
            assert "1 | line1" in result['content']
            assert "2 | line2" in result['content']
    
    def test_read_line_range(self):
        """Test reading specific line range."""
        from praisonai.code.tools.read_file import read_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("line1\nline2\nline3\nline4\nline5")
            
            result = read_file(file_path, start_line=2, end_line=4, add_line_nums=False)
            
            assert result['success'] is True
            assert result['start_line'] == 2
            assert result['end_line'] == 4
            assert "line2" in result['content']
            assert "line4" in result['content']
            assert "line1" not in result['content']
            assert "line5" not in result['content']
    
    def test_read_nonexistent_file(self):
        """Test reading nonexistent file."""
        from praisonai.code.tools.read_file import read_file
        
        result = read_file("/nonexistent/path/file.txt")
        
        assert result['success'] is False
        assert "not found" in result['error'].lower()
    
    def test_read_with_workspace(self):
        """Test reading with workspace path."""
        from praisonai.code.tools.read_file import read_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "subdir", "test.txt")
            os.makedirs(os.path.dirname(file_path))
            with open(file_path, 'w') as f:
                f.write("content")
            
            result = read_file("subdir/test.txt", workspace=temp_dir, add_line_nums=False)
            
            assert result['success'] is True
            assert result['content'] == "content"
    
    def test_read_outside_workspace(self):
        """Test reading file outside workspace is blocked."""
        from praisonai.code.tools.read_file import read_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = read_file("../../../etc/passwd", workspace=temp_dir)
            
            assert result['success'] is False
            assert "outside" in result['error'].lower()


class TestWriteFile:
    """Tests for write_file tool."""
    
    def test_write_new_file(self):
        """Test writing a new file."""
        from praisonai.code.tools.write_file import write_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "new_file.txt")
            
            result = write_file(file_path, "Hello, World!")
            
            assert result['success'] is True
            assert result['created'] is True
            
            with open(file_path, 'r') as f:
                assert f.read() == "Hello, World!"
    
    def test_overwrite_existing_file(self):
        """Test overwriting an existing file."""
        from praisonai.code.tools.write_file import write_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "existing.txt")
            with open(file_path, 'w') as f:
                f.write("old content")
            
            result = write_file(file_path, "new content")
            
            assert result['success'] is True
            assert result['created'] is False
            
            with open(file_path, 'r') as f:
                assert f.read() == "new content"
    
    def test_create_directories(self):
        """Test creating parent directories."""
        from praisonai.code.tools.write_file import write_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "a", "b", "c", "file.txt")
            
            result = write_file(file_path, "content", create_directories=True)
            
            assert result['success'] is True
            assert os.path.exists(file_path)
    
    def test_strip_code_fences(self):
        """Test stripping markdown code fences."""
        from praisonai.code.tools.write_file import write_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.py")
            
            content = """```python
def hello():
    pass
```"""
            
            result = write_file(file_path, content, strip_code_fences=True)
            
            assert result['success'] is True
            
            with open(file_path, 'r') as f:
                saved_content = f.read()
            
            assert "```" not in saved_content
            assert "def hello():" in saved_content
    
    def test_write_with_backup(self):
        """Test writing with backup."""
        from praisonai.code.tools.write_file import write_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("original")
            
            result = write_file(file_path, "modified", backup=True)
            
            assert result['success'] is True
            assert result['backup_path'] is not None
            assert os.path.exists(result['backup_path'])
            
            with open(result['backup_path'], 'r') as f:
                assert f.read() == "original"


class TestListFiles:
    """Tests for list_files tool."""
    
    def test_list_files_basic(self):
        """Test basic file listing."""
        from praisonai.code.tools.list_files import list_files
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some files
            open(os.path.join(temp_dir, "file1.txt"), 'w').close()
            open(os.path.join(temp_dir, "file2.py"), 'w').close()
            os.makedirs(os.path.join(temp_dir, "subdir"))
            
            result = list_files(temp_dir)
            
            assert result['success'] is True
            assert len(result['files']) == 2
            assert len(result['directories']) == 1
    
    def test_list_files_recursive(self):
        """Test recursive file listing."""
        from praisonai.code.tools.list_files import list_files
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested structure
            os.makedirs(os.path.join(temp_dir, "a", "b"))
            open(os.path.join(temp_dir, "file1.txt"), 'w').close()
            open(os.path.join(temp_dir, "a", "file2.txt"), 'w').close()
            open(os.path.join(temp_dir, "a", "b", "file3.txt"), 'w').close()
            
            result = list_files(temp_dir, recursive=True)
            
            assert result['success'] is True
            assert len(result['files']) == 3
    
    def test_list_files_with_extension_filter(self):
        """Test filtering by extension."""
        from praisonai.code.tools.list_files import list_files
        
        with tempfile.TemporaryDirectory() as temp_dir:
            open(os.path.join(temp_dir, "file1.txt"), 'w').close()
            open(os.path.join(temp_dir, "file2.py"), 'w').close()
            open(os.path.join(temp_dir, "file3.py"), 'w').close()
            
            result = list_files(temp_dir, extensions=['py'])
            
            assert result['success'] is True
            assert len(result['files']) == 2
            assert all(f['name'].endswith('.py') for f in result['files'])
    
    def test_list_files_exclude_hidden(self):
        """Test excluding hidden files."""
        from praisonai.code.tools.list_files import list_files
        
        with tempfile.TemporaryDirectory() as temp_dir:
            open(os.path.join(temp_dir, "visible.txt"), 'w').close()
            open(os.path.join(temp_dir, ".hidden"), 'w').close()
            
            result = list_files(temp_dir, include_hidden=False)
            
            assert result['success'] is True
            assert len(result['files']) == 1
            assert result['files'][0]['name'] == "visible.txt"
    
    def test_list_files_max_limit(self):
        """Test max files limit."""
        from praisonai.code.tools.list_files import list_files
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create many files
            for i in range(10):
                open(os.path.join(temp_dir, f"file{i}.txt"), 'w').close()
            
            result = list_files(temp_dir, max_files=5)
            
            assert result['success'] is True
            assert result['total_count'] == 5
            assert result['truncated'] is True


class TestSearchReplace:
    """Tests for search_replace tool."""
    
    def test_simple_replace(self):
        """Test simple string replacement."""
        from praisonai.code.tools.search_replace import search_replace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("Hello, old world!")
            
            result = search_replace(file_path, [
                {'search': 'old', 'replace': 'new'}
            ])
            
            assert result['success'] is True
            assert result['total_replacements'] == 1
            
            with open(file_path, 'r') as f:
                assert f.read() == "Hello, new world!"
    
    def test_multiple_operations(self):
        """Test multiple search/replace operations."""
        from praisonai.code.tools.search_replace import search_replace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("foo bar foo baz")
            
            result = search_replace(file_path, [
                {'search': 'foo', 'replace': 'FOO'},
                {'search': 'bar', 'replace': 'BAR'},
            ])
            
            assert result['success'] is True
            assert result['operations_applied'] == 2
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            assert "FOO" in content
            assert "BAR" in content
    
    def test_regex_replace(self):
        """Test regex replacement."""
        from praisonai.code.tools.search_replace import search_replace
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("def func1(): pass\ndef func2(): pass")
            
            result = search_replace(file_path, [
                {'search': r'def (\w+)\(\)', 'replace': r'def renamed_\1()', 'is_regex': True}
            ])
            
            assert result['success'] is True
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            assert "renamed_func1" in content
            assert "renamed_func2" in content


class TestExecuteCommand:
    """Tests for execute_command tool."""
    
    def test_simple_command(self):
        """Test simple command execution."""
        from praisonai.code.tools.execute_command import execute_command
        
        result = execute_command("echo 'Hello, World!'")
        
        assert result['success'] is True
        assert result['exit_code'] == 0
        assert "Hello" in result['stdout']
    
    def test_command_with_cwd(self):
        """Test command with working directory."""
        from praisonai.code.tools.execute_command import execute_command
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = execute_command("pwd", cwd=temp_dir)
            
            assert result['success'] is True
            assert temp_dir in result['stdout'] or os.path.basename(temp_dir) in result['stdout']
    
    def test_command_failure(self):
        """Test command that fails."""
        from praisonai.code.tools.execute_command import execute_command
        
        result = execute_command("exit 1", shell=True)
        
        assert result['success'] is False
        assert result['exit_code'] == 1
    
    def test_command_timeout(self):
        """Test command timeout."""
        from praisonai.code.tools.execute_command import execute_command
        
        result = execute_command("sleep 10", timeout=1)
        
        assert result['success'] is False
        assert "timed out" in result['error'].lower()
    
    def test_is_safe_command(self):
        """Test safe command detection."""
        from praisonai.code.tools.execute_command import is_safe_command
        
        assert is_safe_command("ls -la") is True
        assert is_safe_command("echo hello") is True
        assert is_safe_command("rm -rf /") is False
        assert is_safe_command("sudo apt install") is False
