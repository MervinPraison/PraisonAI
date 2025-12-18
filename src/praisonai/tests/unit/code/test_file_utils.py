"""
Tests for praisonai.code.utils.file_utils module.
"""

import os
import tempfile


class TestAddLineNumbers:
    """Tests for add_line_numbers function."""
    
    def test_add_line_numbers_basic(self):
        """Test basic line number addition."""
        from praisonai.code.utils.file_utils import add_line_numbers
        
        content = "line1\nline2\nline3"
        result = add_line_numbers(content)
        
        assert "1 | line1" in result
        assert "2 | line2" in result
        assert "3 | line3" in result
    
    def test_add_line_numbers_custom_start(self):
        """Test line numbers with custom start."""
        from praisonai.code.utils.file_utils import add_line_numbers
        
        content = "line1\nline2"
        result = add_line_numbers(content, start_line=10)
        
        assert "10 | line1" in result
        assert "11 | line2" in result
    
    def test_add_line_numbers_empty(self):
        """Test with empty content."""
        from praisonai.code.utils.file_utils import add_line_numbers
        
        result = add_line_numbers("")
        assert result == ""
    
    def test_add_line_numbers_single_line(self):
        """Test with single line."""
        from praisonai.code.utils.file_utils import add_line_numbers
        
        result = add_line_numbers("hello")
        assert "1 | hello" in result


class TestStripLineNumbers:
    """Tests for strip_line_numbers function."""
    
    def test_strip_line_numbers_basic(self):
        """Test basic line number stripping."""
        from praisonai.code.utils.file_utils import strip_line_numbers
        
        content = "  1 | line1\n  2 | line2"
        result = strip_line_numbers(content)
        
        assert result == "line1\nline2"
    
    def test_strip_line_numbers_no_numbers(self):
        """Test with content that has no line numbers."""
        from praisonai.code.utils.file_utils import strip_line_numbers
        
        content = "line1\nline2"
        result = strip_line_numbers(content)
        
        assert result == "line1\nline2"
    
    def test_strip_line_numbers_tab_separator(self):
        """Test with tab separator."""
        from praisonai.code.utils.file_utils import strip_line_numbers
        
        content = "1\tline1\n2\tline2"
        result = strip_line_numbers(content)
        
        assert result == "line1\nline2"


class TestEveryLineHasLineNumbers:
    """Tests for every_line_has_line_numbers function."""
    
    def test_all_lines_have_numbers(self):
        """Test when all lines have numbers."""
        from praisonai.code.utils.file_utils import every_line_has_line_numbers
        
        content = "  1 | line1\n  2 | line2"
        assert every_line_has_line_numbers(content) is True
    
    def test_no_lines_have_numbers(self):
        """Test when no lines have numbers."""
        from praisonai.code.utils.file_utils import every_line_has_line_numbers
        
        content = "line1\nline2"
        assert every_line_has_line_numbers(content) is False
    
    def test_mixed_lines(self):
        """Test when some lines have numbers."""
        from praisonai.code.utils.file_utils import every_line_has_line_numbers
        
        content = "  1 | line1\nline2"
        assert every_line_has_line_numbers(content) is False
    
    def test_empty_content(self):
        """Test with empty content."""
        from praisonai.code.utils.file_utils import every_line_has_line_numbers
        
        assert every_line_has_line_numbers("") is False


class TestNormalizeLineEndings:
    """Tests for normalize_line_endings function."""
    
    def test_normalize_crlf_to_lf(self):
        """Test converting CRLF to LF."""
        from praisonai.code.utils.file_utils import normalize_line_endings
        
        content = "line1\r\nline2\r\n"
        result = normalize_line_endings(content, '\n')
        
        assert result == "line1\nline2\n"
        assert '\r' not in result
    
    def test_normalize_lf_to_crlf(self):
        """Test converting LF to CRLF."""
        from praisonai.code.utils.file_utils import normalize_line_endings
        
        content = "line1\nline2\n"
        result = normalize_line_endings(content, '\r\n')
        
        assert result == "line1\r\nline2\r\n"


class TestIsBinaryFile:
    """Tests for is_binary_file function."""
    
    def test_text_file(self):
        """Test with a text file."""
        from praisonai.code.utils.file_utils import is_binary_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello, world!")
            temp_path = f.name
        
        try:
            assert is_binary_file(temp_path) is False
        finally:
            os.unlink(temp_path)
    
    def test_binary_file(self):
        """Test with a binary file."""
        from praisonai.code.utils.file_utils import is_binary_file
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            f.write(b'\x00\x01\x02\x03\x04\x05')
            temp_path = f.name
        
        try:
            assert is_binary_file(temp_path) is True
        finally:
            os.unlink(temp_path)


class TestFileExists:
    """Tests for file_exists function."""
    
    def test_existing_file(self):
        """Test with existing file."""
        from praisonai.code.utils.file_utils import file_exists
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            assert file_exists(temp_path) is True
        finally:
            os.unlink(temp_path)
    
    def test_nonexistent_file(self):
        """Test with nonexistent file."""
        from praisonai.code.utils.file_utils import file_exists
        
        assert file_exists("/nonexistent/path/file.txt") is False
    
    def test_directory(self):
        """Test with directory (should return False)."""
        from praisonai.code.utils.file_utils import file_exists
        
        with tempfile.TemporaryDirectory() as temp_dir:
            assert file_exists(temp_dir) is False


class TestIsPathWithinDirectory:
    """Tests for is_path_within_directory function."""
    
    def test_path_within(self):
        """Test path within directory."""
        from praisonai.code.utils.file_utils import is_path_within_directory
        
        assert is_path_within_directory("/home/user/project/file.py", "/home/user/project") is True
    
    def test_path_outside(self):
        """Test path outside directory."""
        from praisonai.code.utils.file_utils import is_path_within_directory
        
        assert is_path_within_directory("/home/other/file.py", "/home/user/project") is False
    
    def test_path_traversal(self):
        """Test path traversal attempt."""
        from praisonai.code.utils.file_utils import is_path_within_directory
        
        # This should resolve to /home/other, which is outside /home/user/project
        assert is_path_within_directory("/home/user/project/../other/file.py", "/home/user/project") is False


class TestCreateDirectoriesForFile:
    """Tests for create_directories_for_file function."""
    
    def test_create_directories(self):
        """Test creating directories for a file path."""
        from praisonai.code.utils.file_utils import create_directories_for_file
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "subdir1", "subdir2", "file.txt")
            
            result = create_directories_for_file(file_path)
            
            assert result is True
            assert os.path.isdir(os.path.dirname(file_path))
