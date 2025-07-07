"""Full-featured LiteLLM provider with multi-model support"""

import os
import threading
from typing import Dict, List, Optional, Union, AsyncIterator, Iterator
from .base import LLMProvider


class LiteLLMProvider(LLMProvider):
    """Thread-safe provider with multi-model support via LiteLLM."""
    
    # Class-level lock for thread-safe module initialization
    _litellm_lock = threading.Lock()
    _litellm_module = None
    _litellm_initialized = False
    
    def __init__(self, **kwargs):
        """
        Initialize LiteLLM provider with lazy loading.
        
        Args:
            **kwargs: Provider-specific configuration (api_key, base_url, etc.)
        """
        self.kwargs = kwargs
        
        # Store API key and base URL if provided
        self.api_key = kwargs.get('api_key')
        self.base_url = kwargs.get('base_url')
        self.model = kwargs.get('model', '')
    
    @classmethod
    def _get_litellm(cls):
        """Thread-safe lazy loading of litellm module."""
        if cls._litellm_module is None:
            with cls._litellm_lock:
                # Double-check pattern for thread safety
                if cls._litellm_module is None:
                    try:
                        import litellm
                        
                        # Configure litellm only once at module level
                        if not cls._litellm_initialized:
                            litellm.telemetry = False
                            litellm.set_verbose = False
                            litellm.drop_params = True
                            litellm.modify_params = True
                            # Suppress debug messages by default
                            litellm.suppress_debug_info = True
                            # Set this once to avoid repeated checks
                            os.environ["LITELLM_TELEMETRY"] = "False"
                            cls._litellm_initialized = True
                        
                        cls._litellm_module = litellm
                    except ImportError as e:
                        raise ImportError(
                            "LiteLLM is required for multi-provider support. "
                            "Install with: pip install 'praisonaiagents[llm]' or pip install litellm"
                        ) from e
        return cls._litellm_module
    
    @property
    def litellm(self):
        """Get the litellm module (for backward compatibility)."""
        return self._get_litellm()
    
    def _build_completion_params(self, **call_kwargs) -> Dict[str, Union[str, List, Dict, float, bool]]:
        """Build parameters for litellm completion call with per-request credentials."""
        params = {}
        
        # Add API credentials based on model/provider
        if self.api_key:
            # LiteLLM supports passing API keys directly in the request
            params['api_key'] = self.api_key
            
            # Also add provider-specific keys for better compatibility
            if call_kwargs.get('model', self.model).startswith(('claude', 'anthropic/')):
                params['anthropic_api_key'] = self.api_key
            elif call_kwargs.get('model', self.model).startswith(('gemini', 'vertex_ai/', 'google/')):
                params['vertex_ai_api_key'] = self.api_key
                params['gemini_api_key'] = self.api_key
            elif call_kwargs.get('model', self.model).startswith('cohere/'):
                params['cohere_api_key'] = self.api_key
            elif call_kwargs.get('model', self.model).startswith('replicate/'):
                params['replicate_api_key'] = self.api_key
            elif call_kwargs.get('model', self.model).startswith('bedrock/'):
                params['aws_access_key_id'] = self.api_key
            # OpenAI is the default
        
        # Add base URL if provided
        if self.base_url:
            params['api_base'] = self.base_url
            params['base_url'] = self.base_url
        
        # Merge stored kwargs (from initialization)
        for k, v in self.kwargs.items():
            if k not in ['api_key', 'base_url', 'model'] and v is not None:
                params[k] = v
        
        # Merge call-time kwargs (override init kwargs)
        params.update(call_kwargs)
        
        # Remove None values and internal keys
        return {k: v for k, v in params.items() if v is not None}
    
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
        Thread-safe completion with per-request credentials.
        
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
        litellm = self._get_litellm()
        
        # Build parameters with credentials
        params = self._build_completion_params(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=stream,
            tools=tools,
            **kwargs
        )
        
        # Make the LiteLLM call with per-request params
        response = litellm.completion(**params)
        
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
        Thread-safe async completion with per-request credentials.
        
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
        litellm = self._get_litellm()
        
        # Build parameters with credentials
        params = self._build_completion_params(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=stream,
            tools=tools,
            **kwargs
        )
        
        # Make the async LiteLLM call
        response = await litellm.acompletion(**params)
        
        return response
    
    def get_context_window(self, model: str) -> int:
        """
        Get context window using LiteLLM's model database (thread-safe).
        
        Args:
            model: Model name (can include provider prefix)
            
        Returns:
            Context window size in tokens
        """
        litellm = self._get_litellm()
        
        try:
            # LiteLLM has built-in model context windows
            model_info = litellm.get_model_info(model)
            
            # Try different keys where context window might be stored
            for key in ['max_tokens', 'max_input_tokens', 'context_window']:
                if key in model_info:
                    # Return 75% of actual for safety margin
                    return int(model_info[key] * 0.75)
            
            # If not found in model info, check if it's in the model cost map
            if hasattr(litellm, 'model_cost') and model in litellm.model_cost:
                cost_info = litellm.model_cost[model]
                if 'max_tokens' in cost_info:
                    return int(cost_info['max_tokens'] * 0.75)
                    
        except Exception as e:
            # Log the error but don't fail
            import logging
            logging.debug(f"Could not get context window for {model}: {e}")
        
        # Safe default if model not found
        return 4000