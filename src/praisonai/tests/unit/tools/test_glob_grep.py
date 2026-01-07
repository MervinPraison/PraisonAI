"""Tests for glob and grep tools."""
import os
import tempfile


class TestGlobTool:
    """Tests for the glob tool."""
    
    def test_glob_finds_files(self):
        """Glob finds files matching pattern."""
        from praisonai.tools.glob_tool import glob_files
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            open(os.path.join(tmpdir, "test1.py"), 'w').close()
            open(os.path.join(tmpdir, "test2.py"), 'w').close()
            open(os.path.join(tmpdir, "test.txt"), 'w').close()
            
            result = glob_files("*.py", directory=tmpdir)
            
            assert result["success"] is True
            assert len(result["files"]) == 2
            assert all(f.endswith(".py") for f in result["files"])
    
    def test_glob_recursive(self):
        """Glob can search recursively."""
        from praisonai.tools.glob_tool import glob_files
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)
            open(os.path.join(tmpdir, "root.py"), 'w').close()
            open(os.path.join(subdir, "nested.py"), 'w').close()
            
            result = glob_files("**/*.py", directory=tmpdir, recursive=True)
            
            assert result["success"] is True
            assert len(result["files"]) == 2
    
    def test_glob_no_matches(self):
        """Glob returns empty list when no matches."""
        from praisonai.tools.glob_tool import glob_files
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = glob_files("*.xyz", directory=tmpdir)
            
            assert result["success"] is True
            assert result["files"] == []
    
    def test_glob_with_exclude(self):
        """Glob can exclude patterns."""
        from praisonai.tools.glob_tool import glob_files
        
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "test.py"), 'w').close()
            open(os.path.join(tmpdir, "test_ignore.py"), 'w').close()
            
            result = glob_files("*.py", directory=tmpdir, exclude=["*_ignore*"])
            
            assert result["success"] is True
            assert len(result["files"]) == 1
            assert "test.py" in result["files"][0]
    
    def test_glob_returns_absolute_paths(self):
        """Glob returns absolute paths by default."""
        from praisonai.tools.glob_tool import glob_files
        
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "test.py"), 'w').close()
            
            result = glob_files("*.py", directory=tmpdir)
            
            assert result["success"] is True
            assert all(os.path.isabs(f) for f in result["files"])


class TestGrepTool:
    """Tests for the grep tool."""
    
    def test_grep_finds_pattern(self):
        """Grep finds lines matching pattern."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("def hello():\n    print('hello')\n\ndef world():\n    pass\n")
            
            result = grep_search("hello", directory=tmpdir)
            
            assert result["success"] is True
            assert len(result["matches"]) >= 1
    
    def test_grep_with_file_pattern(self):
        """Grep can filter by file pattern."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "test.py"), 'w') as f:
                f.write("hello python\n")
            with open(os.path.join(tmpdir, "test.txt"), 'w') as f:
                f.write("hello text\n")
            
            result = grep_search("hello", directory=tmpdir, include="*.py")
            
            assert result["success"] is True
            # Should only find in .py file
            assert all(".py" in m["file"] for m in result["matches"])
    
    def test_grep_case_insensitive(self):
        """Grep can search case-insensitively."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("Hello World\nhello world\nHELLO WORLD\n")
            
            result = grep_search("hello", directory=tmpdir, case_sensitive=False)
            
            assert result["success"] is True
            assert len(result["matches"]) == 3
    
    def test_grep_returns_context(self):
        """Grep can return context lines."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("line1\nline2\ntarget\nline4\nline5\n")
            
            result = grep_search("target", directory=tmpdir, context=1)
            
            assert result["success"] is True
            # Should include context
            match = result["matches"][0]
            assert "context_before" in match or "line2" in str(match)
    
    def test_grep_regex(self):
        """Grep supports regex patterns."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("def foo():\ndef bar():\ndef baz():\n")
            
            result = grep_search(r"def \w+\(\)", directory=tmpdir, regex=True)
            
            assert result["success"] is True
            assert len(result["matches"]) == 3
    
    def test_grep_max_results(self):
        """Grep can limit results."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("match\nmatch\nmatch\nmatch\nmatch\n")
            
            result = grep_search("match", directory=tmpdir, max_results=2)
            
            assert result["success"] is True
            assert len(result["matches"]) <= 2
    
    def test_grep_no_matches(self):
        """Grep returns empty when no matches."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("hello world\n")
            
            result = grep_search("nonexistent", directory=tmpdir)
            
            assert result["success"] is True
            assert result["matches"] == []


class TestGrepOutput:
    """Tests for grep output format."""
    
    def test_grep_match_includes_file(self):
        """Grep match includes file path."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("hello\n")
            
            result = grep_search("hello", directory=tmpdir)
            
            assert result["matches"][0]["file"].endswith("test.py")
    
    def test_grep_match_includes_line_number(self):
        """Grep match includes line number."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("line1\nhello\nline3\n")
            
            result = grep_search("hello", directory=tmpdir)
            
            assert result["matches"][0]["line_number"] == 2
    
    def test_grep_match_includes_content(self):
        """Grep match includes line content."""
        from praisonai.tools.grep_tool import grep_search
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, 'w') as f:
                f.write("hello world\n")
            
            result = grep_search("hello", directory=tmpdir)
            
            assert "hello world" in result["matches"][0]["content"]
