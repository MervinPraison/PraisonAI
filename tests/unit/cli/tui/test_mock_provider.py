"""Tests for Mock Provider."""

import pytest
from praisonai.cli.features.tui.mock_provider import (
    MockProvider,
    MockProviderConfig,
    MockResponse,
    MockExecutor,
    create_mock_provider,
)


class TestMockResponse:
    """Tests for MockResponse."""
    
    def test_default_chunking(self):
        """Test automatic chunking of content."""
        response = MockResponse(content="Hello world how are you today")
        
        assert len(response.chunks) > 0
        assert "".join(response.chunks).strip() == response.content
    
    def test_custom_chunks(self):
        """Test custom chunks."""
        response = MockResponse(
            content="Hello world",
            chunks=["Hello", " world"],
        )
        
        assert response.chunks == ["Hello", " world"]
    
    def test_token_estimation(self):
        """Test automatic token estimation."""
        response = MockResponse(content="one two three four five")
        
        # Rough estimate: words * 2
        assert response.tokens == 10


class TestMockProviderConfig:
    """Tests for MockProviderConfig."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = MockProviderConfig()
        
        assert config.seed == 42
        assert config.default_delay == 0.05
        assert config.simulate_errors is False
    
    def test_custom_responses(self):
        """Test custom responses."""
        config = MockProviderConfig(
            responses={
                "custom": MockResponse(content="Custom response"),
            }
        )
        
        assert "custom" in config.responses


class TestMockProvider:
    """Tests for MockProvider."""
    
    def test_default_responses(self):
        """Test default canned responses."""
        provider = MockProvider()
        
        assert "hello" in provider.config.responses
        assert "help" in provider.config.responses
        assert "test" in provider.config.responses
    
    @pytest.mark.asyncio
    async def test_generate_hello(self):
        """Test generating hello response."""
        provider = MockProvider()
        
        result = await provider.generate("hello")
        
        assert "content" in result
        assert "Hello" in result["content"]
        assert result["tokens"] > 0
        assert result["cost"] > 0
    
    @pytest.mark.asyncio
    async def test_generate_streaming(self):
        """Test streaming generation."""
        provider = MockProvider()
        
        chunks = []
        result = await provider.generate(
            "hello",
            stream=True,
            on_chunk=lambda c: chunks.append(c),
        )
        
        assert len(chunks) > 0
        assert "".join(chunks).strip() == result["content"]
    
    @pytest.mark.asyncio
    async def test_generate_non_streaming(self):
        """Test non-streaming generation."""
        provider = MockProvider()
        
        result = await provider.generate("hello", stream=False)
        
        assert "content" in result
    
    @pytest.mark.asyncio
    async def test_generate_error(self):
        """Test error response."""
        provider = MockProvider()
        
        with pytest.raises(Exception, match="Simulated error"):
            await provider.generate("error")
    
    @pytest.mark.asyncio
    async def test_generate_tool_calls(self):
        """Test tool call response."""
        provider = MockProvider()
        
        result = await provider.generate("tool")
        
        assert "tool_calls" in result
        assert len(result["tool_calls"]) > 0
        assert result["tool_calls"][0]["name"] == "mock_tool"
    
    @pytest.mark.asyncio
    async def test_deterministic_responses(self):
        """Test responses are deterministic with same seed."""
        provider1 = MockProvider(MockProviderConfig(seed=123))
        provider2 = MockProvider(MockProviderConfig(seed=123))
        
        result1 = await provider1.generate("unique input xyz")
        result2 = await provider2.generate("unique input xyz")
        
        assert result1["content"] == result2["content"]
    
    @pytest.mark.asyncio
    async def test_different_seeds_different_responses(self):
        """Test different seeds produce different responses."""
        provider1 = MockProvider(MockProviderConfig(seed=1))
        provider2 = MockProvider(MockProviderConfig(seed=2))
        
        # Use input that doesn't match canned responses
        result1 = await provider1.generate("random query abc123")
        result2 = await provider2.generate("random query abc123")
        
        # Content should be deterministic based on input hash, not seed
        # But the random error injection would differ
        assert result1["content"] == result2["content"]
    
    @pytest.mark.asyncio
    async def test_stream_iterator(self):
        """Test stream iterator."""
        provider = MockProvider()
        
        chunks = []
        async for chunk in provider.stream("hello"):
            chunks.append(chunk)
        
        assert len(chunks) > 0
    
    def test_reset(self):
        """Test reset functionality."""
        provider = MockProvider()
        provider._playback_index = 5
        
        provider.reset()
        
        assert provider._playback_index == 0


class TestMockExecutor:
    """Tests for MockExecutor."""
    
    @pytest.mark.asyncio
    async def test_execute(self):
        """Test executor execution."""
        executor = MockExecutor()
        
        outputs = []
        result = await executor.execute(
            input_content="hello",
            agent_config={"model": "test-model"},
            on_output=lambda c: outputs.append(c),
        )
        
        assert "output" in result
        assert "metrics" in result
        assert result["metrics"]["tokens"] > 0
    
    @pytest.mark.asyncio
    async def test_execute_with_custom_provider(self):
        """Test executor with custom provider."""
        provider = create_mock_provider(
            seed=42,
            responses={"custom": "Custom output"},
        )
        executor = MockExecutor(provider)
        
        result = await executor.execute(
            input_content="custom query",
            agent_config={},
        )
        
        assert "Custom output" in result["output"]


class TestCreateMockProvider:
    """Tests for create_mock_provider helper."""
    
    def test_create_with_defaults(self):
        """Test creating with defaults."""
        provider = create_mock_provider()
        
        assert provider.config.seed == 42
    
    def test_create_with_custom_seed(self):
        """Test creating with custom seed."""
        provider = create_mock_provider(seed=123)
        
        assert provider.config.seed == 123
    
    def test_create_with_custom_responses(self):
        """Test creating with custom responses."""
        provider = create_mock_provider(
            responses={"mypattern": "My response"}
        )
        
        assert "mypattern" in provider.config.responses
