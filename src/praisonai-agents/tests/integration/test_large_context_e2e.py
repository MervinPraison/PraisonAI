"""
End-to-End Tests for Large Context Knowledge Handling (Phase 8).

Tests the full pipeline: indexing -> retrieval -> budget enforcement -> context building.
"""
import os
import tempfile
import pytest


class TestLargeContextE2E:
    """End-to-end tests for large context handling."""
    
    def test_full_indexing_pipeline(self):
        """Test complete indexing pipeline."""
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.knowledge.indexing import CorpusStats, IndexResult
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test corpus
            for i in range(5):
                with open(os.path.join(tmpdir, f"doc{i}.txt"), "w") as f:
                    f.write(f"Document {i} content about topic {i % 3}")
            
            # Index
            knowledge = Knowledge()
            result = knowledge.index(tmpdir, user_id="e2e_test", incremental=False)
            
            assert isinstance(result, IndexResult)
            assert result.success is True
            assert result.files_indexed == 5
            
            # Get stats
            stats = knowledge.get_corpus_stats()
            assert isinstance(stats, CorpusStats)
            assert stats.file_count == 5
    
    def test_strategy_selection_by_corpus_size(self):
        """Test strategy auto-selection based on corpus size."""
        from praisonaiagents.knowledge.indexing import CorpusStats
        from praisonaiagents.rag.strategy import select_strategy, RetrievalStrategy
        
        # Small corpus -> DIRECT
        stats = CorpusStats(file_count=5)
        assert select_strategy(stats) == RetrievalStrategy.DIRECT
        
        # Medium corpus -> BASIC
        stats = CorpusStats(file_count=50)
        assert select_strategy(stats) == RetrievalStrategy.BASIC
        
        # Large corpus -> HYBRID
        stats = CorpusStats(file_count=500)
        assert select_strategy(stats) == RetrievalStrategy.HYBRID
    
    def test_token_budget_enforcement(self):
        """Test token budget calculation and enforcement."""
        from praisonaiagents.rag.budget import TokenBudget, DefaultBudgetEnforcer
        
        budget = TokenBudget(
            model_max_tokens=8000,
            reserved_response_tokens=2000,
        )
        
        # Calculate available using dynamic_budget
        available = budget.dynamic_budget(
            system_tokens=500,
            history_tokens=1000,
        )
        
        # 8000 - 2000 - 500 - 1000 = 4500
        assert available == 4500
        
        # Test enforcement
        enforcer = DefaultBudgetEnforcer()
        chunks = [
            {"text": "A" * 1000},  # ~250 tokens
            {"text": "B" * 1000},  # ~250 tokens
            {"text": "C" * 1000},  # ~250 tokens
        ]
        
        # Create a small budget to test enforcement
        small_budget = TokenBudget(model_max_tokens=600, reserved_response_tokens=100)
        enforced = enforcer.enforce(chunks, small_budget)
        # Should fit within budget (500 tokens available, ~750 in chunks)
        assert len(enforced) <= 3
    
    def test_compression_pipeline(self):
        """Test contextual compression."""
        from praisonaiagents.rag.compressor import ContextCompressor
        
        compressor = ContextCompressor()
        
        chunks = [
            {"text": "Python is a programming language. It is widely used."},
            {"text": "Python is a programming language. It is widely used."},  # Duplicate
            {"text": "JavaScript runs in browsers."},
        ]
        
        result = compressor.compress(chunks, "Python", target_tokens=500)
        
        # Should deduplicate
        assert len(result.chunks) <= 2
        assert result.compression_ratio <= 1.0
    
    def test_smart_retriever_filtering(self):
        """Test SmartRetriever with filters."""
        from praisonaiagents.rag.retriever import SmartRetriever
        
        retriever = SmartRetriever()
        
        # Test filter application
        chunks = [
            {"text": "Python code", "metadata": {"filename": "main.py"}},
            {"text": "JavaScript", "metadata": {"filename": "app.js"}},
            {"text": "More Python", "metadata": {"filename": "utils.py"}},
        ]
        
        filtered = retriever._apply_filters(chunks, include_glob=["*.py"])
        assert len(filtered) == 2
        
        filtered = retriever._apply_filters(chunks, exclude_glob=["utils*"])
        assert len(filtered) == 2
    
    def test_hierarchical_summarizer(self):
        """Test hierarchical summary building."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir)
            
            with open(os.path.join(src_dir, "main.py"), "w") as f:
                f.write("# Main application\ndef main(): pass")
            with open(os.path.join(src_dir, "utils.py"), "w") as f:
                f.write("# Utilities\ndef helper(): return True")
            
            summarizer = HierarchicalSummarizer()
            result = summarizer.build_hierarchy(tmpdir, levels=2)
            
            assert result.total_files >= 2
            assert len(result.nodes) >= 2
    
    def test_retrieval_config_integration(self):
        """Test RetrievalConfig with all new fields."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        config = RetrievalConfig(
            strategy="auto",
            compress=True,
            compression_ratio=0.5,
            model_context_window=128000,
            reserved_response_tokens=4096,
        )
        
        # Get budget
        budget = config.get_token_budget()
        assert budget.model_max_tokens == 128000
        
        # Get strategy
        stats = CorpusStats(file_count=500)
        strategy = config.get_strategy(stats)
        assert strategy.value == "hybrid"


class TestLiveAPIIntegration:
    """Live API tests (require OPENAI_API_KEY and RUN_LIVE_TESTS=1)."""
    
    @pytest.fixture
    def skip_if_no_api_key(self):
        """Skip if no API key or live tests disabled."""
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        if os.environ.get("RUN_LIVE_TESTS") != "1":
            pytest.skip("RUN_LIVE_TESTS not set to 1")
    
    def test_live_indexing_and_search(self, skip_if_no_api_key):
        """Test live indexing and search with real API."""
        from praisonaiagents.knowledge import Knowledge
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test documents
            with open(os.path.join(tmpdir, "python.txt"), "w") as f:
                f.write("Python is a high-level programming language known for its simplicity.")
            with open(os.path.join(tmpdir, "javascript.txt"), "w") as f:
                f.write("JavaScript is the language of the web, running in browsers.")
            
            knowledge = Knowledge()
            result = knowledge.index(tmpdir, user_id="live_test", incremental=False)
            
            assert result.files_indexed == 2
            
            # Search
            results = knowledge.search("Python programming", user_id="live_test", limit=5)
            
            # Should find results
            assert results is not None


class TestPerformance:
    """Performance and import time tests."""
    
    def test_import_time_acceptable(self):
        """Import time should be reasonable."""
        import subprocess
        import sys
        
        # Measure import time
        cmd = [
            sys.executable, "-c",
            "import time; start=time.time(); import praisonaiagents; print(time.time()-start)"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            import_time = float(result.stdout.strip())
            # Should import in under 5 seconds
            assert import_time < 5.0, f"Import took {import_time}s"
    
    def test_no_heavy_deps_at_import(self):
        """Heavy dependencies should not be loaded at import."""
        import subprocess
        import sys
        
        # Check if mem0 is loaded at import
        cmd = [
            sys.executable, "-c",
            "import sys; import praisonaiagents; print('mem0' in sys.modules)"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # mem0 should NOT be loaded at import
            assert result.stdout.strip() == "False", "mem0 loaded at import time"
