"""Full-featured LiteLLM provider with multi-model support"""

import os
from typing import Dict, List, Any, Optional, Union, AsyncIterator, Iterator
from .base import LLMProvider


class LiteLLMProvider(LLMProvider):
    """Full-featured provider with multi-model support via LiteLLM."""
    
    def __init__(self, **kwargs):
        """
        Initialize LiteLLM provider with lazy loading.
        
        Args:
            **kwargs: Provider-specific configuration (api_key, base_url, etc.)
        """
        self._litellm = None
        self.kwargs = kwargs
        
        # Store API key and base URL if provided
        self.api_key = kwargs.get('api_key')
        self.base_url = kwargs.get('base_url')
    
    @property
    def litellm(self):
        """Lazy-load litellm on first use to minimize import time."""
        if self._litellm is None:
            try:
                import litellm
                
                # Configure litellm
                litellm.telemetry = False
                litellm.set_verbose = False
                litellm.drop_params = True
                litellm.modify_params = True
                os.environ["LITELLM_TELEMETRY"] = "False"
                
                # Set API key and base URL if provided
                if self.api_key:
                    # Determine which provider based on model or explicit config
                    if self.kwargs.get('model', '').startswith('claude'):
                        os.environ["ANTHROPIC_API_KEY"] = self.api_key
                    elif self.kwargs.get('model', '').startswith('gemini'):
                        os.environ["GEMINI_API_KEY"] = self.api_key
                    else:
                        os.environ["OPENAI_API_KEY"] = self.api_key
                
                if self.base_url:
                    os.environ["OPENAI_API_BASE"] = self.base_url
                
                self._litellm = litellm
            except ImportError:
                raise ImportError(
                    "LiteLLM is required for multi-provider support. "
                    "Install with: pip install 'praisonaiagents[llm]' or pip install litellm"
                )
        return self._litellm
    
    def completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[Dict, Iterator[Dict]]:
        """
        Use LiteLLM for completion with multi-provider support.
        
        Args:
            messages: List of message dictionaries
            model: Model name (can include provider prefix like "anthropic/claude-3")
            temperature: Sampling temperature
            tools: Optional tool definitions
            stream: Whether to stream response
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LiteLLM completion response or stream
        """
        # Build parameters
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
        
        # Merge initialization kwargs and call kwargs
        params.update(self.kwargs)
        params.update(kwargs)
        
        # Remove duplicate keys that shouldn't be passed to completion
        for key in ['api_key', 'base_url']:
            params.pop(key, None)
        
        # Make the LiteLLM call
        response = self.litellm.completion(**params)
        
        return response
    
    async def acompletion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[Dict, AsyncIterator[Dict]]:
        """
        Use LiteLLM for async completion with multi-provider support.
        
        Args:
            messages: List of message dictionaries
            model: Model name (can include provider prefix)
            temperature: Sampling temperature
            tools: Optional tool definitions
            stream: Whether to stream response
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LiteLLM async completion response or stream
        """
        # Build parameters
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
        
        # Merge initialization kwargs and call kwargs
        params.update(self.kwargs)
        params.update(kwargs)
        
        # Remove duplicate keys
        for key in ['api_key', 'base_url']:
            params.pop(key, None)
        
        # Make the async LiteLLM call
        response = await self.litellm.acompletion(**params)
        
        return response
    
    def get_context_window(self, model: str) -> int:
        """
        Get context window using LiteLLM's model database.
        
        Args:
            model: Model name (can include provider prefix)
            
        Returns:
            Context window size in tokens
        """
        try:
            # LiteLLM has built-in model context windows
            model_info = self.litellm.get_model_info(model)
            
            # Try different keys where context window might be stored
            for key in ['max_tokens', 'max_input_tokens', 'context_window']:
                if key in model_info:
                    # Return 75% of actual for safety margin
                    return int(model_info[key] * 0.75)
            
            # If not found in model info, check if it's in the model cost map
            if hasattr(self.litellm, 'model_cost') and model in self.litellm.model_cost:
                cost_info = self.litellm.model_cost[model]
                if 'max_tokens' in cost_info:
                    return int(cost_info['max_tokens'] * 0.75)
                    
        except Exception as e:
            # Log the error but don't fail
            import logging
            logging.debug(f"Could not get context window for {model}: {e}")
        
        # Safe default if model not found
        return 4000