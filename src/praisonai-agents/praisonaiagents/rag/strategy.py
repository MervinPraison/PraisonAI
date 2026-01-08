"""
Retrieval Strategy Selection for PraisonAI Agents.

Provides corpus-aware strategy selection for optimal retrieval performance.
Strategies are selected based on corpus size and characteristics.

No heavy imports - only stdlib and typing.
"""

from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..knowledge.indexing import CorpusStats


class RetrievalStrategy(str, Enum):
    """
    Retrieval strategy levels based on corpus size and complexity.
    
    Each level adds more sophisticated retrieval techniques:
    - DIRECT: Load all content directly (tiny corpora)
    - BASIC: Semantic search only (small corpora)
    - HYBRID: Keyword + semantic search (medium corpora)
    - RERANKED: Hybrid + cross-encoder reranking (large corpora)
    - COMPRESSED: Reranked + contextual compression (very large corpora)
    - HIERARCHICAL: Summaries + routing (massive corpora)
    """
    DIRECT = "direct"
    BASIC = "basic"
    HYBRID = "hybrid"
    RERANKED = "reranked"
    COMPRESSED = "compressed"
    HIERARCHICAL = "hierarchical"


# Strategy thresholds based on file count
STRATEGY_THRESHOLDS: Dict[int, RetrievalStrategy] = {
    10: RetrievalStrategy.DIRECT,        # < 10 files
    100: RetrievalStrategy.BASIC,        # < 100 files
    1000: RetrievalStrategy.HYBRID,      # < 1000 files
    10000: RetrievalStrategy.RERANKED,   # < 10000 files
    100000: RetrievalStrategy.COMPRESSED, # < 100000 files
}
DEFAULT_STRATEGY = RetrievalStrategy.HIERARCHICAL  # >= 100000 files


# Strategy descriptions for logging and UI
STRATEGY_DESCRIPTIONS: Dict[RetrievalStrategy, str] = {
    RetrievalStrategy.DIRECT: "Direct loading - all content loaded into context (< 10 files)",
    RetrievalStrategy.BASIC: "Basic semantic search - embedding-based retrieval (< 100 files)",
    RetrievalStrategy.HYBRID: "Hybrid retrieval - keyword + semantic search (< 1000 files)",
    RetrievalStrategy.RERANKED: "Reranked retrieval - hybrid + cross-encoder reranking (< 10000 files)",
    RetrievalStrategy.COMPRESSED: "Compressed retrieval - reranked + contextual compression (< 100000 files)",
    RetrievalStrategy.HIERARCHICAL: "Hierarchical retrieval - summaries + top-down routing (>= 100000 files)",
}


def get_strategy_description(strategy: RetrievalStrategy) -> str:
    """
    Get human-readable description of a strategy.
    
    Args:
        strategy: The retrieval strategy
        
    Returns:
        Description string
    """
    return STRATEGY_DESCRIPTIONS.get(strategy, f"Unknown strategy: {strategy}")


def select_strategy(
    corpus_stats: "CorpusStats",
    override: Optional[str] = None,
) -> RetrievalStrategy:
    """
    Select optimal retrieval strategy based on corpus characteristics.
    
    Args:
        corpus_stats: Statistics about the indexed corpus
        override: Optional explicit strategy override ("auto" for auto-select)
        
    Returns:
        Selected RetrievalStrategy
    """
    # Handle explicit override
    if override and override != "auto":
        try:
            return RetrievalStrategy(override.lower())
        except ValueError:
            pass  # Fall through to auto-selection
    
    # Auto-select based on file count
    file_count = corpus_stats.file_count if corpus_stats else 0
    
    for threshold, strategy in sorted(STRATEGY_THRESHOLDS.items()):
        if file_count < threshold:
            return strategy
    
    return DEFAULT_STRATEGY


def get_strategy_config(strategy: RetrievalStrategy) -> Dict[str, Any]:
    """
    Get configuration parameters for a strategy.
    
    Args:
        strategy: The retrieval strategy
        
    Returns:
        Dict of configuration parameters
    """
    configs = {
        RetrievalStrategy.DIRECT: {
            "use_retrieval": False,
            "load_all": True,
            "top_k": None,
            "rerank": False,
            "compress": False,
            "use_hierarchy": False,
        },
        RetrievalStrategy.BASIC: {
            "use_retrieval": True,
            "load_all": False,
            "top_k": 5,
            "rerank": False,
            "compress": False,
            "use_hierarchy": False,
        },
        RetrievalStrategy.HYBRID: {
            "use_retrieval": True,
            "load_all": False,
            "top_k": 10,
            "use_keyword_search": True,
            "rerank": False,
            "compress": False,
            "use_hierarchy": False,
        },
        RetrievalStrategy.RERANKED: {
            "use_retrieval": True,
            "load_all": False,
            "top_k": 20,
            "rerank_top_k": 5,
            "use_keyword_search": True,
            "rerank": True,
            "compress": False,
            "use_hierarchy": False,
        },
        RetrievalStrategy.COMPRESSED: {
            "use_retrieval": True,
            "load_all": False,
            "top_k": 30,
            "rerank_top_k": 10,
            "use_keyword_search": True,
            "rerank": True,
            "compress": True,
            "compression_ratio": 0.5,
            "use_hierarchy": False,
        },
        RetrievalStrategy.HIERARCHICAL: {
            "use_retrieval": True,
            "load_all": False,
            "top_k": 50,
            "rerank_top_k": 15,
            "use_keyword_search": True,
            "rerank": True,
            "compress": True,
            "compression_ratio": 0.3,
            "use_hierarchy": True,
            "hierarchy_levels": 3,
        },
    }
    return configs.get(strategy, configs[RetrievalStrategy.BASIC])
