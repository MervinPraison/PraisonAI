"""Tests for multiedit tool."""
import os
import tempfile


class TestMultieditTool:
    """Tests for the multiedit tool."""
    
    def test_multiedit_single_file(self):
        """Multiedit can apply multiple edits to a single file."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    print('hello')\n\ndef world():\n    print('world')\n")
            filepath = f.name
        
        try:
            edits = [
                {"old": "print('hello')", "new": "print('Hello!')"},
                {"old": "print('world')", "new": "print('World!')"},
            ]
            
            result = multiedit(filepath, edits)
            
            assert result["success"] is True
            assert result["edits_applied"] == 2
            
            # Verify file content
            with open(filepath) as f:
                content = f.read()
            
            assert "print('Hello!')" in content
            assert "print('World!')" in content
        finally:
            os.unlink(filepath)
    
    def test_multiedit_with_line_hints(self):
        """Multiedit can use line number hints for faster matching."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\nline3\nline4\nline5\n")
            filepath = f.name
        
        try:
            edits = [
                {"old": "line2", "new": "LINE2", "line": 2},
                {"old": "line4", "new": "LINE4", "line": 4},
            ]
            
            result = multiedit(filepath, edits)
            
            assert result["success"] is True
            
            with open(filepath) as f:
                content = f.read()
            
            assert "LINE2" in content
            assert "LINE4" in content
        finally:
            os.unlink(filepath)
    
    def test_multiedit_preserves_indentation(self):
        """Multiedit preserves indentation."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def foo():\n    x = 1\n    y = 2\n")
            filepath = f.name
        
        try:
            edits = [
                {"old": "x = 1", "new": "x = 10"},
            ]
            
            result = multiedit(filepath, edits)
            
            with open(filepath) as f:
                content = f.read()
            
            # Indentation should be preserved
            assert "    x = 10" in content
        finally:
            os.unlink(filepath)
    
    def test_multiedit_partial_failure(self):
        """Multiedit reports partial failures."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("hello world\n")
            filepath = f.name
        
        try:
            edits = [
                {"old": "hello", "new": "HELLO"},
                {"old": "nonexistent", "new": "NOPE"},  # This won't match
            ]
            
            result = multiedit(filepath, edits)
            
            assert result["edits_applied"] == 1
            assert result["edits_failed"] == 1
        finally:
            os.unlink(filepath)
    
    def test_multiedit_dry_run(self):
        """Multiedit dry run doesn't modify file."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("original content\n")
            filepath = f.name
        
        try:
            edits = [
                {"old": "original", "new": "modified"},
            ]
            
            result = multiedit(filepath, edits, dry_run=True)
            
            assert result["success"] is True
            assert result["dry_run"] is True
            
            # File should be unchanged
            with open(filepath) as f:
                content = f.read()
            
            assert "original content" in content
        finally:
            os.unlink(filepath)
    
    def test_multiedit_returns_diff(self):
        """Multiedit returns diff of changes."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("old text\n")
            filepath = f.name
        
        try:
            edits = [
                {"old": "old text", "new": "new text"},
            ]
            
            result = multiedit(filepath, edits)
            
            assert "diff" in result
            assert "-old text" in result["diff"] or "old text" in result["diff"]
        finally:
            os.unlink(filepath)


class TestMultieditValidation:
    """Tests for multiedit input validation."""
    
    def test_multiedit_requires_file(self):
        """Multiedit requires a valid file path."""
        from praisonai.tools.multiedit import multiedit
        
        result = multiedit("/nonexistent/file.py", [{"old": "x", "new": "y"}])
        
        assert result["success"] is False
        assert "error" in result
    
    def test_multiedit_requires_edits(self):
        """Multiedit requires at least one edit."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("content\n")
            filepath = f.name
        
        try:
            result = multiedit(filepath, [])
            
            assert result["success"] is False
            assert "error" in result
        finally:
            os.unlink(filepath)
    
    def test_multiedit_validates_edit_format(self):
        """Multiedit validates edit format."""
        from praisonai.tools.multiedit import multiedit
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("content\n")
            filepath = f.name
        
        try:
            # Missing 'new' key
            result = multiedit(filepath, [{"old": "content"}])
            
            assert result["success"] is False
        finally:
            os.unlink(filepath)
