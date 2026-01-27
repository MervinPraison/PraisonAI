"""
Tests for EmbeddingAgent - TDD approach.

Tests written BEFORE implementation to define expected behavior.
"""

from unittest.mock import Mock


class TestEmbeddingAgentInit:
    """Test EmbeddingAgent initialization."""
    
    def test_import_embedding_agent(self):
        """EmbeddingAgent should be importable from praisonaiagents."""
        from praisonaiagents import EmbeddingAgent
        assert EmbeddingAgent is not None
    
    def test_import_embedding_config(self):
        """EmbeddingConfig should be importable."""
        from praisonaiagents import EmbeddingConfig
        assert EmbeddingConfig is not None
    
    def test_default_initialization(self):
        """EmbeddingAgent should initialize with defaults."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent()
        assert agent.name == "EmbeddingAgent"
        assert agent.llm is not None
    
    def test_custom_name(self):
        """EmbeddingAgent should accept custom name."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(name="MyEmbedder")
        assert agent.name == "MyEmbedder"
    
    def test_custom_model(self):
        """EmbeddingAgent should accept custom model."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(llm="text-embedding-3-large")
        assert "text-embedding-3-large" in agent.llm
    
    def test_model_alias(self):
        """EmbeddingAgent should accept model= as alias for llm=."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(model="text-embedding-ada-002")
        assert "text-embedding-ada-002" in agent.llm


class TestEmbeddingConfig:
    """Test EmbeddingConfig dataclass."""
    
    def test_default_config(self):
        """EmbeddingConfig should have sensible defaults."""
        from praisonaiagents.agent.embedding_agent import EmbeddingConfig
        config = EmbeddingConfig()
        assert config.dimensions is None
        assert config.encoding_format == "float"
    
    def test_custom_config(self):
        """EmbeddingConfig should accept custom values."""
        from praisonaiagents.agent.embedding_agent import EmbeddingConfig
        config = EmbeddingConfig(dimensions=1536, encoding_format="base64")
        assert config.dimensions == 1536
        assert config.encoding_format == "base64"
    
    def test_config_to_dict(self):
        """EmbeddingConfig should convert to dict."""
        from praisonaiagents.agent.embedding_agent import EmbeddingConfig
        config = EmbeddingConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert "encoding_format" in d


class TestEmbeddingAgentEmbed:
    """Test EmbeddingAgent.embed() method."""
    
    def test_embed_text(self):
        """embed() should return embedding vector."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.embedding.return_value = Mock(
            data=[{"embedding": [0.1, 0.2, 0.3]}]
        )
        agent._litellm = mock_litellm
        
        result = agent.embed("Hello world")
        
        assert result is not None
        assert isinstance(result, list)
        assert result == [0.1, 0.2, 0.3]
    
    def test_embed_with_model_override(self):
        """embed() should accept model override."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.embedding.return_value = Mock(
            data=[{"embedding": [0.1, 0.2, 0.3]}]
        )
        agent._litellm = mock_litellm
        
        result = agent.embed("Hello", model="text-embedding-3-large")
        
        assert result is not None


class TestEmbeddingAgentEmbedBatch:
    """Test EmbeddingAgent.embed_batch() method."""
    
    def test_embed_batch(self):
        """embed_batch() should return multiple embeddings."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.embedding.return_value = Mock(
            data=[
                {"embedding": [0.1, 0.2, 0.3]},
                {"embedding": [0.4, 0.5, 0.6]}
            ]
        )
        agent._litellm = mock_litellm
        
        result = agent.embed_batch(["Hello", "World"])
        
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(emb, list) for emb in result)


class TestEmbeddingAgentSimilarity:
    """Test EmbeddingAgent.similarity() method."""
    
    def test_similarity(self):
        """similarity() should return cosine similarity score."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.embedding.return_value = Mock(
            data=[
                {"embedding": [1.0, 0.0, 0.0]},
                {"embedding": [1.0, 0.0, 0.0]}
            ]
        )
        agent._litellm = mock_litellm
        
        score = agent.similarity("Hello", "Hello")
        
        assert score is not None
        assert isinstance(score, float)
        assert score == 1.0  # Identical vectors
    
    def test_similarity_different_texts(self):
        """similarity() should return lower score for different texts."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.embedding.return_value = Mock(
            data=[
                {"embedding": [1.0, 0.0, 0.0]},
                {"embedding": [0.0, 1.0, 0.0]}
            ]
        )
        agent._litellm = mock_litellm
        
        score = agent.similarity("Hello", "Goodbye")
        
        assert score is not None
        assert isinstance(score, float)
        assert score == 0.0  # Orthogonal vectors


class TestEmbeddingAgentAsync:
    """Test async methods of EmbeddingAgent."""
    
    def test_aembed_exists(self):
        """aembed() should exist as async method."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(verbose=False)
        
        assert hasattr(agent, 'aembed')
        assert callable(agent.aembed)


class TestEmbeddingAgentLazyLoading:
    """Test lazy loading behavior."""
    
    def test_litellm_not_imported_at_init(self):
        """litellm should not be imported until needed."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent()
        
        assert agent._litellm is None
    
    def test_console_lazy_loaded(self):
        """Rich console should be lazy loaded."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent()
        
        assert agent._console is None


class TestEmbeddingAgentConfigResolution:
    """Test configuration resolution (Precedence Ladder)."""
    
    def test_bool_config(self):
        """embedding=True should use defaults."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(embedding=True)
        assert agent._embedding_config is not None
    
    def test_dict_config(self):
        """embedding=dict should create EmbeddingConfig."""
        from praisonaiagents import EmbeddingAgent
        agent = EmbeddingAgent(embedding={"dimensions": 1024})
        assert agent._embedding_config.dimensions == 1024
    
    def test_config_instance(self):
        """embedding=EmbeddingConfig should use directly."""
        from praisonaiagents.agent.embedding_agent import EmbeddingConfig
        from praisonaiagents import EmbeddingAgent
        
        config = EmbeddingConfig(dimensions=512)
        agent = EmbeddingAgent(embedding=config)
        assert agent._embedding_config.dimensions == 512
