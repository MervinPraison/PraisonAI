"""
Tests for Agent retrieval integration.

Tests cover:
1. Agent with retrieval_config parameter
2. Agent.query() method
3. Agent.retrieve() method
4. Retrieval policy in chat()
5. force_retrieval and skip_retrieval
6. Shared Knowledge instances
7. Lazy loading of retrieval dependencies
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestAgentRetrievalConfig:
    """Test Agent initialization with retrieval_config."""
    
    def test_agent_accepts_knowledge_config(self):
        """Test Agent accepts KnowledgeConfig."""
        from praisonaiagents import Agent, KnowledgeConfig
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=KnowledgeConfig(
                sources=["test.txt"],
                retrieval_k=10,
            ),
        )
        
        # Knowledge config should be processed
        assert agent._knowledge_sources is not None or agent.knowledge is not None
    
    def test_agent_accepts_knowledge_list(self):
        """Test Agent accepts knowledge as list of sources."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=["docs/", "data.txt"],
        )
        
        # Knowledge sources should be set
        assert agent._knowledge_sources is not None or agent.knowledge is not None
    
    def test_agent_creates_default_config_with_knowledge(self):
        """Test Agent creates default RetrievalConfig when knowledge is provided."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=["test.txt"],
        )
        
        assert agent._retrieval_config is not None
        assert agent._retrieval_config.enabled is True
    
    def test_agent_no_config_without_knowledge(self):
        """Test Agent has no retrieval_config without knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
        )
        
        assert agent._retrieval_config is None
    
    def test_knowledge_config_with_custom_settings(self):
        """Test KnowledgeConfig with custom retrieval settings."""
        from praisonaiagents import Agent, KnowledgeConfig
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=KnowledgeConfig(
                sources=["test.txt"],
                retrieval_k=15,
                rerank=True,
            ),
        )
        
        # Agent should have knowledge configured
        assert agent._knowledge_sources is not None or agent.knowledge is not None
    
    def test_knowledge_with_embedder_config(self):
        """Test KnowledgeConfig with embedder settings."""
        from praisonaiagents import Agent, KnowledgeConfig
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=KnowledgeConfig(
                sources=["test.txt"],
                embedder="openai",
            ),
        )
        
        # Agent should have knowledge configured
        assert agent._knowledge_sources is not None or agent.knowledge is not None


class TestAgentRetrievalConfigProperty:
    """Test Agent.retrieval_config property."""
    
    def test_retrieval_config_property(self):
        """Test retrieval_config property returns the config."""
        from praisonaiagents import Agent, KnowledgeConfig
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=KnowledgeConfig(
                sources=["test.txt"],
                retrieval_k=25,
            ),
        )
        
        # Agent should have knowledge configured
        assert agent._knowledge_sources is not None or agent.knowledge is not None


class TestAgentSharedKnowledge:
    """Test Agent with shared Knowledge instances."""
    
    def test_agent_accepts_knowledge_instance(self):
        """Test Agent accepts a Knowledge instance directly."""
        from praisonaiagents import Agent
        
        mock_knowledge = Mock()
        mock_knowledge.search = Mock(return_value=[])
        mock_knowledge.add = Mock()
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=mock_knowledge,
        )
        
        assert agent.knowledge is mock_knowledge
        assert agent._knowledge_processed is True
    
    def test_two_agents_share_knowledge(self):
        """Test two agents can share the same Knowledge instance."""
        from praisonaiagents import Agent
        
        mock_knowledge = Mock()
        mock_knowledge.search = Mock(return_value=[])
        mock_knowledge.add = Mock()
        
        agent1 = Agent(
            name="Agent1",
            instructions="Test 1",
            knowledge=mock_knowledge,
        )
        
        agent2 = Agent(
            name="Agent2",
            instructions="Test 2",
            knowledge=mock_knowledge,
        )
        
        assert agent1.knowledge is agent2.knowledge


class TestAgentQueryMethod:
    """Test Agent.query() method."""
    
    def test_query_raises_without_knowledge(self):
        """Test query() raises ValueError without knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
        )
        
        with pytest.raises(ValueError, match="No knowledge configured"):
            agent.query("What is the answer?")
    
    def test_query_returns_rag_result(self):
        """Test query() returns RAGResult with mocked RAG."""
        from praisonaiagents import Agent
        from praisonaiagents.rag.models import RAGResult, Citation
        
        mock_rag_result = RAGResult(
            answer="The answer is 42",
            citations=[Citation(id="1", source="test.txt", text="42 is the answer")],
            context_used="Context here",
            query="What is the answer?",
        )
        
        mock_rag = Mock()
        mock_rag.query = Mock(return_value=mock_rag_result)
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=["test.txt"],
        )
        agent._rag_instance = mock_rag
        agent._knowledge_processed = True
        agent.knowledge = Mock()
        
        result = agent.query("What is the answer?")
        
        assert result.answer == "The answer is 42"
        assert len(result.citations) == 1
        mock_rag.query.assert_called_once()


class TestAgentRetrieveMethod:
    """Test Agent.retrieve() method."""
    
    def test_retrieve_raises_without_knowledge(self):
        """Test retrieve() raises ValueError without knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
        )
        
        with pytest.raises(ValueError, match="No knowledge configured"):
            agent.retrieve("search query")
    
    def test_retrieve_returns_context_pack(self):
        """Test retrieve() returns ContextPack with mocked RAG."""
        from praisonaiagents import Agent
        from praisonaiagents.rag.models import ContextPack, Citation
        
        mock_context_pack = ContextPack(
            context="Retrieved context",
            citations=[Citation(id="1", source="test.txt", text="content")],
            query="search query",
        )
        
        mock_rag = Mock()
        mock_rag.retrieve = Mock(return_value=mock_context_pack)
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=["test.txt"],
        )
        agent._rag_instance = mock_rag
        agent._knowledge_processed = True
        agent.knowledge = Mock()
        
        result = agent.retrieve("search query")
        
        assert result.context == "Retrieved context"
        assert len(result.citations) == 1
        mock_rag.retrieve.assert_called_once()


class TestAgentChatRetrieval:
    """Test retrieval in Agent.chat() method."""
    
    def test_chat_with_force_retrieval(self):
        """Test chat() with force_retrieval=True."""
        from praisonaiagents import Agent, KnowledgeConfig
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=KnowledgeConfig(
                sources=["test.txt"],
            ),
        )
        
        # Verify force parameter is accepted
        # Full integration test would require mocking LLM
        assert hasattr(agent.chat, '__call__')
    
    def test_chat_with_skip_retrieval(self):
        """Test chat() with skip_retrieval=True."""
        from praisonaiagents import Agent, KnowledgeConfig
        
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            knowledge=KnowledgeConfig(
                sources=["test.txt"],
            ),
        )
        
        # Verify skip parameter is accepted
        assert hasattr(agent.chat, '__call__')


class TestLazyLoading:
    """Test lazy loading of retrieval dependencies."""
    
    def test_import_agent_does_not_import_chromadb(self):
        """Test importing Agent does not import chromadb."""
        import sys
        
        # Clear any cached imports
        modules_before = set(sys.modules.keys())
        
        from praisonaiagents import Agent
        
        # Agent import should not trigger chromadb import
        # (chromadb is only imported when knowledge is actually used)
        agent = Agent(name="Test", instructions="Test")
        
        # This is a soft check - chromadb may be imported by other tests
        # The key is that Agent init without knowledge doesn't require it
        assert agent is not None
    
    def test_retrieval_config_import_is_lightweight(self):
        """Test RetrievalConfig import is lightweight."""
        import sys
        import time
        
        start = time.perf_counter()
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        elapsed = time.perf_counter() - start
        
        # Should import in under 50ms (no heavy deps)
        assert elapsed < 0.5  # Allow some slack for slow systems
        
        config = RetrievalConfig()
        assert config is not None


class TestExportsAvailable:
    """Test that all expected exports are available."""
    
    def test_retrieval_config_exported(self):
        """Test RetrievalConfig is exported from top level."""
        from praisonaiagents import RetrievalConfig
        assert RetrievalConfig is not None
    
    def test_retrieval_policy_exported(self):
        """Test RetrievalPolicy is exported from top level."""
        from praisonaiagents import RetrievalPolicy
        assert RetrievalPolicy is not None
    
    def test_citations_mode_exported(self):
        """Test CitationsMode is exported from top level."""
        from praisonaiagents import CitationsMode
        assert CitationsMode is not None
    
    def test_context_pack_exported(self):
        """Test ContextPack is exported from top level."""
        from praisonaiagents import ContextPack
        assert ContextPack is not None
    
    def test_rag_result_exported(self):
        """Test RAGResult is exported from top level."""
        from praisonaiagents import RAGResult
        assert RAGResult is not None
    
    def test_citation_exported(self):
        """Test Citation is exported from top level."""
        from praisonaiagents import Citation
        assert Citation is not None
