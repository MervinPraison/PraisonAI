"""
Mock Provider for PraisonAI TUI Testing.

Provides deterministic, replayable responses for CI and headless testing.
"""

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional


@dataclass
class MockResponse:
    """A mock response configuration."""
    content: str
    chunks: List[str] = field(default_factory=list)
    delay_per_chunk: float = 0.05
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    tokens: int = 0
    cost: float = 0.0
    
    def __post_init__(self):
        if not self.chunks and self.content:
            # Split content into word chunks
            words = self.content.split()
            self.chunks = []
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i+3])
                if i > 0:
                    chunk = " " + chunk
                self.chunks.append(chunk)
        
        if not self.tokens:
            self.tokens = len(self.content.split()) * 2  # Rough estimate


@dataclass
class MockProviderConfig:
    """Configuration for mock provider."""
    seed: int = 42
    default_delay: float = 0.05
    simulate_errors: bool = False
    error_rate: float = 0.1
    record_mode: bool = False
    playback_file: Optional[str] = None
    
    # Canned responses by input pattern
    responses: Dict[str, MockResponse] = field(default_factory=dict)
    
    # Default response if no pattern matches
    default_response: Optional[MockResponse] = None


class MockProvider:
    """
    Mock LLM provider for testing.
    
    Features:
    - Deterministic responses based on seed
    - Streaming simulation
    - Tool call simulation
    - Error injection
    - Record/playback mode
    """
    
    def __init__(self, config: Optional[MockProviderConfig] = None):
        self.config = config or MockProviderConfig()
        self._rng = random.Random(self.config.seed)
        self._recordings: List[Dict[str, Any]] = []
        self._playback_index = 0
        
        # Load playback file if specified
        if self.config.playback_file:
            self._load_playback()
        
        # Setup default responses
        self._setup_defaults()
    
    def _setup_defaults(self) -> None:
        """Setup default canned responses."""
        defaults = {
            "hello": MockResponse(
                content="Hello! I'm a mock AI assistant. How can I help you today?",
                tokens=20,
                cost=0.0001,
            ),
            "help": MockResponse(
                content="I can help you with various tasks. Just ask me anything!",
                tokens=15,
                cost=0.00008,
            ),
            "test": MockResponse(
                content="This is a test response. Everything is working correctly.",
                tokens=12,
                cost=0.00006,
            ),
            "error": MockResponse(
                content="",
                error="Simulated error for testing",
            ),
            "tool": MockResponse(
                content="I'll use a tool to help with that.",
                tool_calls=[{
                    "id": "call_mock_001",
                    "name": "mock_tool",
                    "arguments": {"query": "test"},
                }],
                tokens=25,
                cost=0.00012,
            ),
        }
        
        for pattern, response in defaults.items():
            if pattern not in self.config.responses:
                self.config.responses[pattern] = response
        
        if not self.config.default_response:
            self.config.default_response = MockResponse(
                content="I understand your request. Here's a mock response for testing purposes. "
                        "This response is generated deterministically based on the input.",
                tokens=30,
                cost=0.00015,
            )
    
    def _load_playback(self) -> None:
        """Load recordings for playback."""
        if not self.config.playback_file:
            return
        
        path = Path(self.config.playback_file)
        if path.exists():
            with open(path) as f:
                for line in f:
                    self._recordings.append(json.loads(line))
    
    def _save_recording(self, input_content: str, response: MockResponse) -> None:
        """Save a recording."""
        if not self.config.record_mode or not self.config.playback_file:
            return
        
        record = {
            "timestamp": time.time(),
            "input": input_content,
            "response": {
                "content": response.content,
                "chunks": response.chunks,
                "tool_calls": response.tool_calls,
                "tokens": response.tokens,
                "cost": response.cost,
            }
        }
        
        path = Path(self.config.playback_file)
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    
    def _get_response(self, input_content: str) -> MockResponse:
        """Get response for input."""
        # Check playback mode
        if self._recordings and self._playback_index < len(self._recordings):
            record = self._recordings[self._playback_index]
            self._playback_index += 1
            return MockResponse(**record["response"])
        
        # Check for pattern match
        input_lower = input_content.lower()
        for pattern, response in self.config.responses.items():
            if pattern in input_lower:
                return response
        
        # Simulate random error
        if self.config.simulate_errors and self._rng.random() < self.config.error_rate:
            return MockResponse(content="", error="Random simulated error")
        
        # Generate deterministic response based on input hash
        input_hash = hashlib.md5(input_content.encode()).hexdigest()
        seed = int(input_hash[:8], 16)
        rng = random.Random(seed)
        
        # Generate varied response
        templates = [
            "I've processed your request about '{topic}'. Here's what I found...",
            "Regarding '{topic}', I can provide the following information...",
            "Thank you for asking about '{topic}'. Let me explain...",
            "Based on your query about '{topic}', here's my response...",
        ]
        
        topic = input_content[:30] if len(input_content) > 30 else input_content
        template = rng.choice(templates)
        content = template.format(topic=topic)
        
        # Add some mock content
        content += " This is a deterministic mock response generated for testing. "
        content += f"Input hash: {input_hash[:8]}. "
        content += "The response is reproducible given the same input."
        
        return MockResponse(
            content=content,
            tokens=len(content.split()) * 2,
            cost=len(content) * 0.000001,
        )
    
    async def generate(
        self,
        input_content: str,
        model: str = "mock-model",
        stream: bool = True,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a mock response.
        
        Args:
            input_content: The input prompt
            model: Model name (ignored for mock)
            stream: Whether to stream the response
            on_chunk: Callback for streaming chunks
            
        Returns:
            Response dict with content, tokens, cost
        """
        response = self._get_response(input_content)
        
        # Record if in record mode
        if self.config.record_mode:
            self._save_recording(input_content, response)
        
        # Check for error
        if response.error:
            raise Exception(response.error)
        
        # Stream chunks
        if stream and on_chunk:
            for chunk in response.chunks:
                await asyncio.sleep(response.delay_per_chunk)
                on_chunk(chunk)
        else:
            # Non-streaming delay
            await asyncio.sleep(len(response.chunks) * response.delay_per_chunk)
        
        return {
            "content": response.content,
            "tokens": response.tokens,
            "cost": response.cost,
            "tool_calls": response.tool_calls,
            "model": model,
        }
    
    async def stream(
        self,
        input_content: str,
        model: str = "mock-model",
    ) -> AsyncIterator[str]:
        """
        Stream a mock response.
        
        Yields chunks of the response.
        """
        response = self._get_response(input_content)
        
        if response.error:
            raise Exception(response.error)
        
        for chunk in response.chunks:
            await asyncio.sleep(response.delay_per_chunk)
            yield chunk
    
    def reset(self) -> None:
        """Reset provider state."""
        self._rng = random.Random(self.config.seed)
        self._playback_index = 0


class MockExecutor:
    """
    Mock executor for queue worker testing.
    
    Simulates agent execution with configurable behavior.
    """
    
    def __init__(self, provider: Optional[MockProvider] = None):
        self.provider = provider or MockProvider()
    
    async def execute(
        self,
        input_content: str,
        agent_config: Dict[str, Any],
        on_output: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Execute a mock agent run."""
        model = agent_config.get("model", "mock-model")
        
        result = await self.provider.generate(
            input_content=input_content,
            model=model,
            stream=True,
            on_chunk=on_output,
        )
        
        return {
            "output": result["content"],
            "metrics": {
                "tokens": result["tokens"],
                "cost": result["cost"],
            },
            "tool_calls": result.get("tool_calls", []),
        }


# Convenience function for tests
def create_mock_provider(
    seed: int = 42,
    responses: Optional[Dict[str, str]] = None,
) -> MockProvider:
    """Create a mock provider with optional custom responses."""
    config = MockProviderConfig(seed=seed)
    
    if responses:
        for pattern, content in responses.items():
            config.responses[pattern] = MockResponse(content=content)
    
    return MockProvider(config)
