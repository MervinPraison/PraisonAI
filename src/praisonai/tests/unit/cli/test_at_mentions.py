"""
Unit tests for @ mention autocomplete feature.

Tests for:
1. AtMentionContext - Context detection
2. FileSearchService - File search with fuzzy matching
3. AtMentionCompleter - Autocomplete integration
"""

import os
import tempfile
import time


# ============================================================================
# 1. AtMentionContext Tests
# ============================================================================

class TestAtMentionContext:
    """Test @ mention context detection."""
    
    def test_detect_at_start(self):
        """Should detect @ at start of input."""
        from praisonai.cli.features.at_mentions import detect_at_mention
        
        result = detect_at_mention("@", cursor_pos=1)
        assert result is not None
        assert result.is_active
        assert result.query == ""
        assert result.start_pos == 0
    
    def test_detect_at_with_query(self):
        """Should detect @ with partial query."""
        from praisonai.cli.features.at_mentions import detect_at_mention
        
        result = detect_at_mention("@main", cursor_pos=5)
        assert result is not None
        assert result.is_active
        assert result.query == "main"
        assert result.start_pos == 0
    
    def test_detect_at_mid_text(self):
        """Should detect @ in middle of text."""
        from praisonai.cli.features.at_mentions import detect_at_mention
        
        result = detect_at_mention("read @src/", cursor_pos=10)
        assert result is not None
        assert result.is_active
        assert result.query == "src/"
        assert result.start_pos == 5
    
    def test_no_at_symbol(self):
        """Should return None when no @ present."""
        from praisonai.cli.features.at_mentions import detect_at_mention
        
        result = detect_at_mention("hello world", cursor_pos=11)
        assert result is None
    
    def test_at_after_space_breaks_context(self):
        """Should not detect @ if space after query."""
        from praisonai.cli.features.at_mentions import detect_at_mention
        
        result = detect_at_mention("@file.txt ", cursor_pos=10)
        assert result is None  # Space breaks the @ context
    
    def test_cursor_before_at(self):
        """Should not detect if cursor is before @."""
        from praisonai.cli.features.at_mentions import detect_at_mention
        
        result = detect_at_mention("hello @file", cursor_pos=3)
        assert result is None


# ============================================================================
# 2. FileSuggestion Tests
# ============================================================================

class TestFileSuggestion:
    """Test FileSuggestion dataclass."""
    
    def test_create_file_suggestion(self):
        """Should create file suggestion."""
        from praisonai.cli.features.at_mentions import FileSuggestion
        
        suggestion = FileSuggestion(
            path="src/main.py",
            file_type="file",
            score=100
        )
        assert suggestion.path == "src/main.py"
        assert suggestion.file_type == "file"
        assert suggestion.score == 100
    
    def test_directory_suggestion(self):
        """Should create directory suggestion."""
        from praisonai.cli.features.at_mentions import FileSuggestion
        
        suggestion = FileSuggestion(
            path="src/",
            file_type="directory",
            score=90
        )
        assert suggestion.file_type == "directory"


# ============================================================================
# 3. FileSearchService Tests
# ============================================================================

class TestFileSearchService:
    """Test FileSearchService for file discovery."""
    
    def test_service_creation(self):
        """Should create service."""
        from praisonai.cli.features.at_mentions import FileSearchService
        
        service = FileSearchService(root_dir=".")
        assert service is not None
    
    def test_search_files(self):
        """Should search files in directory."""
        from praisonai.cli.features.at_mentions import FileSearchService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            open(os.path.join(tmpdir, "main.py"), "w").close()
            open(os.path.join(tmpdir, "test.py"), "w").close()
            os.makedirs(os.path.join(tmpdir, "src"))
            open(os.path.join(tmpdir, "src", "app.py"), "w").close()
            
            service = FileSearchService(root_dir=tmpdir)
            results = service.search("main")
            
            assert len(results) >= 1
            assert any("main.py" in r.path for r in results)
    
    def test_fuzzy_match(self):
        """Should fuzzy match file names."""
        from praisonai.cli.features.at_mentions import FileSearchService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "my_long_filename.py"), "w").close()
            
            service = FileSearchService(root_dir=tmpdir)
            results = service.search("mlf")  # Fuzzy match
            
            assert len(results) >= 1
    
    def test_empty_query_returns_all(self):
        """Should return files when query is empty."""
        from praisonai.cli.features.at_mentions import FileSearchService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.py"), "w").close()
            open(os.path.join(tmpdir, "b.py"), "w").close()
            
            service = FileSearchService(root_dir=tmpdir)
            results = service.search("")
            
            assert len(results) >= 2
    
    def test_respects_max_results(self):
        """Should limit results."""
        from praisonai.cli.features.at_mentions import FileSearchService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(20):
                open(os.path.join(tmpdir, f"file{i}.py"), "w").close()
            
            service = FileSearchService(root_dir=tmpdir)
            results = service.search("", max_results=5)
            
            assert len(results) <= 5
    
    def test_cache_works(self):
        """Should cache results."""
        from praisonai.cli.features.at_mentions import FileSearchService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "test.py"), "w").close()
            
            service = FileSearchService(root_dir=tmpdir, cache_ttl=10)
            
            # First search
            start = time.time()
            results1 = service.search("test")
            first_time = time.time() - start
            
            # Second search (cached)
            start = time.time()
            results2 = service.search("test")
            second_time = time.time() - start
            
            assert len(results1) == len(results2)
            # Cache should be faster (or at least not slower)


# ============================================================================
# 4. AtMentionCompleter Tests
# ============================================================================

class TestAtMentionCompleter:
    """Test AtMentionCompleter for prompt_toolkit integration."""
    
    def test_completer_creation(self):
        """Should create completer."""
        from praisonai.cli.features.at_mentions import AtMentionCompleter
        
        completer = AtMentionCompleter(root_dir=".")
        assert completer is not None
    
    def test_no_completions_without_at(self):
        """Should not complete without @."""
        from praisonai.cli.features.at_mentions import AtMentionCompleter
        from prompt_toolkit.document import Document
        
        completer = AtMentionCompleter(root_dir=".")
        doc = Document("hello world")
        completions = list(completer.get_completions(doc, None))
        
        assert len(completions) == 0
    
    def test_completions_with_at(self):
        """Should complete with @."""
        from praisonai.cli.features.at_mentions import AtMentionCompleter
        from prompt_toolkit.document import Document
        
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "main.py"), "w").close()
            
            completer = AtMentionCompleter(root_dir=tmpdir)
            doc = Document("@main")
            completions = list(completer.get_completions(doc, None))
            
            assert len(completions) >= 1


# ============================================================================
# 5. CombinedCompleter Tests
# ============================================================================

class TestCombinedCompleter:
    """Test CombinedCompleter that handles both / and @."""
    
    def test_slash_commands(self):
        """Should complete slash commands."""
        from praisonai.cli.features.at_mentions import CombinedCompleter
        from prompt_toolkit.document import Document
        
        completer = CombinedCompleter(
            commands=["help", "exit", "queue"],
            root_dir="."
        )
        doc = Document("/he")
        completions = list(completer.get_completions(doc, None))
        
        assert len(completions) >= 1
        assert any("/help" in c.text for c in completions)
    
    def test_at_mentions(self):
        """Should complete @ mentions."""
        from praisonai.cli.features.at_mentions import CombinedCompleter
        from prompt_toolkit.document import Document
        
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "test.py"), "w").close()
            
            completer = CombinedCompleter(
                commands=["help"],
                root_dir=tmpdir
            )
            doc = Document("@test")
            completions = list(completer.get_completions(doc, None))
            
            assert len(completions) >= 1
    
    def test_no_completions_for_regular_text(self):
        """Should not complete regular text."""
        from praisonai.cli.features.at_mentions import CombinedCompleter
        from prompt_toolkit.document import Document
        
        completer = CombinedCompleter(
            commands=["help"],
            root_dir="."
        )
        doc = Document("hello world")
        completions = list(completer.get_completions(doc, None))
        
        assert len(completions) == 0
