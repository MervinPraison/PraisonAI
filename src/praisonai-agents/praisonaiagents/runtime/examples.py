"""Example runtime implementations demonstrating extensibility.

These are reference implementations showing how to create custom runtimes.
They are not intended for production use.
"""

from typing import AsyncIterator, Optional
import asyncio

from .protocols import (
    AgentRuntimeProtocol,
    StreamingRuntimeProtocol,
    RuntimeResult,
    RuntimeDelta
)


class MockRuntime:
    """Mock runtime for testing and demonstration.
    
    A simple runtime that returns predefined responses.
    Useful for testing runtime registry and protocol compliance.
    """
    
    def __init__(self, response: str = "Mock response"):
        """Initialize mock runtime with predefined response."""
        self.runtime_id = "mock"
        self.response = response
        
    def supports(self, model_ref: Optional[str] = None) -> bool:
        """Mock runtime supports all models."""
        return True
        
    async def run_turn(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        model_ref: Optional[str] = None,
        **kwargs
    ) -> RuntimeResult:
        """Return predefined response."""
        return RuntimeResult(
            content=self.response,
            metadata={
                'runtime': self.runtime_id,
                'prompt': prompt,
                'model': model_ref
            }
        )
        
    async def stream_turn(
        self,
        prompt: str,
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Stream mock response as single delta."""
        yield RuntimeDelta(
            type="text",
            content=self.response,
            metadata={'runtime': self.runtime_id}
        )


class EchoRuntime:
    """Echo runtime that returns the input prompt.
    
    Demonstrates a minimal runtime implementation that
    simply echoes back the user's input. Useful for debugging
    and understanding the runtime protocol.
    """
    
    def __init__(self):
        """Initialize echo runtime."""
        self.runtime_id = "echo"
        
    def supports(self, model_ref: Optional[str] = None) -> bool:
        """Echo runtime supports all models."""
        return True
        
    async def run_turn(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        model_ref: Optional[str] = None,
        **kwargs
    ) -> RuntimeResult:
        """Echo back the prompt."""
        response = f"Echo: {prompt}"
        if system_prompt:
            response = f"{system_prompt}\n{response}"
            
        return RuntimeResult(
            content=response,
            metadata={
                'runtime': self.runtime_id,
                'echoed_length': len(prompt)
            }
        )
        
    async def stream_turn(
        self,
        prompt: str,
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Stream echo response."""
        system_prompt = kwargs.get('system_prompt')
        
        if system_prompt:
            yield RuntimeDelta(
                type="text",
                content=f"{system_prompt}\n",
                metadata={'runtime': self.runtime_id}
            )
            
        yield RuntimeDelta(
            type="text",
            content=f"Echo: {prompt}",
            metadata={'runtime': self.runtime_id}
        )


class DelayedStreamingRuntime:
    """Example runtime with simulated incremental streaming.
    
    Demonstrates how a runtime would implement true incremental
    streaming when the underlying implementation supports it.
    This example simulates streaming by breaking the response
    into chunks with delays.
    """
    
    def __init__(self, chunk_delay: float = 0.1):
        """Initialize with configurable chunk delay."""
        self.runtime_id = "delayed-streaming"
        self.chunk_delay = chunk_delay
        
    def supports(self, model_ref: Optional[str] = None) -> bool:
        """Support all models for demonstration."""
        return True
        
    def supports_incremental_streaming(self) -> bool:
        """This runtime supports true incremental streaming."""
        return True
        
    async def run_turn(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        model_ref: Optional[str] = None,
        **kwargs
    ) -> RuntimeResult:
        """Execute and return full response."""
        response = f"Processing: {prompt[:50]}..."
        
        return RuntimeResult(
            content=response,
            metadata={
                'runtime': self.runtime_id,
                'streaming_supported': True
            }
        )
        
    async def stream_turn(
        self,
        prompt: str,
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Stream with simulated delays."""
        response = f"Processing: {prompt[:50]}..."
        
        # Simulate incremental streaming
        words = response.split()
        for i, word in enumerate(words):
            await asyncio.sleep(self.chunk_delay)
            
            # Add space except for first word
            content = word if i == 0 else f" {word}"
            
            yield RuntimeDelta(
                type="text",
                content=content,
                metadata={
                    'runtime': self.runtime_id,
                    'chunk_index': i
                }
            )
            
    async def stream_turn_incremental(
        self,
        prompt: str,
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Enhanced streaming with finer granularity.
        
        This would be called when the consumer detects
        StreamingRuntimeProtocol support.
        """
        response = f"Processing: {prompt[:50]}..."
        
        # Simulate character-by-character streaming
        for i, char in enumerate(response):
            await asyncio.sleep(self.chunk_delay / 10)  # Faster for chars
            
            yield RuntimeDelta(
                type="text",
                content=char,
                metadata={
                    'runtime': self.runtime_id,
                    'char_index': i,
                    'incremental': True
                }
            )