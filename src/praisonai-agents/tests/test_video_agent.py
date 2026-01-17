"""
Unit tests for VideoAgent class.

Tests all 5 operations (generate, status, content, list, remix) with mocked LiteLLM responses.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Mock VideoObject for testing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MockVideoObject:
    """Mock video object matching LiteLLM's VideoObject structure."""
    id: str = "video_test123"
    object: str = "video"
    status: str = "queued"
    created_at: int = 1705500000
    completed_at: Optional[int] = None
    expires_at: Optional[int] = None
    error: Optional[Dict] = None
    progress: int = 0
    remixed_from_video_id: Optional[str] = None
    seconds: str = "8"
    size: str = "1280x720"
    model: str = "sora-2"
    usage: Dict[str, Any] = field(default_factory=lambda: {"duration_seconds": 8.0})


# ─────────────────────────────────────────────────────────────────────────────
# VideoAgent Import and Class Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVideoAgentImport:
    """Test that VideoAgent can be imported correctly."""
    
    def test_import_from_praisonaiagents(self):
        """Test import from main package."""
        from praisonaiagents import VideoAgent, VideoConfig
        assert VideoAgent is not None
        assert VideoConfig is not None
    
    def test_import_from_agent_module(self):
        """Test import from agent submodule."""
        from praisonaiagents.agent import VideoAgent, VideoConfig
        assert VideoAgent is not None
        assert VideoConfig is not None
    
    def test_import_direct(self):
        """Test direct import from video_agent module."""
        from praisonaiagents.agent.video_agent import VideoAgent, VideoConfig
        assert VideoAgent is not None
        assert VideoConfig is not None


class TestVideoAgentInit:
    """Test VideoAgent initialization."""
    
    def test_default_initialization(self):
        """Test default initialization."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent()
        assert agent.name == "VideoAgent"
        assert agent.llm == "openai/sora-2"
        assert agent.verbose == True
    
    def test_with_llm_parameter(self):
        """Test initialization with llm parameter."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="gemini/veo-3.0-generate-preview")
        assert agent.llm == "gemini/veo-3.0-generate-preview"
    
    def test_with_model_alias(self):
        """Test initialization with model= alias for llm=."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(model="azure/sora-2")
        assert agent.llm == "azure/sora-2"
    
    def test_llm_takes_precedence_over_model(self):
        """Test that llm= takes precedence over model=."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="openai/sora-2-pro", model="openai/sora-2")
        assert agent.llm == "openai/sora-2-pro"
    
    def test_with_name_and_instructions(self):
        """Test initialization with custom name and instructions."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(
            name="MyVideoAgent",
            instructions="Generate creative videos",
            llm="openai/sora-2"
        )
        assert agent.name == "MyVideoAgent"
        assert agent.instructions == "Generate creative videos"


class TestVideoConfig:
    """Test VideoConfig dataclass."""
    
    def test_default_values(self):
        """Test default VideoConfig values."""
        from praisonaiagents import VideoConfig
        
        config = VideoConfig()
        assert config.seconds == "8"
        assert config.size is None
        assert config.input_reference is None
        assert config.timeout == 600
        assert config.poll_interval == 10
        assert config.max_wait_time == 600
    
    def test_custom_values(self):
        """Test VideoConfig with custom values."""
        from praisonaiagents import VideoConfig
        
        config = VideoConfig(
            seconds="16",
            size="720x1280",
            timeout=900,
            poll_interval=5
        )
        assert config.seconds == "16"
        assert config.size == "720x1280"
        assert config.timeout == 900
        assert config.poll_interval == 5
    
    def test_to_dict(self):
        """Test VideoConfig.to_dict() method."""
        from praisonaiagents import VideoConfig
        
        config = VideoConfig(seconds="8", size="1280x720")
        d = config.to_dict()
        
        assert d["seconds"] == "8"
        assert d["size"] == "1280x720"
        assert "timeout" in d


class TestVideoConfigPrecedenceLadder:
    """Test Precedence Ladder for video configuration."""
    
    def test_bool_true_uses_defaults(self):
        """Test video=True uses default config."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(video=True)
        assert agent._video_config.seconds == "8"
    
    def test_bool_false_uses_defaults(self):
        """Test video=False still provides config."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(video=False)
        assert agent._video_config is not None
    
    def test_dict_configuration(self):
        """Test video=dict configuration."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(video={"seconds": "16", "size": "720x1280"})
        assert agent._video_config.seconds == "16"
        assert agent._video_config.size == "720x1280"
    
    def test_config_instance(self):
        """Test video=VideoConfig() instance."""
        from praisonaiagents import VideoAgent, VideoConfig
        
        config = VideoConfig(seconds="10", size="1920x1080")
        agent = VideoAgent(video=config)
        assert agent._video_config.seconds == "10"
        assert agent._video_config.size == "1920x1080"


# ─────────────────────────────────────────────────────────────────────────────
# Mock-based Operation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVideoAgentOperations:
    """Test VideoAgent operations with mocked LiteLLM."""
    
    @pytest.fixture
    def mock_video_module(self):
        """Create mock video module."""
        mock_response = MockVideoObject()
        return {
            "video_generation": Mock(return_value=mock_response),
            "avideo_generation": Mock(return_value=mock_response),
            "video_status": Mock(return_value=MockVideoObject(status="completed")),
            "avideo_status": Mock(return_value=MockVideoObject(status="completed")),
            "video_content": Mock(return_value=b"fake_video_bytes"),
            "avideo_content": Mock(return_value=b"fake_video_bytes"),
            "video_list": Mock(return_value=[mock_response]),
            "avideo_list": Mock(return_value=[mock_response]),
            "video_remix": Mock(return_value=mock_response),
            "avideo_remix": Mock(return_value=mock_response),
        }
    
    @pytest.fixture
    def agent_with_mocks(self, mock_video_module):
        """Create VideoAgent with mocked video module."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="openai/sora-2", verbose=False)
        agent._litellm_video = mock_video_module
        return agent
    
    def test_generate_basic(self, agent_with_mocks, mock_video_module):
        """Test basic video generation."""
        result = agent_with_mocks.generate("A cat playing with yarn")
        
        assert result.id == "video_test123"
        assert result.status == "queued"
        mock_video_module["video_generation"].assert_called_once()
    
    def test_generate_with_params(self, agent_with_mocks, mock_video_module):
        """Test video generation with parameters."""
        result = agent_with_mocks.generate(
            prompt="A sunset over the ocean",
            seconds="16",
            size="720x1280"
        )
        
        call_kwargs = mock_video_module["video_generation"].call_args.kwargs
        assert call_kwargs["prompt"] == "A sunset over the ocean"
        assert call_kwargs["seconds"] == "16"
        assert call_kwargs["size"] == "720x1280"
    
    def test_status(self, agent_with_mocks, mock_video_module):
        """Test status check."""
        result = agent_with_mocks.status("video_test123")
        
        assert result.status == "completed"
        mock_video_module["video_status"].assert_called_once_with(video_id="video_test123")
    
    def test_content(self, agent_with_mocks, mock_video_module):
        """Test content download."""
        result = agent_with_mocks.content("video_test123")
        
        assert result == b"fake_video_bytes"
        mock_video_module["video_content"].assert_called_once_with(video_id="video_test123")
    
    def test_list(self, agent_with_mocks, mock_video_module):
        """Test list videos."""
        result = agent_with_mocks.list()
        
        assert len(result) == 1
        assert result[0].id == "video_test123"
        mock_video_module["video_list"].assert_called_once()
    
    def test_remix(self, agent_with_mocks, mock_video_module):
        """Test video remix."""
        result = agent_with_mocks.remix("video_test123", "Make it more dramatic")
        
        assert result.id == "video_test123"
        mock_video_module["video_remix"].assert_called_once_with(
            video_id="video_test123",
            prompt="Make it more dramatic"
        )


class TestVideoAgentConvenienceMethods:
    """Test convenience methods (start, run, wait_for_completion)."""
    
    @pytest.fixture
    def agent_with_immediate_completion(self):
        """Create agent that immediately returns completed status."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="openai/sora-2", verbose=False)
        
        # Mock video module
        initial_video = MockVideoObject(status="processing")
        completed_video = MockVideoObject(status="completed")
        
        agent._litellm_video = {
            "video_generation": Mock(return_value=initial_video),
            "avideo_generation": Mock(return_value=initial_video),
            "video_status": Mock(return_value=completed_video),
            "avideo_status": Mock(return_value=completed_video),
            "video_content": Mock(return_value=b"video_bytes_here"),
            "avideo_content": Mock(return_value=b"video_bytes_here"),
            "video_list": Mock(return_value=[]),
            "avideo_list": Mock(return_value=[]),
            "video_remix": Mock(return_value=initial_video),
            "avideo_remix": Mock(return_value=initial_video),
        }
        return agent
    
    def test_run_returns_immediately(self, agent_with_immediate_completion):
        """Test run() returns immediately without waiting."""
        result = agent_with_immediate_completion.run("A test prompt")
        
        assert result.status == "processing"  # Initial status
    
    def test_start_without_wait(self, agent_with_immediate_completion):
        """Test start(wait=False) returns immediately."""
        result = agent_with_immediate_completion.start("A test prompt", wait=False)
        
        assert result.status == "processing"
    
    def test_start_with_wait(self, agent_with_immediate_completion):
        """Test start(wait=True) waits for completion."""
        result = agent_with_immediate_completion.start("A test prompt", wait=True)
        
        assert result.status == "completed"


class TestVideoAgentProviders:
    """Test provider-specific configurations."""
    
    def test_openai_provider(self):
        """Test OpenAI Sora-2 configuration."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="openai/sora-2")
        assert "sora" in agent.llm
    
    def test_azure_provider(self):
        """Test Azure configuration."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="azure/sora-2")
        assert "azure" in agent.llm
    
    def test_gemini_provider(self):
        """Test Gemini Veo configuration."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="gemini/veo-3.0-generate-preview")
        assert "veo" in agent.llm
    
    def test_vertex_ai_provider(self):
        """Test Vertex AI configuration."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="vertex_ai/veo-3.0-generate-preview")
        assert "vertex_ai" in agent.llm
    
    def test_runwayml_provider(self):
        """Test RunwayML configuration."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="runwayml/gen4_turbo")
        assert "runwayml" in agent.llm


# ─────────────────────────────────────────────────────────────────────────────
# Async Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoAgentAsync:
    """Test async operations."""
    
    @pytest.fixture
    def async_agent(self):
        """Create agent with async mocks."""
        from praisonaiagents import VideoAgent
        
        agent = VideoAgent(llm="openai/sora-2", verbose=False)
        
        mock_response = MockVideoObject()
        completed_response = MockVideoObject(status="completed")
        
        async def async_generate(*args, **kwargs):
            return mock_response
        
        async def async_status(*args, **kwargs):
            return completed_response
        
        async def async_content(*args, **kwargs):
            return b"async_video_bytes"
        
        async def async_list(*args, **kwargs):
            return [mock_response]
        
        async def async_remix(*args, **kwargs):
            return mock_response
        
        agent._litellm_video = {
            "video_generation": Mock(return_value=mock_response),
            "avideo_generation": async_generate,
            "video_status": Mock(return_value=completed_response),
            "avideo_status": async_status,
            "video_content": Mock(return_value=b"video_bytes"),
            "avideo_content": async_content,
            "video_list": Mock(return_value=[]),
            "avideo_list": async_list,
            "video_remix": Mock(return_value=mock_response),
            "avideo_remix": async_remix,
        }
        return agent
    
    async def test_agenerate(self, async_agent):
        """Test async generation."""
        result = await async_agent.agenerate("Async test prompt")
        assert result.id == "video_test123"
    
    async def test_astatus(self, async_agent):
        """Test async status."""
        result = await async_agent.astatus("video_test123")
        assert result.status == "completed"
    
    async def test_acontent(self, async_agent):
        """Test async content download."""
        result = await async_agent.acontent("video_test123")
        assert result == b"async_video_bytes"
    
    async def test_alist(self, async_agent):
        """Test async list."""
        result = await async_agent.alist()
        assert len(result) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
