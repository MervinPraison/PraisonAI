"""
Tests for Fast Context result classes.
"""

import pytest
import time


class TestLineRange:
    """Tests for LineRange dataclass."""
    
    def test_line_range_creation(self):
        """Test basic LineRange creation."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr = LineRange(start=10, end=20)
        assert lr.start == 10
        assert lr.end == 20
        assert lr.content is None
        assert lr.relevance_score == 1.0
    
    def test_line_range_with_content(self):
        """Test LineRange with content."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr = LineRange(start=1, end=3, content="line1\nline2\nline3")
        assert lr.content == "line1\nline2\nline3"
    
    def test_line_range_invalid_start(self):
        """Test LineRange corrects invalid start."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr = LineRange(start=0, end=5)
        assert lr.start == 1  # Corrected to 1
    
    def test_line_range_invalid_end(self):
        """Test LineRange corrects invalid end."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr = LineRange(start=10, end=5)
        assert lr.end == 10  # Corrected to start
    
    def test_line_count(self):
        """Test line_count property."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr = LineRange(start=10, end=20)
        assert lr.line_count == 11
    
    def test_overlaps_true(self):
        """Test overlaps returns True for overlapping ranges."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr1 = LineRange(start=10, end=20)
        lr2 = LineRange(start=15, end=25)
        assert lr1.overlaps(lr2) is True
        assert lr2.overlaps(lr1) is True
    
    def test_overlaps_false(self):
        """Test overlaps returns False for non-overlapping ranges."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr1 = LineRange(start=10, end=20)
        lr2 = LineRange(start=25, end=30)
        assert lr1.overlaps(lr2) is False
    
    def test_overlaps_adjacent(self):
        """Test overlaps for adjacent ranges."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr1 = LineRange(start=10, end=20)
        lr2 = LineRange(start=21, end=30)
        assert lr1.overlaps(lr2) is False
    
    def test_merge(self):
        """Test merging overlapping ranges."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr1 = LineRange(start=10, end=20, relevance_score=0.8)
        lr2 = LineRange(start=15, end=25, relevance_score=0.9)
        merged = lr1.merge(lr2)
        
        assert merged.start == 10
        assert merged.end == 25
        assert merged.relevance_score == 0.9  # Max of both
    
    def test_merge_non_overlapping_raises(self):
        """Test merge raises for non-overlapping ranges."""
        from praisonaiagents.context.fast.result import LineRange
        
        lr1 = LineRange(start=10, end=20)
        lr2 = LineRange(start=25, end=30)
        
        with pytest.raises(ValueError):
            lr1.merge(lr2)


class TestFileMatch:
    """Tests for FileMatch dataclass."""
    
    def test_file_match_creation(self):
        """Test basic FileMatch creation."""
        from praisonaiagents.context.fast.result import FileMatch
        
        fm = FileMatch(path="/path/to/file.py")
        assert fm.path == "/path/to/file.py"
        assert fm.line_ranges == []
        assert fm.relevance_score == 1.0
        assert fm.match_count == 0
    
    def test_add_line_range(self):
        """Test adding line ranges."""
        from praisonaiagents.context.fast.result import FileMatch, LineRange
        
        fm = FileMatch(path="/path/to/file.py")
        fm.add_line_range(LineRange(start=10, end=20))
        
        assert len(fm.line_ranges) == 1
        assert fm.line_ranges[0].start == 10
    
    def test_add_overlapping_line_ranges(self):
        """Test adding overlapping line ranges merges them."""
        from praisonaiagents.context.fast.result import FileMatch, LineRange
        
        fm = FileMatch(path="/path/to/file.py")
        fm.add_line_range(LineRange(start=10, end=20))
        fm.add_line_range(LineRange(start=15, end=25))
        
        assert len(fm.line_ranges) == 1
        assert fm.line_ranges[0].start == 10
        assert fm.line_ranges[0].end == 25
    
    def test_add_non_overlapping_line_ranges(self):
        """Test adding non-overlapping line ranges keeps them separate."""
        from praisonaiagents.context.fast.result import FileMatch, LineRange
        
        fm = FileMatch(path="/path/to/file.py")
        fm.add_line_range(LineRange(start=10, end=20))
        fm.add_line_range(LineRange(start=30, end=40))
        
        assert len(fm.line_ranges) == 2
    
    def test_total_lines(self):
        """Test total_lines property."""
        from praisonaiagents.context.fast.result import FileMatch, LineRange
        
        fm = FileMatch(path="/path/to/file.py")
        fm.add_line_range(LineRange(start=10, end=20))  # 11 lines
        fm.add_line_range(LineRange(start=30, end=35))  # 6 lines
        
        assert fm.total_lines == 17


class TestFastContextResult:
    """Tests for FastContextResult dataclass."""
    
    def test_result_creation(self):
        """Test basic result creation."""
        from praisonaiagents.context.fast.result import FastContextResult
        
        result = FastContextResult(query="find authentication")
        assert result.query == "find authentication"
        assert result.files == []
        assert result.search_time_ms == 0
    
    def test_timer(self):
        """Test timer functionality."""
        from praisonaiagents.context.fast.result import FastContextResult
        
        result = FastContextResult()
        result.start_timer()
        time.sleep(0.1)  # 100ms
        result.stop_timer()
        
        assert result.search_time_ms >= 100
        assert result.search_time_ms < 200  # Should be close to 100ms
    
    def test_add_file(self):
        """Test adding files."""
        from praisonaiagents.context.fast.result import FastContextResult, FileMatch
        
        result = FastContextResult()
        result.add_file(FileMatch(path="/path/to/file.py"))
        
        assert result.total_files == 1
    
    def test_add_duplicate_file_merges(self):
        """Test adding duplicate file path merges them."""
        from praisonaiagents.context.fast.result import (
            FastContextResult, FileMatch, LineRange
        )
        
        result = FastContextResult()
        
        fm1 = FileMatch(path="/path/to/file.py", relevance_score=0.8)
        fm1.add_line_range(LineRange(start=10, end=20))
        result.add_file(fm1)
        
        fm2 = FileMatch(path="/path/to/file.py", relevance_score=0.9)
        fm2.add_line_range(LineRange(start=30, end=40))
        result.add_file(fm2)
        
        assert result.total_files == 1
        assert len(result.files[0].line_ranges) == 2
        assert result.files[0].relevance_score == 0.9
    
    def test_sort_by_relevance(self):
        """Test sorting files by relevance."""
        from praisonaiagents.context.fast.result import FastContextResult, FileMatch
        
        result = FastContextResult()
        result.add_file(FileMatch(path="/low.py", relevance_score=0.3))
        result.add_file(FileMatch(path="/high.py", relevance_score=0.9))
        result.add_file(FileMatch(path="/mid.py", relevance_score=0.6))
        
        result.sort_by_relevance()
        
        assert result.files[0].path == "/high.py"
        assert result.files[1].path == "/mid.py"
        assert result.files[2].path == "/low.py"
    
    def test_to_context_string(self):
        """Test converting result to context string."""
        from praisonaiagents.context.fast.result import (
            FastContextResult, FileMatch, LineRange
        )
        
        result = FastContextResult()
        fm = FileMatch(path="/path/to/file.py")
        fm.add_line_range(LineRange(start=10, end=20))
        result.add_file(fm)
        
        context = result.to_context_string()
        
        assert "1 relevant file" in context
        assert "/path/to/file.py" in context
        assert "Lines 10-20" in context
    
    def test_to_context_string_empty(self):
        """Test context string for empty result."""
        from praisonaiagents.context.fast.result import FastContextResult
        
        result = FastContextResult()
        context = result.to_context_string()
        
        assert "No relevant files found" in context
    
    def test_to_dict(self):
        """Test converting result to dictionary."""
        from praisonaiagents.context.fast.result import (
            FastContextResult, FileMatch, LineRange
        )
        
        result = FastContextResult(query="test", search_time_ms=100, turns_used=2)
        fm = FileMatch(path="/file.py", relevance_score=0.8)
        fm.add_line_range(LineRange(start=10, end=20))
        result.add_file(fm)
        
        d = result.to_dict()
        
        assert d["query"] == "test"
        assert d["search_time_ms"] == 100
        assert d["turns_used"] == 2
        assert len(d["files"]) == 1
        assert d["files"][0]["path"] == "/file.py"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
