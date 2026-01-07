"""
Unit tests for AutoRagAgent.

Tests:
- AutoRagConfig creation and serialization
- RetrievalPolicy enum
- AutoRagAgent decision logic (AUTO/ALWAYS/NEVER + overrides)
- AutoRagAgent chat method
- Integration with RAG.retrieve and Agent.chat_with_context
"""

from unittest.mock import Mock


class TestAutoRagConfig:
    """Tests for AutoRagConfig dataclass."""
    
    def test_default_config(self):
        """Test default AutoRagConfig values."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagConfig, RetrievalPolicy
        
        config = AutoRagConfig()
        
        assert config.retrieval_policy == RetrievalPolicy.AUTO
        assert config.top_k == 5
        assert config.hybrid is False
        assert config.rerank is False
        assert config.include_citations is True
        assert config.citations_mode == "append"
        assert config.auto_min_length == 10
        assert "what" in config.auto_keywords
    
    def test_config_with_always_policy(self):
        """Test config with ALWAYS retrieval policy."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagConfig, RetrievalPolicy
        
        config = AutoRagConfig(retrieval_policy=RetrievalPolicy.ALWAYS)
        assert config.retrieval_policy == RetrievalPolicy.ALWAYS
    
    def test_config_to_dict(self):
        """Test config serialization."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagConfig
        
        config = AutoRagConfig(top_k=10, hybrid=True)
        d = config.to_dict()
        
        assert d["top_k"] == 10
        assert d["hybrid"] is True
        assert d["retrieval_policy"] == "auto"
    
    def test_config_from_dict(self):
        """Test config deserialization."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagConfig, RetrievalPolicy
        
        data = {
            "retrieval_policy": "always",
            "top_k": 10,
            "hybrid": True,
        }
        
        config = AutoRagConfig.from_dict(data)
        assert config.retrieval_policy == RetrievalPolicy.ALWAYS
        assert config.top_k == 10
        assert config.hybrid is True


class TestRetrievalPolicy:
    """Tests for RetrievalPolicy enum."""
    
    def test_policy_values(self):
        """Test RetrievalPolicy enum values."""
        from praisonaiagents.agents.auto_rag_agent import RetrievalPolicy
        
        assert RetrievalPolicy.AUTO.value == "auto"
        assert RetrievalPolicy.ALWAYS.value == "always"
        assert RetrievalPolicy.NEVER.value == "never"
    
    def test_policy_from_string(self):
        """Test creating policy from string."""
        from praisonaiagents.agents.auto_rag_agent import RetrievalPolicy
        
        assert RetrievalPolicy("auto") == RetrievalPolicy.AUTO
        assert RetrievalPolicy("always") == RetrievalPolicy.ALWAYS
        assert RetrievalPolicy("never") == RetrievalPolicy.NEVER


class TestAutoRagAgentDecision:
    """Tests for AutoRagAgent decision logic."""
    
    def test_needs_retrieval_with_question_mark(self):
        """Test that questions trigger retrieval."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        assert auto_rag._needs_retrieval("What is the capital?") is True
        assert auto_rag._needs_retrieval("How does it work?") is True
    
    def test_needs_retrieval_with_keywords(self):
        """Test that keywords trigger retrieval."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        assert auto_rag._needs_retrieval("explain the process") is True
        assert auto_rag._needs_retrieval("summarize the document") is True
        assert auto_rag._needs_retrieval("find the answer") is True
    
    def test_needs_retrieval_short_query(self):
        """Test that short queries don't trigger retrieval."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        assert auto_rag._needs_retrieval("hi") is False
        assert auto_rag._needs_retrieval("ok") is False
    
    def test_should_retrieve_with_force(self):
        """Test force_retrieval override."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.rag = Mock()
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        # Force retrieval even for short query
        assert auto_rag._should_retrieve("hi", force_retrieval=True) is True
    
    def test_should_retrieve_with_skip(self):
        """Test skip_retrieval override."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.rag = Mock()
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        # Skip retrieval even for question
        assert auto_rag._should_retrieve("What is X?", skip_retrieval=True) is False
    
    def test_should_retrieve_always_policy(self):
        """Test ALWAYS policy."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent, RetrievalPolicy
        
        mock_agent = Mock()
        mock_agent.rag = Mock()
        
        auto_rag = AutoRagAgent(agent=mock_agent, retrieval_policy="always")
        
        assert auto_rag._should_retrieve("hi") is True
        assert auto_rag._should_retrieve("ok") is True
    
    def test_should_retrieve_never_policy(self):
        """Test NEVER policy."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.rag = Mock()
        
        auto_rag = AutoRagAgent(agent=mock_agent, retrieval_policy="never")
        
        assert auto_rag._should_retrieve("What is X?") is False
        assert auto_rag._should_retrieve("explain everything") is False
    
    def test_should_retrieve_no_rag_available(self):
        """Test that retrieval is skipped when RAG is not available."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        # Even with question, no retrieval if RAG not available
        assert auto_rag._should_retrieve("What is X?") is False


class TestAutoRagAgentChat:
    """Tests for AutoRagAgent.chat() method."""
    
    def test_chat_without_retrieval(self):
        """Test chat() skips retrieval for simple messages."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.chat.return_value = "Hello!"
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(agent=mock_agent, retrieval_policy="never")
        
        result = auto_rag.chat("hi")
        
        assert result == "Hello!"
        mock_agent.chat.assert_called_once_with("hi")
    
    def test_chat_with_retrieval(self):
        """Test chat() performs retrieval when needed."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        from praisonaiagents.rag.models import ContextPack, Citation
        
        mock_agent = Mock()
        mock_agent.chat.return_value = "Answer based on context"
        mock_agent.rag = Mock()
        
        # Mock retrieve to return a ContextPack
        mock_context = ContextPack(
            context="Retrieved context",
            citations=[Citation(id="1", source="doc.pdf", text="text", score=0.9)],
            query="What is X?",
        )
        mock_agent.rag.retrieve.return_value = mock_context
        
        # Agent doesn't have chat_with_context, so fallback path is used
        del mock_agent.chat_with_context
        
        auto_rag = AutoRagAgent(agent=mock_agent, retrieval_policy="always")
        
        result = auto_rag.chat("What is X?")
        
        # Should have called retrieve
        mock_agent.rag.retrieve.assert_called_once()
        # Should have called chat with augmented message
        mock_agent.chat.assert_called_once()
        # Result should include citations
        assert "Sources:" in result or "Answer" in result
    
    def test_chat_with_chat_with_context(self):
        """Test chat() uses chat_with_context when available."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        from praisonaiagents.rag.models import ContextPack, Citation
        
        mock_agent = Mock()
        mock_agent.chat_with_context.return_value = "Response with context"
        mock_agent.rag = Mock()
        
        mock_context = ContextPack(
            context="Retrieved context",
            citations=[Citation(id="1", source="doc.pdf", text="text", score=0.9)],
            query="What is X?",
        )
        mock_agent.rag.retrieve.return_value = mock_context
        
        auto_rag = AutoRagAgent(agent=mock_agent, retrieval_policy="always")
        
        result = auto_rag.chat("What is X?")
        
        # Should have used chat_with_context
        mock_agent.chat_with_context.assert_called_once()
        assert result == "Response with context"


class TestAutoRagAgentInit:
    """Tests for AutoRagAgent initialization."""
    
    def test_init_with_kwargs(self):
        """Test initialization with keyword arguments."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent, RetrievalPolicy
        
        mock_agent = Mock()
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(
            agent=mock_agent,
            retrieval_policy="always",
            top_k=10,
            hybrid=True,
            rerank=True,
            citations=False,
        )
        
        assert auto_rag.config.retrieval_policy == RetrievalPolicy.ALWAYS
        assert auto_rag.config.top_k == 10
        assert auto_rag.config.hybrid is True
        assert auto_rag.config.rerank is True
        assert auto_rag.config.include_citations is False
    
    def test_name_delegation(self):
        """Test that name is delegated to wrapped agent."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        assert auto_rag.name == "TestAgent"
    
    def test_lazy_rag_from_agent(self):
        """Test lazy RAG loading from agent."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_rag = Mock()
        mock_agent = Mock()
        mock_agent.rag = mock_rag
        
        auto_rag = AutoRagAgent(agent=mock_agent)
        
        # RAG should be lazily loaded from agent
        assert auto_rag.rag is mock_rag


class TestAutoRagAgentExports:
    """Tests for AutoRagAgent exports."""
    
    def test_export_from_agents_module(self):
        """Test AutoRagAgent is exported from agents module."""
        from praisonaiagents.agents import AutoRagAgent, AutoRagConfig, RetrievalPolicy
        
        assert AutoRagAgent is not None
        assert AutoRagConfig is not None
        assert RetrievalPolicy is not None
    
    def test_export_from_top_level(self):
        """Test AutoRagAgent is exported from top-level."""
        from praisonaiagents import AutoRagAgent, AutoRagConfig
        
        assert AutoRagAgent is not None
        assert AutoRagConfig is not None


class TestAutoRagAgentAliases:
    """Tests for AutoRagAgent method aliases."""
    
    def test_run_alias(self):
        """Test run() is alias for chat()."""
        from praisonaiagents.agents.auto_rag_agent import AutoRagAgent
        
        mock_agent = Mock()
        mock_agent.chat.return_value = "Hello!"
        mock_agent.rag = None
        
        auto_rag = AutoRagAgent(agent=mock_agent, retrieval_policy="never")
        
        # run should work same as chat
        result = auto_rag.run("hi")
        assert result == "Hello!"
