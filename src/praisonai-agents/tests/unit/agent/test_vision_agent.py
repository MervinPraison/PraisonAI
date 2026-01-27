"""
Tests for VisionAgent - TDD approach.

Tests written BEFORE implementation to define expected behavior.
"""

from unittest.mock import Mock


class TestVisionAgentInit:
    """Test VisionAgent initialization."""
    
    def test_import_vision_agent(self):
        """VisionAgent should be importable from praisonaiagents."""
        from praisonaiagents import VisionAgent
        assert VisionAgent is not None
    
    def test_import_vision_config(self):
        """VisionConfig should be importable."""
        from praisonaiagents import VisionConfig
        assert VisionConfig is not None
    
    def test_default_initialization(self):
        """VisionAgent should initialize with defaults."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent()
        assert agent.name == "VisionAgent"
        assert agent.llm is not None
    
    def test_custom_name(self):
        """VisionAgent should accept custom name."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(name="MyVision")
        assert agent.name == "MyVision"
    
    def test_custom_model(self):
        """VisionAgent should accept custom model."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(llm="gpt-4o")
        assert "gpt-4o" in agent.llm
    
    def test_model_alias(self):
        """VisionAgent should accept model= as alias for llm=."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(model="gpt-4o-mini")
        assert "gpt-4o-mini" in agent.llm


class TestVisionConfig:
    """Test VisionConfig dataclass."""
    
    def test_default_config(self):
        """VisionConfig should have sensible defaults."""
        from praisonaiagents.agent.vision_agent import VisionConfig
        config = VisionConfig()
        assert config.detail == "auto"
        assert config.max_tokens == 4096
        assert config.timeout == 60
    
    def test_custom_config(self):
        """VisionConfig should accept custom values."""
        from praisonaiagents.agent.vision_agent import VisionConfig
        config = VisionConfig(detail="high", max_tokens=8192)
        assert config.detail == "high"
        assert config.max_tokens == 8192
    
    def test_config_to_dict(self):
        """VisionConfig should convert to dict."""
        from praisonaiagents.agent.vision_agent import VisionConfig
        config = VisionConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert "detail" in d


class TestVisionAgentAnalyze:
    """Test VisionAgent.analyze() method."""
    
    def test_analyze_with_url(self):
        """analyze() should work with image URL."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(verbose=False)
        
        # Mock the litellm property after initialization
        mock_litellm = Mock()
        mock_litellm.completion.return_value = Mock(
            choices=[Mock(message=Mock(content="A cat sitting on a couch"))]
        )
        agent._litellm = mock_litellm
        
        result = agent.analyze("https://example.com/cat.jpg")
        
        assert result is not None
        assert isinstance(result, str)
        assert result == "A cat sitting on a couch"
    
    def test_analyze_with_prompt(self):
        """analyze() should accept custom prompt."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.completion.return_value = Mock(
            choices=[Mock(message=Mock(content="3 cats"))]
        )
        agent._litellm = mock_litellm
        
        result = agent.analyze(
            "https://example.com/cats.jpg",
            prompt="How many cats are in this image?"
        )
        
        assert result is not None
        assert result == "3 cats"


class TestVisionAgentDescribe:
    """Test VisionAgent.describe() method."""
    
    def test_describe_image(self):
        """describe() should return detailed description."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.completion.return_value = Mock(
            choices=[Mock(message=Mock(content="A detailed description..."))]
        )
        agent._litellm = mock_litellm
        
        result = agent.describe("https://example.com/image.jpg")
        
        assert result is not None
        assert isinstance(result, str)


class TestVisionAgentCompare:
    """Test VisionAgent.compare() method."""
    
    def test_compare_two_images(self):
        """compare() should compare multiple images."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.completion.return_value = Mock(
            choices=[Mock(message=Mock(content="The images differ in..."))]
        )
        agent._litellm = mock_litellm
        
        result = agent.compare([
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg"
        ])
        
        assert result is not None


class TestVisionAgentExtractText:
    """Test VisionAgent.extract_text() method."""
    
    def test_extract_text_from_image(self):
        """extract_text() should extract text from image."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(verbose=False)
        
        mock_litellm = Mock()
        mock_litellm.completion.return_value = Mock(
            choices=[Mock(message=Mock(content="Hello World"))]
        )
        agent._litellm = mock_litellm
        
        result = agent.extract_text("https://example.com/text.jpg")
        
        assert result is not None
        assert isinstance(result, str)


class TestVisionAgentAsync:
    """Test async methods of VisionAgent."""
    
    def test_aanalyze_exists(self):
        """aanalyze() should exist as async method."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(verbose=False)
        
        # Should have async method
        assert hasattr(agent, 'aanalyze')
        assert callable(agent.aanalyze)


class TestVisionAgentLazyLoading:
    """Test lazy loading behavior."""
    
    def test_litellm_not_imported_at_init(self):
        """litellm should not be imported until needed."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent()
        
        # _litellm should be None until first use
        assert agent._litellm is None
    
    def test_console_lazy_loaded(self):
        """Rich console should be lazy loaded."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent()
        
        # _console should be None until first use
        assert agent._console is None


class TestVisionAgentConfigResolution:
    """Test configuration resolution (Precedence Ladder)."""
    
    def test_bool_config(self):
        """vision=True should use defaults."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(vision=True)
        assert agent._vision_config is not None
    
    def test_dict_config(self):
        """vision=dict should create VisionConfig."""
        from praisonaiagents import VisionAgent
        agent = VisionAgent(vision={"detail": "high"})
        assert agent._vision_config.detail == "high"
    
    def test_config_instance(self):
        """vision=VisionConfig should use directly."""
        from praisonaiagents.agent.vision_agent import VisionConfig
        from praisonaiagents import VisionAgent
        
        config = VisionConfig(detail="low", max_tokens=2048)
        agent = VisionAgent(vision=config)
        assert agent._vision_config.detail == "low"
        assert agent._vision_config.max_tokens == 2048
