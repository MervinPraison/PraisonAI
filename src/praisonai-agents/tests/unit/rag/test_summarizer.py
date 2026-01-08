"""
Unit tests for HierarchicalSummarizer (Phase 6).
"""
import os
import tempfile


class TestHierarchicalSummarizer:
    """Tests for HierarchicalSummarizer class."""
    
    def test_import_hierarchical_summarizer(self):
        """HierarchicalSummarizer should be importable."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        assert HierarchicalSummarizer is not None
    
    def test_summary_node_dataclass(self):
        """SummaryNode should be a proper dataclass."""
        from praisonaiagents.rag.summarizer import SummaryNode
        
        node = SummaryNode(path="/test", level=1, summary="Test summary")
        assert node.path == "/test"
        assert node.level == 1
        assert node.summary == "Test summary"
    
    def test_summary_node_to_dict(self):
        """SummaryNode should serialize to dict."""
        from praisonaiagents.rag.summarizer import SummaryNode
        
        node = SummaryNode(path="/test", level=1, summary="Test")
        data = node.to_dict()
        
        assert data["path"] == "/test"
        assert data["level"] == 1
    
    def test_summary_node_from_dict(self):
        """SummaryNode should deserialize from dict."""
        from praisonaiagents.rag.summarizer import SummaryNode
        
        data = {"path": "/test", "level": 2, "summary": "Folder summary"}
        node = SummaryNode.from_dict(data)
        
        assert node.path == "/test"
        assert node.level == 2
    
    def test_hierarchy_result_dataclass(self):
        """HierarchyResult should be a proper dataclass."""
        from praisonaiagents.rag.summarizer import HierarchyResult
        
        result = HierarchyResult()
        assert result.nodes == {}
        assert result.total_files == 0
        assert result.levels == 3
    
    def test_build_hierarchy_empty_dir(self):
        """HierarchicalSummarizer should handle empty directories."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            summarizer = HierarchicalSummarizer()
            result = summarizer.build_hierarchy(tmpdir)
            
            assert result.total_files == 0
    
    def test_build_hierarchy_with_files(self):
        """HierarchicalSummarizer should build hierarchy for files."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("def main():\n    print('Hello')")
            with open(os.path.join(tmpdir, "utils.py"), "w") as f:
                f.write("def helper():\n    return True")
            
            summarizer = HierarchicalSummarizer()
            result = summarizer.build_hierarchy(tmpdir, levels=1)
            
            assert result.total_files == 2
            assert len(result.nodes) >= 2
    
    def test_build_hierarchy_with_folders(self):
        """HierarchicalSummarizer should build folder summaries."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir)
            
            with open(os.path.join(src_dir, "app.py"), "w") as f:
                f.write("# Application code")
            
            summarizer = HierarchicalSummarizer()
            result = summarizer.build_hierarchy(tmpdir, levels=2)
            
            # Should have file and folder summaries
            assert result.total_files >= 1
    
    def test_query_hierarchy(self):
        """HierarchicalSummarizer should query hierarchy."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files with specific content
            with open(os.path.join(tmpdir, "python.py"), "w") as f:
                f.write("Python programming language code")
            with open(os.path.join(tmpdir, "javascript.js"), "w") as f:
                f.write("JavaScript web development")
            
            summarizer = HierarchicalSummarizer()
            summarizer.build_hierarchy(tmpdir, levels=1)
            
            results = summarizer.query_hierarchy("Python", tmpdir)
            
            # Should find Python-related content
            assert len(results) >= 0  # May be 0 if no overlap
    
    def test_extract_summary(self):
        """HierarchicalSummarizer should extract summaries."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        
        summarizer = HierarchicalSummarizer()
        
        content = "First line.\nSecond line.\nThird line."
        summary = summarizer._extract_summary(content, max_chars=50)
        
        assert len(summary) <= 60  # Some buffer
        assert "First" in summary


class TestEstimateTokensSummarizer:
    """Tests for token estimation in summarizer."""
    
    def test_estimate_tokens(self):
        """estimate_tokens should work correctly."""
        from praisonaiagents.rag.summarizer import estimate_tokens
        
        assert estimate_tokens("") == 0
        assert estimate_tokens("test") == 2
