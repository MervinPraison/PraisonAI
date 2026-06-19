"""Built-in PraisonAI runtime implementation.

Implements the default embedded runtime that wraps the existing ChatMixin 
and execution logic without duplicating code.
"""

import asyncio
from typing import Optional, AsyncIterator, Dict, Any

from .protocols import AgentRuntimeProtocol, RuntimeResult, RuntimeDelta


class PraisonAIRuntime:
    """Built-in PraisonAI runtime implementation.
    
    This runtime wraps the existing ChatMixin / unified execution loop
    to provide a runtime abstraction without duplicating logic.
    """
    
    def __init__(self):
        """Initialize the PraisonAI runtime."""
        self.runtime_id = "praisonai"
        
    def supports(self, model_ref: Optional[str] = None) -> bool:
        """Check if this runtime supports the given model reference.
        
        The built-in runtime supports all models that the current
        LLM subsystem supports.
        
        Args:
            model_ref: Optional model reference
            
        Returns:
            True - the built-in runtime is designed to be universal
        """
        # The built-in runtime delegates to the LLM subsystem,
        # so it supports whatever models are configured there
        return True
    
    async def run_turn(
        self, 
        prompt: str, 
        *,
        system_prompt: Optional[str] = None,
        model_ref: Optional[str] = None,
        **kwargs
    ) -> RuntimeResult:
        """Execute a single turn using the embedded agent logic.
        
        Args:
            prompt: User prompt/query
            system_prompt: Optional system prompt
            model_ref: Optional model reference
            **kwargs: Additional runtime-specific options
            
        Returns:
            RuntimeResult with response content and metadata
        """
        try:
            # Import agent here to avoid circular imports
            from ..agent.agent import Agent
            
            # Create a minimal agent instance for execution
            # Use model_ref if provided, otherwise use default
            agent_kwargs = {}
            if model_ref:
                agent_kwargs['model'] = model_ref
            if system_prompt:
                # Agent uses 'instructions' not 'system_prompt'
                agent_kwargs['instructions'] = system_prompt
                
            # Tools can be passed to Agent constructor
            if 'tools' in kwargs:
                agent_kwargs['tools'] = kwargs['tools']
                
            # Create agent instance using async context manager for proper cleanup
            async with Agent(**agent_kwargs) as agent:
                # Prepare achat kwargs - these go to achat, not Agent constructor
                chat_kwargs = {}
                if 'max_tokens' in kwargs:
                    # max_tokens might need to be in model config, handle gracefully
                    chat_kwargs['config'] = {'max_tokens': kwargs['max_tokens']}
                if 'temperature' in kwargs:
                    chat_kwargs['temperature'] = kwargs['temperature']
                    
                # Execute the prompt using agent's chat capabilities
                result = await agent.achat(prompt, **chat_kwargs)
                
                # Extract metadata from agent
                metadata = {
                    'model': getattr(agent, 'model', None),
                    'agent_id': getattr(agent, 'agent_id', None),
                    'runtime': self.runtime_id
                }
                
                # Check if result is empty (might indicate API key issue)
                if not result:
                    # Check for common API key issues
                    import os
                    if not os.environ.get('OPENAI_API_KEY'):
                        return RuntimeResult(
                            content="",
                            metadata=metadata,
                            error="OPENAI_API_KEY environment variable is required"
                        )
                
                return RuntimeResult(
                    content=str(result) if result else "",
                    metadata=metadata
                )
            
        except Exception as e:
            return RuntimeResult(
                content="",
                metadata={'runtime': self.runtime_id},
                error=str(e)
            )
    
    async def stream_turn(
        self, 
        prompt: str, 
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Stream response deltas from runtime execution.
        
        NOTE: The current Agent implementation doesn't support true async streaming.
        The `achat(stream=True)` returns a string, not an AsyncIterator. 
        As a workaround, this returns the full response as a single delta.
        
        Args:
            prompt: User prompt/query
            **kwargs: Additional options (system_prompt, model_ref, etc.)
            
        Yields:
            RuntimeDelta objects with incremental response content
        """
        try:
            # Import agent here to avoid circular imports
            from ..agent.agent import Agent
            import os
            
            # Extract parameters
            system_prompt = kwargs.get('system_prompt')
            model_ref = kwargs.get('model_ref')
            
            # Create agent kwargs
            agent_kwargs = {}
            if model_ref:
                agent_kwargs['model'] = model_ref
            if system_prompt:
                # Agent uses 'instructions' not 'system_prompt'
                agent_kwargs['instructions'] = system_prompt
                
            # Tools can be passed to Agent constructor
            if 'tools' in kwargs:
                agent_kwargs['tools'] = kwargs['tools']
                
            # Create agent instance using async context manager
            async with Agent(**agent_kwargs) as agent:
                # Prepare achat kwargs
                chat_kwargs = {}
                if 'max_tokens' in kwargs:
                    chat_kwargs['config'] = {'max_tokens': kwargs['max_tokens']}
                if 'temperature' in kwargs:
                    chat_kwargs['temperature'] = kwargs['temperature']
                    
                # Call achat - it returns a string, not an iterator
                # The stream=True parameter affects display but doesn't change return type
                result = await agent.achat(prompt, **chat_kwargs)
                
                # Check for API key and return appropriate error
                if not result and not os.environ.get('OPENAI_API_KEY'):
                    yield RuntimeDelta(
                        type="error",
                        content="OPENAI_API_KEY environment variable is required",
                        metadata={'runtime': self.runtime_id}
                    )
                else:
                    # Return the full response as a single delta
                    # This is the current limitation - no true streaming
                    yield RuntimeDelta(
                        type="text",
                        content=str(result) if result else "",
                        metadata={'runtime': self.runtime_id}
                    )
                    
        except Exception as e:
            yield RuntimeDelta(
                type="error",
                content=str(e),
                metadata={'runtime': self.runtime_id}
            )
