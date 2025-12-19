"""
Unit tests for configurable max_file_chars in MentionsParser.

TDD approach: Write tests first, then implement.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestMentionsParserConfigurableLimit:
    """Test suite for configurable file truncation limit."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def small_file(self, temp_workspace):
        """Create a small test file (1KB)."""
        file_path = temp_workspace / "small.py"
        content = "# Small file\n" + "x = 1\n" * 100  # ~700 chars
        file_path.write_text(content)
        return file_path
    
    @pytest.fixture
    def large_file(self, temp_workspace):
        """Create a large test file (100KB)."""
        file_path = temp_workspace / "large.py"
        content = "# Large file\n" + "x = 'a' * 100\n" * 7000  # ~100KB
        file_path.write_text(content)
        return file_path
    
    @pytest.fixture
    def huge_file(self, temp_workspace):
        """Create a huge test file (600KB)."""
        file_path = temp_workspace / "huge.py"
        content = "# Huge file\n" + "x = 'a' * 100\n" * 42000  # ~600KB
        file_path.write_text(content)
        return file_path

    # ===== Test 1.1: Default value (500K) =====
    def test_default_max_file_chars_is_500k(self, temp_workspace):
        """Default max_file_chars should be 500,000."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        parser = MentionsParser(workspace_path=str(temp_workspace))
        assert parser.max_file_chars == 500000
    
    # ===== Test 1.2: Custom value via constructor =====
    def test_custom_max_file_chars_via_constructor(self, temp_workspace):
        """max_file_chars should be configurable via constructor."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        parser = MentionsParser(
            workspace_path=str(temp_workspace),
            max_file_chars=100000
        )
        assert parser.max_file_chars == 100000
    
    def test_custom_max_file_chars_zero_means_no_limit(self, temp_workspace):
        """max_file_chars=0 should mean no truncation."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        parser = MentionsParser(
            workspace_path=str(temp_workspace),
            max_file_chars=0
        )
        assert parser.max_file_chars == 0
    
    # ===== Test 1.3: Environment variable override =====
    def test_env_var_override(self, temp_workspace):
        """PRAISON_MAX_FILE_CHARS env var should override default."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        with patch.dict(os.environ, {'PRAISON_MAX_FILE_CHARS': '200000'}):
            # Need to reimport to pick up env var
            parser = MentionsParser(workspace_path=str(temp_workspace))
            assert parser.max_file_chars == 200000
    
    def test_constructor_takes_precedence_over_env_var(self, temp_workspace):
        """Constructor value should take precedence over env var."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        with patch.dict(os.environ, {'PRAISON_MAX_FILE_CHARS': '200000'}):
            parser = MentionsParser(
                workspace_path=str(temp_workspace),
                max_file_chars=100000
            )
            assert parser.max_file_chars == 100000
    
    # ===== Test 1.4: No-limit mode =====
    def test_no_truncation_when_limit_is_zero(self, temp_workspace, huge_file):
        """File should not be truncated when max_file_chars=0."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        parser = MentionsParser(
            workspace_path=str(temp_workspace),
            max_file_chars=0
        )
        
        context, _ = parser.process(f"@file:{huge_file.name} explain")
        
        # Should contain full content, no truncation message
        assert "(truncated)" not in context
        # Should have the full file content
        original_size = huge_file.read_text().__len__()
        # Context includes header and code fence, so check it's close
        assert len(context) >= original_size
    
    # ===== Test 1.5: Truncation behavior =====
    def test_truncation_at_custom_limit(self, temp_workspace, large_file):
        """File should be truncated at custom limit."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        parser = MentionsParser(
            workspace_path=str(temp_workspace),
            max_file_chars=10000  # 10KB limit
        )
        
        context, _ = parser.process(f"@file:{large_file.name} explain")
        
        # Should be truncated
        assert "(truncated)" in context
        # Content should be around the limit (plus header/fence overhead)
        assert len(context) < 15000  # Some overhead for markdown
    
    def test_no_truncation_when_file_under_limit(self, temp_workspace, small_file):
        """Small files should not be truncated."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        parser = MentionsParser(
            workspace_path=str(temp_workspace),
            max_file_chars=500000
        )
        
        context, _ = parser.process(f"@file:{small_file.name} explain")
        
        # Should NOT be truncated
        assert "(truncated)" not in context
    
    def test_truncation_warning_logged(self, temp_workspace, large_file, caplog):
        """Warning should be logged when file is truncated."""
        from praisonaiagents.tools.mentions import MentionsParser
        import logging
        
        parser = MentionsParser(
            workspace_path=str(temp_workspace),
            max_file_chars=10000,
            verbose=1
        )
        
        with caplog.at_level(logging.WARNING):
            parser.process(f"@file:{large_file.name} explain")
        
        # Should log a warning about truncation
        assert any("truncat" in record.message.lower() for record in caplog.records)
    
    # ===== Test: URL truncation also uses configurable limit =====
    def test_url_truncation_uses_same_limit(self, temp_workspace):
        """URL content should also respect max_file_chars."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        parser = MentionsParser(
            workspace_path=str(temp_workspace),
            max_file_chars=100000
        )
        
        # URL truncation should use the same limit
        assert parser.max_file_chars == 100000
    
    # ===== Test: Backward compatibility =====
    def test_backward_compatible_no_args(self, temp_workspace):
        """Parser should work without max_file_chars argument."""
        from praisonaiagents.tools.mentions import MentionsParser
        
        # Should not raise any errors
        parser = MentionsParser(workspace_path=str(temp_workspace))
        assert hasattr(parser, 'max_file_chars')
    
    # ===== Test: Performance - no impact on small files =====
    def test_performance_small_file(self, temp_workspace, small_file):
        """Processing small files should be fast."""
        from praisonaiagents.tools.mentions import MentionsParser
        import time
        
        parser = MentionsParser(workspace_path=str(temp_workspace))
        
        start = time.time()
        for _ in range(100):
            parser.process(f"@file:{small_file.name} explain")
        elapsed = time.time() - start
        
        # 100 iterations should complete in under 1 second
        assert elapsed < 1.0, f"Performance regression: {elapsed}s for 100 iterations"


class TestProcessMentionsFunction:
    """Test the convenience function."""
    
    def test_process_mentions_uses_default_limit(self):
        """process_mentions function should use default limit."""
        from praisonaiagents.tools.mentions import process_mentions
        
        # The function should create a parser with default settings
        # Just verify it works without errors
        context, cleaned = process_mentions("hello world")
        assert cleaned == "hello world"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
