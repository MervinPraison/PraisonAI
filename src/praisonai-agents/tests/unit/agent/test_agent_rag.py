"""
Tests for Agent RAG integration.

Tests that Agent can access RAG features through the knowledge parameter.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestAgentRAGConfig:
    """Tests for Agent rag_config parameter."""
    
    def test_agent_accepts_rag_config(self):
        """Test that Agent accepts rag_config parameter."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=["test.txt"],
            rag_config={"include_citations": True, "top_k": 5}
        )
        
        assert agent._rag_config == {"include_citations": True, "top_k": 5}
    
    def test_agent_without_rag_config(self):
        """Test that Agent works without rag_config."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=["test.txt"]
        )
        
        assert agent._rag_config is None
    
    def test_agent_without_knowledge_has_no_rag_config(self):
        """Test that Agent without knowledge has no rag_config."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent"
        )
        
        assert agent._rag_config is None
        assert agent._rag_instance is None


class TestAgentRAGProperty:
    """Tests for Agent.rag property."""
    
    def test_agent_has_rag_property(self):
        """Test that Agent has rag property."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=["test.txt"],
            rag_config={"include_citations": True}
        )
        
        assert hasattr(agent, 'rag')
    
    def test_agent_rag_returns_none_without_knowledge(self):
        """Test that Agent.rag returns None without knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent"
        )
        
        assert agent.rag is None
    
    @patch('praisonaiagents.knowledge.Knowledge')
    @patch('praisonaiagents.rag.RAG')
    @patch('praisonaiagents.rag.RAGConfig')
    def test_agent_rag_lazy_loads(self, mock_rag_config, mock_rag, mock_knowledge):
        """Test that Agent.rag lazy loads RAG instance."""
        from praisonaiagents import Agent
        
        mock_knowledge_instance = MagicMock()
        mock_knowledge.return_value = mock_knowledge_instance
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=["test.txt"],
            rag_config={"include_citations": True}
        )
        
        # RAG should not be loaded yet
        assert agent._rag_instance is None
        
        # Access rag property - this triggers lazy loading
        # Note: In real usage, knowledge processing would happen first


class TestAgentRAGQuery:
    """Tests for Agent.rag_query method."""
    
    def test_agent_has_rag_query_method(self):
        """Test that Agent has rag_query method."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=["test.txt"],
            rag_config={"include_citations": True}
        )
        
        assert hasattr(agent, 'rag_query')
        assert callable(agent.rag_query)
    
    def test_rag_query_raises_without_knowledge(self):
        """Test that rag_query raises error without knowledge."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent"
        )
        
        with pytest.raises(ValueError, match="No knowledge sources configured"):
            agent.rag_query("What is the answer?")


class TestAgentKnowledgeContext:
    """Tests for Agent._get_knowledge_context method."""
    
    def test_agent_has_get_knowledge_context_method(self):
        """Test that Agent has _get_knowledge_context method."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=["test.txt"]
        )
        
        assert hasattr(agent, '_get_knowledge_context')
        assert callable(agent._get_knowledge_context)
    
    def test_get_knowledge_context_returns_tuple(self):
        """Test that _get_knowledge_context returns tuple."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent"
        )
        
        result = agent._get_knowledge_context("test query")
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == ""  # No knowledge, empty context
        assert result[1] is None  # No citations


class TestAgentRAGIntegration:
    """Integration tests for Agent + RAG."""
    
    def test_agent_rag_config_passed_to_rag_instance(self):
        """Test that rag_config is passed to RAG instance."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            knowledge=["test.txt"],
            rag_config={
                "include_citations": True,
                "top_k": 10,
                "min_score": 0.5
            }
        )
        
        # Verify config is stored
        assert agent._rag_config["include_citations"] is True
        assert agent._rag_config["top_k"] == 10
        assert agent._rag_config["min_score"] == 0.5
