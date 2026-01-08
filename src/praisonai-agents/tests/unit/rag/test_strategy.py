"""
Unit tests for Strategy Selection (Phase 3).

Tests RetrievalStrategy enum, select_strategy(), and auto-strategy selection.
"""


class TestRetrievalStrategyEnum:
    """Tests for RetrievalStrategy enum."""
    
    def test_import_retrieval_strategy(self):
        """RetrievalStrategy should be importable."""
        from praisonaiagents.rag.strategy import RetrievalStrategy
        assert RetrievalStrategy is not None
    
    def test_all_strategy_levels(self):
        """RetrievalStrategy should have all levels."""
        from praisonaiagents.rag.strategy import RetrievalStrategy
        
        assert RetrievalStrategy.DIRECT.value == "direct"
        assert RetrievalStrategy.BASIC.value == "basic"
        assert RetrievalStrategy.HYBRID.value == "hybrid"
        assert RetrievalStrategy.RERANKED.value == "reranked"
        assert RetrievalStrategy.COMPRESSED.value == "compressed"
        assert RetrievalStrategy.HIERARCHICAL.value == "hierarchical"
    
    def test_strategy_from_string(self):
        """RetrievalStrategy should be creatable from string."""
        from praisonaiagents.rag.strategy import RetrievalStrategy
        
        assert RetrievalStrategy("direct") == RetrievalStrategy.DIRECT
        assert RetrievalStrategy("basic") == RetrievalStrategy.BASIC
        assert RetrievalStrategy("hybrid") == RetrievalStrategy.HYBRID


class TestSelectStrategy:
    """Tests for select_strategy() function."""
    
    def test_import_select_strategy(self):
        """select_strategy should be importable."""
        from praisonaiagents.rag.strategy import select_strategy
        assert select_strategy is not None
    
    def test_select_strategy_by_file_count(self):
        """select_strategy should select based on file count."""
        from praisonaiagents.rag.strategy import select_strategy, RetrievalStrategy
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        # Small corpus (< 10 files)
        stats = CorpusStats(file_count=5)
        assert select_strategy(stats) == RetrievalStrategy.DIRECT
        
        # Medium corpus (< 100 files)
        stats = CorpusStats(file_count=50)
        assert select_strategy(stats) == RetrievalStrategy.BASIC
        
        # Large corpus (< 1000 files)
        stats = CorpusStats(file_count=500)
        assert select_strategy(stats) == RetrievalStrategy.HYBRID
        
        # Very large corpus (< 10000 files)
        stats = CorpusStats(file_count=5000)
        assert select_strategy(stats) == RetrievalStrategy.RERANKED
        
        # Massive corpus (< 100000 files)
        stats = CorpusStats(file_count=50000)
        assert select_strategy(stats) == RetrievalStrategy.COMPRESSED
        
        # Huge corpus (>= 100000 files)
        stats = CorpusStats(file_count=500000)
        assert select_strategy(stats) == RetrievalStrategy.HIERARCHICAL
    
    def test_select_strategy_with_override(self):
        """select_strategy should respect explicit override."""
        from praisonaiagents.rag.strategy import select_strategy, RetrievalStrategy
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        stats = CorpusStats(file_count=5)  # Would normally be DIRECT
        
        # Override to RERANKED
        result = select_strategy(stats, override="reranked")
        assert result == RetrievalStrategy.RERANKED
    
    def test_select_strategy_auto(self):
        """select_strategy with 'auto' should auto-select."""
        from praisonaiagents.rag.strategy import select_strategy, RetrievalStrategy
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        stats = CorpusStats(file_count=500)
        result = select_strategy(stats, override="auto")
        assert result == RetrievalStrategy.HYBRID


class TestStrategyMetadata:
    """Tests for strategy metadata and descriptions."""
    
    def test_strategy_description(self):
        """Each strategy should have a description."""
        from praisonaiagents.rag.strategy import get_strategy_description, RetrievalStrategy
        
        desc = get_strategy_description(RetrievalStrategy.DIRECT)
        assert "direct" in desc.lower() or "load" in desc.lower()
        
        desc = get_strategy_description(RetrievalStrategy.HIERARCHICAL)
        assert "hierarchical" in desc.lower() or "summary" in desc.lower()
    
    def test_strategy_thresholds(self):
        """Strategy thresholds should be accessible."""
        from praisonaiagents.rag.strategy import STRATEGY_THRESHOLDS
        
        assert 10 in STRATEGY_THRESHOLDS
        assert 100 in STRATEGY_THRESHOLDS
        assert 1000 in STRATEGY_THRESHOLDS


class TestRetrievalConfigStrategy:
    """Tests for RetrievalConfig strategy integration."""
    
    def test_retrieval_config_has_strategy(self):
        """RetrievalConfig should have strategy field."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        
        config = RetrievalConfig()
        assert hasattr(config, "strategy")
        assert config.strategy == "auto"
    
    def test_retrieval_config_get_strategy(self):
        """RetrievalConfig should provide strategy selection."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        from praisonaiagents.rag.strategy import RetrievalStrategy
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        config = RetrievalConfig(strategy="auto")
        stats = CorpusStats(file_count=500)
        
        strategy = config.get_strategy(stats)
        assert strategy == RetrievalStrategy.HYBRID
    
    def test_retrieval_config_explicit_strategy(self):
        """RetrievalConfig should respect explicit strategy."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        from praisonaiagents.rag.strategy import RetrievalStrategy
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        config = RetrievalConfig(strategy="reranked")
        stats = CorpusStats(file_count=5)  # Would normally be DIRECT
        
        strategy = config.get_strategy(stats)
        assert strategy == RetrievalStrategy.RERANKED
