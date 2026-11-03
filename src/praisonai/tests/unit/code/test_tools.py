"""
Tests for praisonai.code.tools module.
"""

import os
import tempfile
import pytest


class TestReadFile:
    """Tests for read_file tool."""
    
    def test_read_entire_file(self):
        """Test reading entire file."""
        from praisonai.code.tools.read_file import read_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("line1\nline2\nline3")
            
            result = read_file(file_path, workspace=temp_dir, add_line_nums=False)
            
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
            
            result = read_file(file_path, workspace=temp_dir, add_line_nums=True)
            
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
            
            result = read_file(file_path, workspace=temp_dir, start_line=2, end_line=4, add_line_nums=False)
            
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
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = read_file(
                os.path.join(temp_dir, "missing.txt"),
                workspace=temp_dir,
            )
            
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
            
            result = write_file(file_path, "Hello, World!", workspace=temp_dir)
            
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
            
            result = write_file(file_path, "new content", workspace=temp_dir)
            
            assert result['success'] is True
            assert result['created'] is False
            
            with open(file_path, 'r') as f:
                assert f.read() == "new content"
    
    def test_create_directories(self):
        """Test creating parent directories."""
        from praisonai.code.tools.write_file import write_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "a", "b", "c", "file.txt")
            
            result = write_file(file_path, "content", workspace=temp_dir, create_directories=True)
            
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
            
            result = write_file(file_path, content, workspace=temp_dir, strip_code_fences=True)
            
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
            
            result = write_file(file_path, "modified", workspace=temp_dir, backup=True)
            
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
            ], workspace=temp_dir)
            
            assert result['success'] is True
            assert result['total_replacements'] == 1
            
            with open(file_path, 'r') as f:
                assert f.read() == "Hello, new world!"

    def test_interrupted_write_keeps_original(self, monkeypatch):
        """A failure mid-write must not truncate the original file."""
        from praisonai.code.tools.search_replace import search_replace

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            with open(file_path, 'w') as f:
                f.write("Hello, old world!")

            def boom(*args, **kwargs):
                raise KeyboardInterrupt

            monkeypatch.setattr(os, "fsync", boom)
            try:
                search_replace(file_path, [
                    {'search': 'old', 'replace': 'new'}
                ], workspace=temp_dir)
            except KeyboardInterrupt:
                pass

            with open(file_path, 'r') as f:
                assert f.read() == "Hello, old world!"
            assert os.listdir(temp_dir) == ["test.txt"]

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
    def test_atomic_write_new_file_respects_umask(self):
        """New files get 0666 & ~umask like open(path, 'w'), not mkstemp's 0600."""
        from praisonai.code.utils.file_utils import atomic_write

        with tempfile.TemporaryDirectory() as temp_dir:
            old = os.umask(0o022)
            try:
                path = os.path.join(temp_dir, "new.txt")
                atomic_write(path, "x")
            finally:
                os.umask(old)
            assert (os.stat(path).st_mode & 0o777) == 0o644

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
    def test_atomic_write_does_not_touch_process_umask(self, monkeypatch):
        """os.umask is process-wide; changing it races with other threads."""
        from praisonai.code.utils.file_utils import atomic_write

        def no_umask(*args, **kwargs):
            raise AssertionError("atomic_write must not call os.umask")

        with tempfile.TemporaryDirectory() as temp_dir:
            monkeypatch.setattr(os, "umask", no_umask)
            new_path = os.path.join(temp_dir, "new.txt")
            atomic_write(new_path, "a")
            atomic_write(new_path, "b")
            with open(new_path) as f:
                assert f.read() == "b"
            assert os.listdir(temp_dir) == ["new.txt"]

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
    def test_atomic_write_writes_through_symlink(self):
        """Like open(path, 'w'), editing a symlink must update its target and keep the link."""
        from praisonai.code.utils.file_utils import atomic_write

        with tempfile.TemporaryDirectory() as temp_dir:
            real = os.path.join(temp_dir, "real.txt")
            link = os.path.join(temp_dir, "link.txt")
            with open(real, "w") as f:
                f.write("orig")
            try:
                os.symlink(real, link)
            except OSError:
                pytest.skip("cannot create symlink")
            atomic_write(link, "new")
            assert os.path.islink(link)
            with open(real) as f:
                assert f.read() == "new"
            assert sorted(os.listdir(temp_dir)) == ["link.txt", "real.txt"]

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
    def test_atomic_write_temp_file_never_wider_than_private_target(self, monkeypatch):
        """A 0600 target's new content must never sit in a more readable temp file."""
        import stat
        from praisonai.code.utils import file_utils

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, ".env")
            with open(path, "w") as f:
                f.write("OLD=1")
            os.chmod(path, 0o600)

            seen = []
            real_fdopen = os.fdopen

            def spy_fdopen(fd, *a, **kw):
                seen.append(stat.S_IMODE(os.fstat(fd).st_mode))
                return real_fdopen(fd, *a, **kw)

            monkeypatch.setattr(file_utils.os, "fdopen", spy_fdopen)
            file_utils.atomic_write(path, "NEW=2")

            assert seen and all(m & 0o077 == 0 for m in seen), seen
            assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
            with open(path) as f:
                assert f.read() == "NEW=2"

    @pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="POSIX permissions; root bypasses them")
    def test_atomic_write_refuses_read_only_target(self):
        """Like open(path, 'w'), a read-only file must not be replaced via inode swap."""
        from praisonai.code.utils.file_utils import atomic_write

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "locked.txt")
            with open(path, "w") as f:
                f.write("orig")
            os.chmod(path, 0o444)
            try:
                with pytest.raises(PermissionError):
                    atomic_write(path, "new")
                with open(path) as f:
                    assert f.read() == "orig"
                assert os.listdir(temp_dir) == ["locked.txt"]
            finally:
                os.chmod(path, 0o644)

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
            ], workspace=temp_dir)
            
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
            ], workspace=temp_dir)
            
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
        
        result = execute_command("false", shell=False)
        
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
