"""
Live smoke tests for Agent retrieval functionality.

These tests require real API keys and are gated by RUN_LIVE_TESTS=1.

Run with:
    RUN_LIVE_TESTS=1 python -m pytest tests/live/test_retrieval_live.py -v
"""

import os
import pytest
import tempfile
import shutil

# Skip all tests if RUN_LIVE_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="Live tests require RUN_LIVE_TESTS=1"
)


@pytest.fixture
def test_knowledge_dir():
    """Create a temporary directory with test documents."""
    temp_dir = tempfile.mkdtemp(prefix="praison_test_")
    
    # Create test document
    doc_content = """
    # Test Document
    
    This is a test document for retrieval testing.
    
    ## Key Points
    
    1. The capital of France is Paris.
    2. Python is a programming language.
    3. PraisonAI is an AI agents framework.
    
    ## Details
    
    Paris is known for the Eiffel Tower.
    Python was created by Guido van Rossum.
    PraisonAI supports multi-agent workflows.
    """
    
    with open(os.path.join(temp_dir, "test_doc.txt"), "w") as f:
        f.write(doc_content)
    
    yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestLiveRetrieval:
    """Live tests for retrieval functionality."""
    
    def test_agent_chat_with_knowledge(self, test_knowledge_dir):
        """Test Agent.chat() with knowledge retrieval."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Answer questions based on the provided knowledge. Be concise.",
            knowledge=[test_knowledge_dir],
            retrieval_config={
                "policy": "always",
                "top_k": 3,
            }
        )
        
        response = agent.chat("What is the capital of France?")
        
        assert response is not None
        assert len(response) > 0
        assert "Paris" in response or "paris" in response.lower()
    
    def test_agent_chat_skip_retrieval(self, test_knowledge_dir):
        """Test Agent.chat() with skip_retrieval=True."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="You are a helpful assistant.",
            knowledge=[test_knowledge_dir],
            retrieval_config={"policy": "always"}
        )
        
        # Skip retrieval - should still work but not use knowledge
        response = agent.chat("What is 2 + 2?", skip_retrieval=True)
        
        assert response is not None
        assert "4" in response
    
    def test_retrieval_config_policy_auto(self, test_knowledge_dir):
        """Test auto retrieval policy."""
        from praisonaiagents import Agent
        from praisonaiagents.rag.retrieval_config import RetrievalConfig, RetrievalPolicy
        
        config = RetrievalConfig(
            policy=RetrievalPolicy.AUTO,
            top_k=3,
        )
        
        agent = Agent(
            name="TestAgent",
            instructions="Answer questions based on knowledge when relevant.",
            knowledge=[test_knowledge_dir],
            retrieval_config=config,
        )
        
        # This should trigger retrieval (contains question keywords)
        response = agent.chat("What is PraisonAI?")
        
        assert response is not None
        assert len(response) > 0


class TestLiveExports:
    """Test that all exports work with real imports."""
    
    def test_all_exports_importable(self):
        """Test all retrieval-related exports are importable."""
        from praisonaiagents import (
            Agent,
            RetrievalConfig,
            RetrievalPolicy,
            CitationsMode,
            ContextPack,
            RAGResult,
            Citation,
        )
        
        assert Agent is not None
        assert RetrievalConfig is not None
        assert RetrievalPolicy is not None
        assert CitationsMode is not None
        assert ContextPack is not None
        assert RAGResult is not None
        assert Citation is not None
    
    def test_retrieval_config_creation(self):
        """Test RetrievalConfig can be created with various options."""
        from praisonaiagents import RetrievalConfig, RetrievalPolicy, CitationsMode
        
        config = RetrievalConfig(
            enabled=True,
            policy=RetrievalPolicy.ALWAYS,
            top_k=10,
            min_score=0.5,
            max_context_tokens=8000,
            rerank=True,
            hybrid=True,
            citations=True,
            citations_mode=CitationsMode.INLINE,
        )
        
        assert config.policy == RetrievalPolicy.ALWAYS
        assert config.top_k == 10
        assert config.rerank is True


if __name__ == "__main__":
    # Allow running directly with: python test_retrieval_live.py
    os.environ["RUN_LIVE_TESTS"] = "1"
    pytest.main([__file__, "-v"])
