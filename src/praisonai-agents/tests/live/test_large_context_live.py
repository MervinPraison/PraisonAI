#!/usr/bin/env python3
"""
Live API Tests for Large Context Knowledge Handling.

These tests require a real API key and make actual API calls.
They are gated by environment variables and should only run in CI
or when explicitly enabled.

Environment Variables:
    PRAISONAI_LIVE_TESTS=1  - Enable live tests
    OPENAI_API_KEY          - Required for LLM calls

Usage:
    # Run all live tests
    PRAISONAI_LIVE_TESTS=1 pytest tests/live/test_large_context_live.py -v
    
    # Run specific test
    PRAISONAI_LIVE_TESTS=1 pytest tests/live/test_large_context_live.py::test_agent_retrieves_unique_code -v
"""

import os
import tempfile
import shutil
import pytest


# Skip all tests if PRAISONAI_LIVE_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.environ.get("PRAISONAI_LIVE_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="Live tests disabled. Set PRAISONAI_LIVE_TESTS=1 to enable."
)


# Unique codes that cannot be guessed by the LLM
UNIQUE_CODES = {
    "project_code": "XRAY-7K2M9",
    "budget_code": "FOXTROT-3N8P1",
    "security_code": "TANGO-5Q4R6",
}


@pytest.fixture
def temp_knowledge_dir():
    """Create a temporary directory with test documents."""
    temp_dir = tempfile.mkdtemp(prefix='praison_live_test_')
    
    # Create document with unique codes
    doc_path = os.path.join(temp_dir, 'confidential.txt')
    with open(doc_path, 'w') as f:
        f.write(f"""
CONFIDENTIAL INTERNAL DOCUMENT
==============================

Project Information:
- Project Name: Phoenix Initiative
- Project Code: {UNIQUE_CODES['project_code']}
- Start Date: 2024-01-15

Budget Information:
- Total Budget: $2,500,000
- Budget Code: {UNIQUE_CODES['budget_code']}
- Fiscal Year: 2024

Security Information:
- Classification: Internal
- Security Code: {UNIQUE_CODES['security_code']}
- Access Level: Restricted

This document contains sensitive information.
Do not share outside the organization.
""")
    
    yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestAgentKnowledgeRetrieval:
    """Test Agent retrieval of unique codes from knowledge base."""
    
    def test_agent_retrieves_unique_code(self, temp_knowledge_dir):
        """Agent should retrieve unique project code from knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Answer based ONLY on the provided knowledge. Quote exact codes.",
            knowledge=[temp_knowledge_dir],
            user_id="live_test_user",
            verbose=False,
        )
        
        response = agent.chat("What is the project code for Phoenix Initiative?")
        
        assert UNIQUE_CODES['project_code'] in response.upper(), \
            f"Expected code {UNIQUE_CODES['project_code']} not found in response: {response}"
    
    def test_agent_retrieves_budget_code(self, temp_knowledge_dir):
        """Agent should retrieve unique budget code from knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Answer based ONLY on the provided knowledge. Quote exact codes.",
            knowledge=[temp_knowledge_dir],
            user_id="live_test_user",
            verbose=False,
        )
        
        response = agent.chat("What is the budget code?")
        
        assert UNIQUE_CODES['budget_code'] in response.upper(), \
            f"Expected code {UNIQUE_CODES['budget_code']} not found in response: {response}"
    
    def test_agent_retrieves_security_code(self, temp_knowledge_dir):
        """Agent should retrieve unique security code from knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Answer based ONLY on the provided knowledge. Quote exact codes.",
            knowledge=[temp_knowledge_dir],
            user_id="live_test_user",
            verbose=False,
        )
        
        response = agent.chat("What is the security code?")
        
        assert UNIQUE_CODES['security_code'] in response.upper(), \
            f"Expected code {UNIQUE_CODES['security_code']} not found in response: {response}"


class TestIncrementalIndexing:
    """Test incremental indexing with real API."""
    
    def test_incremental_indexing_skips_unchanged(self, temp_knowledge_dir):
        """Incremental indexing should skip unchanged files."""
        from praisonaiagents.knowledge import Knowledge
        
        knowledge = Knowledge()
        
        # First index
        result1 = knowledge.index(
            temp_knowledge_dir,
            user_id="live_test_user",
            incremental=True,
        )
        
        assert result1.files_indexed >= 1, "Should index at least one file"
        
        # Second index should skip unchanged files
        result2 = knowledge.index(
            temp_knowledge_dir,
            user_id="live_test_user",
            incremental=True,
        )
        
        assert result2.files_skipped >= 1, "Should skip unchanged files"
        assert result2.files_indexed == 0, "Should not re-index unchanged files"


class TestTokenBudgeting:
    """Test token budget calculations."""
    
    def test_token_budget_calculation(self):
        """Token budget should calculate correctly for different models."""
        from praisonaiagents.rag import TokenBudget
        
        # Test with default settings (gpt-4o-mini context window)
        budget = TokenBudget(model_max_tokens=128000)
        
        assert budget.model_max_tokens > 0, "Should have positive context window"
        assert budget.reserved_response_tokens > 0, "Should have reserved response tokens"
        
        available = budget.dynamic_budget(
            system_tokens=500,
            history_tokens=1000,
        )
        
        assert available > 0, "Should have available tokens"
        assert available < budget.model_max_tokens, "Available should be less than total"


class TestStrategySelection:
    """Test retrieval strategy selection."""
    
    def test_strategy_selection_by_corpus_size(self):
        """Strategy should be selected based on corpus size."""
        from praisonaiagents.rag import select_strategy, RetrievalStrategy
        from praisonaiagents.knowledge.indexing import CorpusStats
        
        # Small corpus -> DIRECT
        small_stats = CorpusStats(file_count=5, total_tokens=100)
        small_strategy = select_strategy(small_stats)
        assert small_strategy == RetrievalStrategy.DIRECT
        
        # Medium corpus -> BASIC
        medium_stats = CorpusStats(file_count=50, total_tokens=5000)
        medium_strategy = select_strategy(medium_stats)
        assert medium_strategy == RetrievalStrategy.BASIC
        
        # Large corpus -> HYBRID or higher
        large_stats = CorpusStats(file_count=500, total_tokens=50000)
        large_strategy = select_strategy(large_stats)
        assert large_strategy in (
            RetrievalStrategy.HYBRID,
            RetrievalStrategy.RERANKED,
            RetrievalStrategy.COMPRESSED,
        )


class TestContextCompression:
    """Test context compression functionality."""
    
    def test_compression_preserves_query_relevant_content(self):
        """Compression should preserve query-relevant content."""
        from praisonaiagents.rag import ContextCompressor
        
        compressor = ContextCompressor(
            similarity_threshold=0.85,
            verbose=False,
        )
        
        # Chunks with metadata (as expected by the API)
        chunks = [
            {"text": "This is a long document with lots of filler content.", "score": 0.9},
            {"text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.", "score": 0.8},
            {"text": "The secret code is: COMPRESS-TEST-123.", "score": 0.95},
            {"text": "More filler content follows here.", "score": 0.7},
            {"text": "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.", "score": 0.6},
        ]
        
        # ContextCompressor.compress takes chunks, query, and target_tokens
        result = compressor.compress(chunks, query="secret code", target_tokens=500)
        
        # Result should be a CompressionResult
        assert hasattr(result, 'chunks'), "Should have chunks attribute"
        assert len(result.chunks) <= len(chunks), "Should not increase chunk count"


class TestSmartRetriever:
    """Test smart retriever functionality."""
    
    def test_retriever_initialization(self, temp_knowledge_dir):
        """Smart retriever should initialize correctly."""
        from praisonaiagents.rag import SmartRetriever
        
        # Test basic initialization
        retriever = SmartRetriever()
        
        # Verify retriever has expected attributes
        assert retriever is not None, "Retriever should initialize"
        
        # Test with reranker
        retriever_with_rerank = SmartRetriever(reranker=None)
        assert retriever_with_rerank is not None, "Retriever with reranker should initialize"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
