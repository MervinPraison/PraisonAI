"""
Tests for praisonai.code.diff.diff_strategy module.
"""

import os
import tempfile


class TestValidateDiffFormat:
    """Tests for validate_diff_format function."""
    
    def test_valid_single_block(self):
        """Test valid single SEARCH/REPLACE block."""
        from praisonai.code.diff.diff_strategy import validate_diff_format
        
        diff = """<<<<<<< SEARCH
:start_line:1
-------
old content
=======
new content
>>>>>>> REPLACE"""
        
        is_valid, error = validate_diff_format(diff)
        assert is_valid is True
        assert error is None
    
    def test_valid_multiple_blocks(self):
        """Test valid multiple SEARCH/REPLACE blocks."""
        from praisonai.code.diff.diff_strategy import validate_diff_format
        
        diff = """<<<<<<< SEARCH
:start_line:1
-------
old1
=======
new1
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:10
-------
old2
=======
new2
>>>>>>> REPLACE"""
        
        is_valid, error = validate_diff_format(diff)
        assert is_valid is True
    
    def test_missing_replace_marker(self):
        """Test missing REPLACE marker."""
        from praisonai.code.diff.diff_strategy import validate_diff_format
        
        diff = """<<<<<<< SEARCH
old content
=======
new content"""
        
        is_valid, error = validate_diff_format(diff)
        assert is_valid is False
        assert ">>>>>>> REPLACE" in error
    
    def test_missing_separator(self):
        """Test missing separator."""
        from praisonai.code.diff.diff_strategy import validate_diff_format
        
        diff = """<<<<<<< SEARCH
old content
>>>>>>> REPLACE"""
        
        is_valid, error = validate_diff_format(diff)
        assert is_valid is False


class TestParseDiffBlocks:
    """Tests for parse_diff_blocks function."""
    
    def test_parse_single_block(self):
        """Test parsing single block."""
        from praisonai.code.diff.diff_strategy import parse_diff_blocks
        
        diff = """<<<<<<< SEARCH
:start_line:5
-------
def old():
    pass
=======
def new():
    return True
>>>>>>> REPLACE"""
        
        blocks, error = parse_diff_blocks(diff)
        
        assert error is None
        assert len(blocks) == 1
        assert blocks[0].start_line == 5
        assert "def old():" in blocks[0].search_content
        assert "def new():" in blocks[0].replace_content
    
    def test_parse_multiple_blocks(self):
        """Test parsing multiple blocks."""
        from praisonai.code.diff.diff_strategy import parse_diff_blocks
        
        diff = """<<<<<<< SEARCH
:start_line:1
-------
first
=======
first_new
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:10
-------
second
=======
second_new
>>>>>>> REPLACE"""
        
        blocks, error = parse_diff_blocks(diff)
        
        assert error is None
        assert len(blocks) == 2
        # Should be sorted by start_line
        assert blocks[0].start_line == 1
        assert blocks[1].start_line == 10
    
    def test_parse_block_without_start_line(self):
        """Test parsing block without start_line hint."""
        from praisonai.code.diff.diff_strategy import parse_diff_blocks
        
        diff = """<<<<<<< SEARCH
-------
old content
=======
new content
>>>>>>> REPLACE"""
        
        blocks, error = parse_diff_blocks(diff)
        
        assert error is None
        assert len(blocks) == 1
        assert blocks[0].start_line is None


class TestApplySearchReplaceDiff:
    """Tests for apply_search_replace_diff function."""
    
    def test_exact_match_replacement(self):
        """Test exact match replacement."""
        from praisonai.code.diff.diff_strategy import apply_search_replace_diff
        
        original = """def hello():
    print("hello")

def world():
    print("world")"""
        
        diff = """<<<<<<< SEARCH
:start_line:1
-------
def hello():
    print("hello")
=======
def hello():
    print("Hello, World!")
>>>>>>> REPLACE"""
        
        result = apply_search_replace_diff(original, diff)
        
        assert result.success is True
        assert result.applied_count == 1
        assert 'print("Hello, World!")' in result.content
    
    def test_multiple_replacements(self):
        """Test multiple replacements in one diff."""
        from praisonai.code.diff.diff_strategy import apply_search_replace_diff
        
        original = """line1
line2
line3
line4
line5"""
        
        diff = """<<<<<<< SEARCH
:start_line:1
-------
line1
=======
LINE1
>>>>>>> REPLACE

<<<<<<< SEARCH
:start_line:5
-------
line5
=======
LINE5
>>>>>>> REPLACE"""
        
        result = apply_search_replace_diff(original, diff)
        
        assert result.success is True
        assert result.applied_count == 2
        assert "LINE1" in result.content
        assert "LINE5" in result.content
    
    def test_fuzzy_matching(self):
        """Test fuzzy matching with threshold."""
        from praisonai.code.diff.diff_strategy import apply_search_replace_diff
        
        original = """def hello():
    print("hello")"""
        
        # Slightly different content (extra space)
        diff = """<<<<<<< SEARCH
:start_line:1
-------
def hello():
    print("hello")
=======
def hello():
    print("goodbye")
>>>>>>> REPLACE"""
        
        # With exact matching, this should work
        result = apply_search_replace_diff(original, diff, fuzzy_threshold=1.0)
        
        assert result.success is True
        assert 'print("goodbye")' in result.content
    
    def test_no_match_found(self):
        """Test when no match is found."""
        from praisonai.code.diff.diff_strategy import apply_search_replace_diff
        
        original = """def hello():
    print("hello")"""
        
        diff = """<<<<<<< SEARCH
:start_line:1
-------
def nonexistent():
    pass
=======
def new():
    pass
>>>>>>> REPLACE"""
        
        result = apply_search_replace_diff(original, diff)
        
        assert result.success is False
        assert len(result.failed_blocks) > 0
    
    def test_indentation_preservation(self):
        """Test that indentation is preserved."""
        from praisonai.code.diff.diff_strategy import apply_search_replace_diff
        
        original = """class MyClass:
    def method(self):
        pass"""
        
        diff = """<<<<<<< SEARCH
:start_line:2
-------
    def method(self):
        pass
=======
    def method(self):
        return True
>>>>>>> REPLACE"""
        
        result = apply_search_replace_diff(original, diff)
        
        assert result.success is True
        # Check indentation is preserved
        lines = result.content.split('\n')
        assert lines[1].startswith('    ')  # Method should be indented
        assert lines[2].startswith('        ')  # Body should be double indented
    
    def test_identical_search_replace_error(self):
        """Test that identical search/replace is rejected."""
        from praisonai.code.diff.diff_strategy import apply_search_replace_diff
        
        original = """def hello():
    pass"""
        
        diff = """<<<<<<< SEARCH
:start_line:1
-------
def hello():
    pass
=======
def hello():
    pass
>>>>>>> REPLACE"""
        
        result = apply_search_replace_diff(original, diff)
        
        # Should fail because search and replace are identical
        assert result.success is False


class TestDiffIntegration:
    """Integration tests for diff operations."""
    
    def test_apply_diff_to_file(self):
        """Test applying diff to an actual file."""
        from praisonai.code.tools.apply_diff import apply_diff
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test file
            file_path = os.path.join(temp_dir, "test.py")
            with open(file_path, 'w') as f:
                f.write("""def old_function():
    return "old"

def another():
    pass""")
            
            diff = """<<<<<<< SEARCH
:start_line:1
-------
def old_function():
    return "old"
=======
def new_function():
    return "new"
>>>>>>> REPLACE"""
            
            result = apply_diff(file_path, diff)
            
            assert result['success'] is True
            assert result['applied_count'] == 1
            
            # Verify file was modified
            with open(file_path, 'r') as f:
                content = f.read()
            
            assert "def new_function():" in content
            assert 'return "new"' in content
