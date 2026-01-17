"""Tests for OCRAgent."""
import pytest
from unittest.mock import MagicMock, patch


class TestOCRAgentImports:
    """Test OCRAgent can be imported."""
    
    def test_import_from_package(self):
        """Test importing from main package."""
        from praisonaiagents import OCRAgent, OCRConfig
        assert OCRAgent is not None
        assert OCRConfig is not None
    
    def test_import_from_agent_module(self):
        """Test importing from agent module."""
        from praisonaiagents.agent import OCRAgent, OCRConfig
        assert OCRAgent is not None
        assert OCRConfig is not None


class TestOCRAgentInit:
    """Test OCRAgent initialization."""
    
    def test_default_init(self):
        """Test default initialization."""
        from praisonaiagents import OCRAgent
        agent = OCRAgent()
        assert agent.name == "OCRAgent"
        assert agent.llm == "mistral/mistral-ocr-latest"
    
    def test_custom_model(self):
        """Test custom model."""
        from praisonaiagents import OCRAgent
        agent = OCRAgent(llm="mistral/custom-ocr")
        assert agent.llm == "mistral/custom-ocr"
    
    def test_model_alias(self):
        """Test model= alias for llm=."""
        from praisonaiagents import OCRAgent
        agent = OCRAgent(model="mistral/custom-ocr")
        assert agent.llm == "mistral/custom-ocr"


class TestOCRConfig:
    """Test OCRConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration."""
        from praisonaiagents import OCRConfig
        config = OCRConfig()
        assert config.include_image_base64 == False
        assert config.pages is None
        assert config.timeout == 600
    
    def test_custom_config(self):
        """Test custom configuration."""
        from praisonaiagents import OCRConfig
        config = OCRConfig(
            include_image_base64=True,
            pages=[1, 2, 3],
            image_limit=5
        )
        assert config.include_image_base64 == True
        assert config.pages == [1, 2, 3]
        assert config.image_limit == 5
    
    def test_config_to_dict(self):
        """Test config to_dict method."""
        from praisonaiagents import OCRConfig
        config = OCRConfig(include_image_base64=True)
        d = config.to_dict()
        assert d["include_image_base64"] == True


class TestOCRAgentOperations:
    """Test OCRAgent operations."""
    
    @patch('praisonaiagents.agent.ocr_agent.OCRAgent.litellm', new_callable=lambda: MagicMock())
    def test_extract_pdf(self, mock_litellm):
        """Test extracting text from PDF."""
        from praisonaiagents import OCRAgent
        
        # Mock response
        mock_response = MagicMock()
        mock_response.pages = [MagicMock(markdown="Page 1 content")]
        mock_litellm.ocr.return_value = mock_response
        
        agent = OCRAgent(verbose=False)
        agent._litellm = mock_litellm
        
        result = agent.extract("https://example.com/doc.pdf")
        
        assert mock_litellm.ocr.called
        call_args = mock_litellm.ocr.call_args
        assert call_args[1]["document"]["type"] == "document_url"
    
    @patch('praisonaiagents.agent.ocr_agent.OCRAgent.litellm', new_callable=lambda: MagicMock())
    def test_extract_image(self, mock_litellm):
        """Test extracting text from image."""
        from praisonaiagents import OCRAgent
        
        mock_response = MagicMock()
        mock_response.pages = [MagicMock(markdown="Image text")]
        mock_litellm.ocr.return_value = mock_response
        
        agent = OCRAgent(verbose=False)
        agent._litellm = mock_litellm
        
        result = agent.extract("https://example.com/image.png")
        
        call_args = mock_litellm.ocr.call_args
        assert call_args[1]["document"]["type"] == "image_url"
    
    @patch('praisonaiagents.agent.ocr_agent.OCRAgent.litellm', new_callable=lambda: MagicMock())
    def test_read_convenience(self, mock_litellm):
        """Test read() convenience method."""
        from praisonaiagents import OCRAgent
        
        mock_page = MagicMock()
        mock_page.markdown = "Extracted text"
        mock_response = MagicMock()
        mock_response.pages = [mock_page]
        mock_litellm.ocr.return_value = mock_response
        
        agent = OCRAgent(verbose=False)
        agent._litellm = mock_litellm
        
        text = agent.read("https://example.com/doc.pdf")
        
        assert text == "Extracted text"


class TestImageAgentEnhancements:
    """Test ImageAgent edit and variation methods."""
    
    def test_edit_method_exists(self):
        """Test edit method exists."""
        from praisonaiagents import ImageAgent
        agent = ImageAgent()
        assert hasattr(agent, 'edit')
        assert hasattr(agent, 'aedit')
    
    def test_variation_method_exists(self):
        """Test variation method exists."""
        from praisonaiagents import ImageAgent
        agent = ImageAgent()
        assert hasattr(agent, 'variation')
        assert hasattr(agent, 'avariation')
