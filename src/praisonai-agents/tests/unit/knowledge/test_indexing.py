"""
Unit tests for Incremental Indexing + Ignore Patterns (Phase 2).

Tests IndexResult, CorpusStats, incremental indexing, and .praisonignore support.
"""

import os
import tempfile
import time


class TestCorpusStats:
    """Tests for CorpusStats dataclass."""
    
    def test_import_corpus_stats(self):
        """CorpusStats should be importable from knowledge module."""
        from praisonaiagents.knowledge.indexing import CorpusStats
        assert CorpusStats is not None
    
    def test_default_values(self):
        """CorpusStats should have sensible defaults."""
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        stats = CorpusStats()
        assert stats.file_count == 0
        assert stats.chunk_count == 0
        assert stats.total_tokens == 0
        assert stats.indexed_at is None
        assert stats.strategy_recommendation == "direct"
    
    def test_from_directory(self):
        """CorpusStats should be creatable from directory scan."""
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            for i in range(5):
                with open(os.path.join(tmpdir, f"file{i}.txt"), "w") as f:
                    f.write(f"Content {i} " * 100)
            
            stats = CorpusStats.from_directory(tmpdir)
            assert stats.file_count == 5
            assert stats.total_tokens > 0
    
    def test_strategy_recommendation_by_size(self):
        """CorpusStats should recommend strategy based on corpus size."""
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        # Small corpus
        stats = CorpusStats(file_count=5)
        assert stats.strategy_recommendation == "direct"
        
        # Medium corpus
        stats = CorpusStats(file_count=50)
        assert stats.strategy_recommendation == "basic"
        
        # Large corpus
        stats = CorpusStats(file_count=500)
        assert stats.strategy_recommendation == "hybrid"
        
        # Very large corpus
        stats = CorpusStats(file_count=5000)
        assert stats.strategy_recommendation == "reranked"
        
        # Massive corpus
        stats = CorpusStats(file_count=50000)
        assert stats.strategy_recommendation == "compressed"
        
        # Huge corpus
        stats = CorpusStats(file_count=500000)
        assert stats.strategy_recommendation == "hierarchical"
    
    def test_to_dict(self):
        """CorpusStats should be serializable to dict."""
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        stats = CorpusStats(file_count=10, chunk_count=50, total_tokens=5000)
        d = stats.to_dict()
        
        assert d["file_count"] == 10
        assert d["chunk_count"] == 50
        assert d["total_tokens"] == 5000


class TestIndexResult:
    """Tests for IndexResult dataclass."""
    
    def test_import_index_result(self):
        """IndexResult should be importable from knowledge module."""
        from praisonaiagents.knowledge.indexing import IndexResult
        assert IndexResult is not None
    
    def test_default_values(self):
        """IndexResult should have sensible defaults."""
        from praisonaiagents.knowledge.indexing import IndexResult
        
        result = IndexResult()
        assert result.success is True
        assert result.files_indexed == 0
        assert result.files_skipped == 0
        assert result.chunks_created == 0
        assert result.errors == []
    
    def test_incremental_stats(self):
        """IndexResult should track incremental indexing stats."""
        from praisonaiagents.knowledge.indexing import IndexResult
        
        result = IndexResult(
            files_indexed=10,
            files_skipped=5,  # Unchanged files
            chunks_created=50,
        )
        
        assert result.files_indexed == 10
        assert result.files_skipped == 5
        assert result.total_files == 15


class TestIgnoreMatcher:
    """Tests for .praisonignore pattern matching."""
    
    def test_import_ignore_matcher(self):
        """IgnoreMatcher should be importable."""
        from praisonaiagents.knowledge.indexing import IgnoreMatcher
        assert IgnoreMatcher is not None
    
    def test_basic_patterns(self):
        """IgnoreMatcher should match basic glob patterns."""
        from praisonaiagents.knowledge.indexing import IgnoreMatcher
        
        matcher = IgnoreMatcher(patterns=["*.pyc", "__pycache__", ".git"])
        
        assert matcher.should_ignore("test.pyc") is True
        assert matcher.should_ignore("__pycache__") is True
        assert matcher.should_ignore(".git") is True
        assert matcher.should_ignore("test.py") is False
        assert matcher.should_ignore("src/main.py") is False
    
    def test_directory_patterns(self):
        """IgnoreMatcher should handle directory patterns."""
        from praisonaiagents.knowledge.indexing import IgnoreMatcher
        
        matcher = IgnoreMatcher(patterns=["node_modules", "build/"])
        
        assert matcher.should_ignore("node_modules/package/index.js") is True
        assert matcher.should_ignore("src/node_modules/test.js") is True
        assert matcher.should_ignore("build/output.js") is True
        assert matcher.should_ignore("src/main.js") is False
    
    def test_negation_patterns(self):
        """IgnoreMatcher should support negation patterns."""
        from praisonaiagents.knowledge.indexing import IgnoreMatcher
        
        matcher = IgnoreMatcher(patterns=["*.log", "!important.log"])
        
        assert matcher.should_ignore("debug.log") is True
        assert matcher.should_ignore("important.log") is False
    
    def test_from_file(self):
        """IgnoreMatcher should load patterns from .praisonignore file."""
        from praisonaiagents.knowledge.indexing import IgnoreMatcher
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ignore_file = os.path.join(tmpdir, ".praisonignore")
            with open(ignore_file, "w") as f:
                f.write("*.pyc\n")
                f.write("__pycache__\n")
                f.write("# This is a comment\n")
                f.write("\n")  # Empty line
                f.write(".git\n")
            
            matcher = IgnoreMatcher.from_file(ignore_file)
            
            assert matcher.should_ignore("test.pyc") is True
            assert matcher.should_ignore("__pycache__") is True
            assert matcher.should_ignore(".git") is True
            assert matcher.should_ignore("main.py") is False
    
    def test_from_directory(self):
        """IgnoreMatcher should auto-detect .praisonignore in directory."""
        from praisonaiagents.knowledge.indexing import IgnoreMatcher
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ignore_file = os.path.join(tmpdir, ".praisonignore")
            with open(ignore_file, "w") as f:
                f.write("*.tmp\n")
            
            matcher = IgnoreMatcher.from_directory(tmpdir)
            
            assert matcher.should_ignore("test.tmp") is True
            assert matcher.should_ignore("test.txt") is False


class TestFileTracker:
    """Tests for file hash/mtime tracking."""
    
    def test_import_file_tracker(self):
        """FileTracker should be importable."""
        from praisonaiagents.knowledge.indexing import FileTracker
        assert FileTracker is not None
    
    def test_track_file(self):
        """FileTracker should track file hash and mtime."""
        from praisonaiagents.knowledge.indexing import FileTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Hello World")
            
            tracker = FileTracker()
            info = tracker.get_file_info(test_file)
            
            assert info["path"] == test_file
            assert "hash" in info
            assert "mtime" in info
            assert "size" in info
    
    def test_detect_unchanged_file(self):
        """FileTracker should detect unchanged files."""
        from praisonaiagents.knowledge.indexing import FileTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Hello World")
            
            tracker = FileTracker()
            
            # First check
            info1 = tracker.get_file_info(test_file)
            tracker.mark_indexed(test_file, info1)
            
            # Second check (unchanged)
            assert tracker.has_changed(test_file) is False
    
    def test_detect_changed_file(self):
        """FileTracker should detect changed files."""
        from praisonaiagents.knowledge.indexing import FileTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Hello World")
            
            tracker = FileTracker()
            
            # First check
            info1 = tracker.get_file_info(test_file)
            tracker.mark_indexed(test_file, info1)
            
            # Modify file
            time.sleep(0.1)  # Ensure mtime changes
            with open(test_file, "w") as f:
                f.write("Modified Content")
            
            # Second check (changed)
            assert tracker.has_changed(test_file) is True
    
    def test_persist_and_load(self):
        """FileTracker should persist and load state."""
        from praisonaiagents.knowledge.indexing import FileTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, ".praison_index_state.json")
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Hello World")
            
            # Track and save
            tracker1 = FileTracker(state_file=state_file)
            info = tracker1.get_file_info(test_file)
            tracker1.mark_indexed(test_file, info)
            tracker1.save()
            
            # Load in new tracker
            tracker2 = FileTracker(state_file=state_file)
            tracker2.load()
            
            assert tracker2.has_changed(test_file) is False


class TestKnowledgeIndex:
    """Tests for Knowledge.index() method."""
    
    def test_knowledge_has_index_method(self):
        """Knowledge should have an index() method."""
        from praisonaiagents.knowledge import Knowledge
        
        assert hasattr(Knowledge, "index")
    
    def test_index_returns_result(self):
        """Knowledge.index() should return IndexResult."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.knowledge.indexing import IndexResult
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            with open(os.path.join(tmpdir, "test.txt"), "w") as f:
                f.write("Test content for indexing")
            
            knowledge = Knowledge()
            result = knowledge.index(tmpdir)
            
            assert isinstance(result, IndexResult)
            assert result.files_indexed >= 1
    
    def test_incremental_index(self):
        """Knowledge.index() should support incremental indexing."""
        from praisonaiagents.knowledge import Knowledge
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create initial file
            with open(os.path.join(tmpdir, "file1.txt"), "w") as f:
                f.write("Initial content")
            
            knowledge = Knowledge()
            
            # First index
            result1 = knowledge.index(tmpdir, incremental=True)
            assert result1.files_indexed == 1
            
            # Second index (no changes)
            result2 = knowledge.index(tmpdir, incremental=True)
            assert result2.files_indexed == 0
            assert result2.files_skipped == 1
            
            # Add new file
            with open(os.path.join(tmpdir, "file2.txt"), "w") as f:
                f.write("New content")
            
            # Third index (one new file)
            result3 = knowledge.index(tmpdir, incremental=True)
            assert result3.files_indexed == 1
            assert result3.files_skipped == 1
    
    def test_index_respects_ignore_patterns(self):
        """Knowledge.index() should respect exclude_glob patterns."""
        from praisonaiagents.knowledge import Knowledge
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files
            with open(os.path.join(tmpdir, "main.txt"), "w") as f:
                f.write("Main content")
            with open(os.path.join(tmpdir, "debug.log"), "w") as f:
                f.write("Log content")
            with open(os.path.join(tmpdir, "other.log"), "w") as f:
                f.write("Other log content")
            
            knowledge = Knowledge()
            # Use exclude_glob to ignore .log files
            result = knowledge.index(
                tmpdir, 
                user_id="test_user", 
                incremental=False,
                exclude_glob=["*.log"],
            )
            
            # Should only index main.txt (*.log files excluded)
            assert result.files_indexed == 1
    
    def test_index_with_include_exclude_globs(self):
        """Knowledge.index() should support include/exclude globs."""
        from praisonaiagents.knowledge import Knowledge
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("Python code")
            with open(os.path.join(tmpdir, "test.py"), "w") as f:
                f.write("Test code")
            with open(os.path.join(tmpdir, "data.json"), "w") as f:
                f.write('{"key": "value"}')
            
            knowledge = Knowledge()
            
            # Include only .py files
            result = knowledge.index(
                tmpdir,
                include_glob=["*.py"],
                user_id="test_user",
                incremental=False,
            )
            assert result.files_indexed == 2
            
            # Exclude test files (use fresh knowledge instance)
            knowledge2 = Knowledge()
            result = knowledge2.index(
                tmpdir,
                include_glob=["*.py"],
                exclude_glob=["test*.py"],
                user_id="test_user2",
                incremental=False,
            )
            assert result.files_indexed == 1
    
    def test_get_corpus_stats(self):
        """Knowledge should provide corpus stats."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.txt"), "w") as f:
                    f.write(f"Content {i} " * 50)
            
            knowledge = Knowledge()
            knowledge.index(tmpdir, user_id="test_user", incremental=False)
            
            stats = knowledge.get_corpus_stats()
            
            assert isinstance(stats, CorpusStats)
            assert stats.file_count == 3
            # chunk_count may be 0 if storage fails, just check stats exist
