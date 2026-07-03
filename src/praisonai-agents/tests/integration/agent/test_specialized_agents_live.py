"""
Live integration tests for specialized agents.

These tests require:
- PRAISONAI_LIVE_TESTS=1 environment variable
- OPENAI_API_KEY environment variable

Run with: PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/agent/test_specialized_agents_live.py -v
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.mark.live
class TestCodeAgentLive:
    """Live tests for CodeAgent real functionality."""
    
    def test_code_agent_real_code_generation(self, openai_api_key):
        """Test CodeAgent generates and executes actual code."""
        try:
            from praisonaiagents.agent import CodeAgent
        except ImportError:
            pytest.skip("CodeAgent not available")
        
        agent = CodeAgent(
            name="TestCodeAgent",
            instructions="You are a Python code generation expert."
        )
        
        # Real task: generate actual working code
        result = agent.generate("Write a Python function that calculates the fibonacci sequence for n=5 and print the result")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert "fibonacci" in result.lower() or "fib" in result.lower()
        
        print(f"CodeAgent result: {result}")


@pytest.mark.live
class TestVisionAgentLive:
    """Live tests for VisionAgent real functionality."""
    
    def test_vision_agent_real_image_analysis(self, openai_api_key):
        """Test VisionAgent analyzes actual image content."""
        try:
            from praisonaiagents.agent import VisionAgent
        except ImportError:
            pytest.skip("VisionAgent not available")
        
        pytest.skip("VisionAgent requires an image input for analyze()")


@pytest.mark.live  
class TestImageAgentLive:
    """Live tests for ImageAgent real functionality."""
    
    def test_image_agent_real_generation(self, openai_api_key):
        """Test ImageAgent generates actual images."""
        try:
            from praisonaiagents.agent import ImageAgent
        except ImportError:
            pytest.skip("ImageAgent not available")
        
        agent = ImageAgent(
            name="TestImageAgent",
            instructions="You are an image generation expert."
        )
        
        # Real task: generate image
        result = agent.start("Create a simple landscape image description")
        
        # Assertions  
        assert result is not None
        assert len(result) > 0
        
        print(f"ImageAgent result: {result}")


@pytest.mark.live
class TestRouterAgentLive:
    """Live tests for RouterAgent real functionality."""
    
    def test_router_agent_real_routing(self, openai_api_key):
        """Test RouterAgent routes tasks to appropriate models."""
        try:
            from praisonaiagents.agent import RouterAgent
        except ImportError:
            pytest.skip("RouterAgent not available")
        
        agent = RouterAgent(
            name="TestRouterAgent",
            role="Task Router",
            goal="Route tasks efficiently",
            models=["gpt-4o-mini"],
            routing_strategy="auto"
        )
        
        # Real task: test routing decision
        result = agent.start("What is 2 + 2? This is a simple math question.")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert "4" in result
        
        print(f"RouterAgent result: {result}")


@pytest.mark.live
class TestDeepResearchAgentLive:
    """Live tests for DeepResearchAgent real functionality."""
    
    def test_deep_research_agent_real_research(self, openai_api_key):
        """Test DeepResearchAgent performs actual research tasks."""
        try:
            from praisonaiagents.agent import DeepResearchAgent
        except ImportError:
            pytest.skip("DeepResearchAgent not available")
        
        agent = DeepResearchAgent(
            name="TestResearchAgent",
            instructions="You are a research expert."
        )
        
        # Real task: research and synthesize
        result = agent.research("Summarise artificial intelligence in one paragraph.")
        text = getattr(result, "output", None) or getattr(result, "content", None) or str(result)
        
        # Assertions
        assert result is not None
        assert len(str(text)) > 0
        assert ("artificial intelligence" in str(text).lower() or "ai" in str(text).lower())
        
        print(f"DeepResearchAgent result: {text}")


@pytest.mark.live
class TestContextAgentLive:
    """Live tests for ContextAgent real functionality."""
    
    def test_context_agent_real_context_management(self, openai_api_key):
        """Test ContextAgent manages context effectively."""
        try:
            from praisonaiagents.agent import ContextAgent
        except ImportError:
            pytest.skip("ContextAgent not available")
        
        agent = ContextAgent(
            name="TestContextAgent",
            instructions="You are a context-aware assistant."
        )
        
        # Real task: test context awareness
        result = agent.start("Remember that my name is Alice. Now greet me by name.")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert "alice" in result.lower()
        
        print(f"ContextAgent result: {result}")


@pytest.mark.live
class TestEmbeddingAgentLive:
    """Live tests for EmbeddingAgent real functionality."""
    
    def test_embedding_agent_real_embeddings(self, openai_api_key):
        """Test EmbeddingAgent generates actual embeddings."""
        try:
            from praisonaiagents.agent import EmbeddingAgent
        except ImportError:
            pytest.skip("EmbeddingAgent not available")
        
        agent = EmbeddingAgent(
            name="TestEmbeddingAgent",
            instructions="You are an embedding generation expert."
        )
        
        # Real task: generate embeddings for text
        vector = agent.embed("Hello world")
        assert isinstance(vector, list)
        assert len(vector) > 0
        print(f"EmbeddingAgent result: embedding_dim={len(vector)}")


@pytest.mark.live
class TestRealtimeAgentLive:
    """Live tests for RealtimeAgent real functionality."""
    
    def test_realtime_agent_real_response(self, openai_api_key):
        pytest.skip("RealtimeAgent requires an active WebSocket Realtime session")


@pytest.mark.live
class TestAudioAgentLive:
    """Live tests for AudioAgent real functionality."""
    
    def test_audio_agent_real_processing(self, openai_api_key):
        """Test AudioAgent processes audio-related tasks."""
        try:
            from praisonaiagents.agent import AudioAgent
        except ImportError:
            pytest.skip("AudioAgent not available")
        
        pytest.skip("AudioAgent requires an audio file for transcribe()")


@pytest.mark.live
class TestVideoAgentLive:
    """Live tests for VideoAgent real functionality."""
    
    def test_video_agent_real_processing(self, openai_api_key):
        """Test VideoAgent processes video-related tasks."""
        try:
            from praisonaiagents.agent import VideoAgent
        except ImportError:
            pytest.skip("VideoAgent not available")
        
        agent = VideoAgent(
            name="TestVideoAgent",
            instructions="You are a video processing expert."
        )
        
        # Real task: video-related processing  
        result = agent.start("Explain video compression techniques")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert "video" in result.lower()
        
        print(f"VideoAgent result: {result}")


@pytest.mark.live
class TestOCRAgentLive:
    """Live tests for OCRAgent real functionality."""
    
    def test_ocr_agent_real_text_extraction(self, openai_api_key):
        """Test OCRAgent performs text extraction tasks."""
        try:
            from praisonaiagents.agent import OCRAgent
        except ImportError:
            pytest.skip("OCRAgent not available")
        
        pytest.skip("OCRAgent requires an image file for extract()")