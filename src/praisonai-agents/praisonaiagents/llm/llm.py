import logging
import os
import warnings
import re
import inspect
from typing import Any, Dict, List, Optional, Union, Literal, Callable
from pydantic import BaseModel
import time
import json
from ..main import (
    display_error,
    display_tool_call,
    display_instruction,
    display_interaction,
    display_generating,
    display_self_reflection,
    ReflectionOutput,
    execute_sync_callback,
)
from rich.console import Console
from rich.live import Live

# Import token tracking
try:
    from ..telemetry.token_collector import TokenMetrics, _token_collector
except ImportError:
    TokenMetrics = None
    _token_collector = None

# Logging is already configured in _logging.py via __init__.py

# TODO: Include in-build tool calling in LLM class
# TODO: Restructure so that duplicate calls are not made (Sync with agent.py)
class LLMContextLengthExceededException(Exception):
    """Raised when LLM context length is exceeded"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

    def _is_context_limit_error(self, error_message: str) -> bool:
        """Check if error is related to context length"""
        context_limit_phrases = [
            "maximum context length",
            "context window is too long",
            "context length exceeded",
            "context_length_exceeded"
        ]
        return any(phrase in error_message.lower() for phrase in context_limit_phrases)

class LLM:
    """
    Easy to use wrapper for language models. Supports multiple providers like OpenAI, 
    Anthropic, and others through LiteLLM.
    """
    
    # Class-level flag for one-time logging configuration
    _logging_configured = False
    
    # Default window sizes for different models (75% of actual to be safe)
    MODEL_WINDOWS = {
        # OpenAI
        "gpt-4": 6144,                    # 8,192 actual
        "gpt-4o": 96000,                  # 128,000 actual
        "gpt-4o-mini": 96000,            # 128,000 actual
        "gpt-4-turbo": 96000,            # 128,000 actual
        "o1-preview": 96000,             # 128,000 actual
        "o1-mini": 96000,                # 128,000 actual
        
        # Anthropic
        "claude-3-5-sonnet": 12288,       # 16,384 actual
        "claude-3-sonnet": 12288,         # 16,384 actual
        "claude-3-opus": 96000,           # 128,000 actual
        "claude-3-haiku": 96000,          # 128,000 actual
        
        # Gemini
        "gemini-2.0-flash": 786432,       # 1,048,576 actual
        "gemini-1.5-pro": 1572864,        # 2,097,152 actual
        "gemini-1.5-flash": 786432,       # 1,048,576 actual
        "gemini-1.5-flash-8b": 786432,    # 1,048,576 actual
        
        # Deepseek
        "deepseek-chat": 96000,           # 128,000 actual
        
        # Groq
        "gemma2-9b-it": 6144,            # 8,192 actual
        "gemma-7b-it": 6144,             # 8,192 actual
        "llama3-70b-8192": 6144,         # 8,192 actual
        "llama3-8b-8192": 6144,          # 8,192 actual
        "mixtral-8x7b-32768": 24576,     # 32,768 actual
        "llama-3.3-70b-versatile": 96000, # 128,000 actual
        "llama-3.3-70b-instruct": 96000,  # 128,000 actual
        
        # Other llama models
        "llama-3.1-70b-versatile": 98304, # 131,072 actual
        "llama-3.1-8b-instant": 98304,    # 131,072 actual
        "llama-3.2-1b-preview": 6144,     # 8,192 actual
        "llama-3.2-3b-preview": 6144,     # 8,192 actual
        "llama-3.2-11b-text-preview": 6144,  # 8,192 actual
        "llama-3.2-90b-text-preview": 6144   # 8,192 actual
    }

    # Ollama-specific prompt constants
    OLLAMA_TOOL_USAGE_PROMPT = "Please analyze the request and use the available tools to help answer the question. Start by identifying what information you need."
    OLLAMA_FINAL_ANSWER_PROMPT = "Based on the tool results above, please provide the final answer to the original question."
    
    # Ollama iteration threshold for summary generation
    OLLAMA_SUMMARY_ITERATION_THRESHOLD = 1

    @classmethod
    def _configure_logging(cls):
        """Configure logging settings once for all LLM instances."""
        try:
            import litellm
            # Disable telemetry
            litellm.telemetry = False
            
            # Set litellm options globally
            litellm.set_verbose = False
            litellm.success_callback = []
            litellm._async_success_callback = []
            litellm.callbacks = []
            
            # Suppress all litellm debug info
            litellm.suppress_debug_info = True
            if hasattr(litellm, '_logging'):
                litellm._logging._disable_debugging()
            
            # Always suppress litellm's internal debug messages
            logging.getLogger("litellm.utils").setLevel(logging.WARNING)
            logging.getLogger("litellm.main").setLevel(logging.WARNING)
            logging.getLogger("litellm.litellm_logging").setLevel(logging.WARNING)
            logging.getLogger("litellm.transformation").setLevel(logging.WARNING)
            
            # Allow httpx logging when LOGLEVEL=debug, otherwise suppress it
            loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
            if loglevel == 'DEBUG':
                logging.getLogger("litellm.llms.custom_httpx.http_handler").setLevel(logging.INFO)
            else:
                logging.getLogger("litellm.llms.custom_httpx.http_handler").setLevel(logging.WARNING)
            
            # Keep asyncio at WARNING unless explicitly in high debug mode
            logging.getLogger("asyncio").setLevel(logging.WARNING)
            logging.getLogger("selector_events").setLevel(logging.WARNING)
            
            # Enable error dropping for cleaner output
            litellm.drop_params = True
            # Enable parameter modification for providers like Anthropic
            litellm.modify_params = True
            
            if hasattr(litellm, '_logging'):
                litellm._logging._disable_debugging()
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            
            cls._logging_configured = True
            
        except ImportError:
            # If litellm not installed, we'll handle it in __init__
            pass

    def _log_llm_config(self, method_name: str, **config):
        """Centralized debug logging for LLM configuration and parameters.
        
        Args:
            method_name: The name of the method calling this logger (e.g., '__init__', 'get_response')
            **config: Configuration parameters to log
        """
        # Check for debug logging - either global debug level OR explicit verbose mode
        verbose = config.get('verbose', self.verbose if hasattr(self, 'verbose') else False)
        should_log = logging.getLogger().getEffectiveLevel() == logging.DEBUG or (not isinstance(verbose, bool) and verbose >= 10)
        
        if should_log:
            # Mask sensitive information
            safe_config = config.copy()
            if 'api_key' in safe_config:
                safe_config['api_key'] = "***" if safe_config['api_key'] is not None else None
            if 'extra_settings' in safe_config and isinstance(safe_config['extra_settings'], dict):
                safe_config['extra_settings'] = {k: v for k, v in safe_config['extra_settings'].items() if k not in ["api_key"]}
            
            # Handle special formatting for certain fields
            if 'prompt' in safe_config:
                prompt = safe_config['prompt']
                # Convert to string first for consistent logging behavior
                prompt_str = str(prompt) if not isinstance(prompt, str) else prompt
                if len(prompt_str) > 100:
                    safe_config['prompt'] = prompt_str[:100] + "..."
                else:
                    safe_config['prompt'] = prompt_str
            if 'system_prompt' in safe_config:
                sp = safe_config['system_prompt']
                if sp and isinstance(sp, str) and len(sp) > 100:
                    safe_config['system_prompt'] = sp[:100] + "..."
            if 'chat_history' in safe_config:
                ch = safe_config['chat_history']
                safe_config['chat_history'] = f"[{len(ch)} messages]" if ch else None
            if 'tools' in safe_config:
                tools = safe_config['tools']
                # Check if tools is iterable before processing
                if tools and isinstance(tools, (list, tuple)):
                    safe_config['tools'] = [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools]
                elif tools and callable(tools):
                    safe_config['tools'] = tools.__name__ if hasattr(tools, "__name__") else str(tools)
                else:
                    safe_config['tools'] = None
            if 'output_json' in safe_config:
                oj = safe_config['output_json']
                safe_config['output_json'] = str(oj.__class__.__name__) if oj else None
            if 'output_pydantic' in safe_config:
                op = safe_config['output_pydantic']
                safe_config['output_pydantic'] = str(op.__class__.__name__) if op else None
            
            # Log based on method name - check more specific conditions first
            if method_name == '__init__':
                logging.debug(f"LLM instance initialized with: {json.dumps(safe_config, indent=2, default=str)}")
            elif "parameters" in method_name:
                logging.debug(f"{method_name}: {json.dumps(safe_config, indent=2, default=str)}")
            elif "_async" in method_name:
                logging.debug(f"LLM async instance configuration: {json.dumps(safe_config, indent=2, default=str)}")
            else:
                logging.debug(f"{method_name} configuration: {json.dumps(safe_config, indent=2, default=str)}")

    def __init__(
        self,
        model: str,
        timeout: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        n: Optional[int] = None,
        max_tokens: Optional[int] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        logit_bias: Optional[Dict[int, float]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        logprobs: Optional[bool] = None,
        top_logprobs: Optional[int] = None,
        api_version: Optional[str] = None,
        stop_phrases: Optional[Union[str, List[str]]] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        events: List[Any] = [],
        **extra_settings
    ):
        # Configure logging only once at the class level
        if not LLM._logging_configured:
            LLM._configure_logging()
            
        # Import litellm after logging is configured
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "LiteLLM is required but not installed. "
                "Please install with: pip install 'praisonaiagents[llm]'"
            )

        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p
        self.n = n
        self.max_tokens = max_tokens
        self.presence_penalty = presence_penalty
        self.frequency_penalty = frequency_penalty
        self.logit_bias = logit_bias
        self.response_format = response_format
        self.seed = seed
        self.logprobs = logprobs
        self.top_logprobs = top_logprobs
        self.api_version = api_version
        self.stop_phrases = stop_phrases
        self.api_key = api_key
        self.base_url = base_url
        self.events = events
        self.extra_settings = extra_settings
        self._console = None  # Lazy load console when needed
        self.chat_history = []
        self.verbose = extra_settings.get('verbose', True)
        self.markdown = extra_settings.get('markdown', True)
        self.self_reflect = extra_settings.get('self_reflect', False)
        self.max_reflect = extra_settings.get('max_reflect', 3)
        self.min_reflect = extra_settings.get('min_reflect', 1)
        self.reasoning_steps = extra_settings.get('reasoning_steps', False)
        self.metrics = extra_settings.get('metrics', False)
        
        # Token tracking
        self.last_token_metrics: Optional[TokenMetrics] = None
        self.session_token_metrics: Optional[TokenMetrics] = None
        self.current_agent_name: Optional[str] = None
        
        # Cache for formatted tools and messages
        self._formatted_tools_cache = {}
        self._max_cache_size = 100
        
        # Enable error dropping for cleaner output
        import litellm
        litellm.drop_params = True
        # Enable parameter modification for providers like Anthropic
        litellm.modify_params = True
        self._setup_event_tracking(events)
        
        # Log all initialization parameters when in debug mode or verbose >= 10
        self._log_llm_config(
            '__init__',
            model=self.model,
            timeout=self.timeout,
            temperature=self.temperature,
            top_p=self.top_p,
            n=self.n,
            max_tokens=self.max_tokens,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
            logit_bias=self.logit_bias,
            response_format=self.response_format,
            seed=self.seed,
            logprobs=self.logprobs,
            top_logprobs=self.top_logprobs,
            api_version=self.api_version,
            stop_phrases=self.stop_phrases,
            api_key=self.api_key,
            base_url=self.base_url,
            verbose=self.verbose,
            markdown=self.markdown,
            self_reflect=self.self_reflect,
            max_reflect=self.max_reflect,
            min_reflect=self.min_reflect,
            reasoning_steps=self.reasoning_steps,
            extra_settings=self.extra_settings
        )
    
    @property
    def console(self):
        """Lazily initialize Rich Console only when needed."""
        if self._console is None:
            from rich.console import Console
            self._console = Console()
        return self._console

    def _is_ollama_provider(self) -> bool:
        """Detect if this is an Ollama provider regardless of naming convention"""
        if not self.model:
            return False
        
        # Direct ollama/ prefix
        if self.model.startswith("ollama/"):
            return True
        
        # Check base_url if provided
        if self.base_url and "ollama" in self.base_url.lower():
            return True
            
        # Check environment variables for Ollama base URL
        base_url = os.getenv("OPENAI_BASE_URL", "")
        api_base = os.getenv("OPENAI_API_BASE", "")
        
        # Common Ollama endpoints (including custom ports)
        if any(url and ("ollama" in url.lower() or ":11434" in url) 
               for url in [base_url, api_base, self.base_url or ""]):
            return True
        
        return False

    def _is_qwen_provider(self) -> bool:
        """Detect if this is a Qwen provider"""
        if not self.model:
            return False
        
        # Direct qwen/ prefix or Qwen in model name
        model_lower = self.model.lower()
        if any(pattern in model_lower for pattern in ["qwen", "qwen2", "qwen2.5"]):
            return True
        
        # OpenAI-compatible API serving Qwen models
        if "openai/" in self.model and any(pattern in model_lower for pattern in ["qwen", "qwen2", "qwen2.5"]):
            return True
            
        return False

    def _generate_ollama_tool_summary(self, tool_results: List[Any], response_text: str) -> Optional[str]:
        """
        Generate a summary from tool results for Ollama to prevent infinite loops.
        
        This prevents infinite loops where Ollama provides an empty response after a
        tool call, expecting the user to prompt for a summary.

        Args:
            tool_results: The list of results from tool execution.
            response_text: The text response from the LLM.

        Returns:
            A summary string if conditions are met, otherwise None.
        """
        # Constant for minimal response length check
        OLLAMA_MIN_RESPONSE_LENGTH = 10
        
        # Only generate summary for Ollama with tool results
        if not (self._is_ollama_provider() and tool_results):
            return None

        # For Ollama, always generate summary when we have tool results
        # This prevents infinite loops caused by empty/minimal responses
            
        # Filter out error results first
        valid_results = []
        for result in tool_results:
            # Skip error responses
            if isinstance(result, dict) and 'error' in result:
                continue
            valid_results.append(result)
        
        # If no valid results, return None to continue
        if not valid_results:
            return None
        
        # Generate a natural summary based on the tool results
        if len(valid_results) == 1:
            # Single tool result - create natural response
            result = valid_results[0]
            # For simple numeric results, create a more natural response
            if isinstance(result, (int, float)):
                return f"The result is {result}."
            return str(result)
        else:
            # Multiple tool results - create coherent summary
            summary_parts = []
            
            for result in valid_results:
                result_str = str(result)
                # Clean up the result string
                result_str = result_str.strip()
                
                # If result is just a number, keep it simple
                if isinstance(result, (int, float)):
                    # Don't add extra context, let the LLM's response provide that
                    pass
                # Ensure string results end with proper punctuation
                elif result_str and not result_str[-1] in '.!?':
                    result_str += '.'
                    
                summary_parts.append(result_str)
            
            # Join the parts naturally
            return " ".join(summary_parts)

    def _format_ollama_tool_result_message(self, function_name: str, tool_result: Any) -> Dict[str, str]:
        """
        Format tool result message for Ollama provider.
        Simplified approach without hardcoded regex extraction.
        """
        tool_result_str = str(tool_result)
        return {
            "role": "user",
            "content": f"The {function_name} function returned: {tool_result_str}"
        }

    def _process_stream_delta(self, delta, response_text: str, tool_calls: List[Dict], formatted_tools: Optional[List] = None) -> tuple:
        """
        Process a streaming delta chunk to extract content and tool calls.
        
        Args:
            delta: The delta object from a streaming chunk
            response_text: The accumulated response text so far
            tool_calls: The accumulated tool calls list so far
            formatted_tools: Optional list of formatted tools for tool call support check
            
        Returns:
            tuple: (updated_response_text, updated_tool_calls)
        """
        # Process content
        if delta.content:
            response_text += delta.content
        
        # Capture tool calls from streaming chunks if provider supports it
        if formatted_tools and self._supports_streaming_tools() and hasattr(delta, 'tool_calls') and delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.index >= len(tool_calls):
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": "", "arguments": ""}
                    })
                if tc.function.name:
                    tool_calls[tc.index]["function"]["name"] = tc.function.name
                if tc.function.arguments:
                    tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
        
        return response_text, tool_calls

    def _parse_tool_call_arguments(self, tool_call: Dict, is_ollama: bool = False) -> tuple:
        """
        Safely parse tool call arguments with proper error handling
        
        Returns:
            tuple: (function_name, arguments, tool_call_id)
        """
        try:
            if is_ollama:
                # Special handling for Ollama provider which may have different structure
                if "function" in tool_call and isinstance(tool_call["function"], dict):
                    function_name = tool_call["function"]["name"]
                    arguments = json.loads(tool_call["function"]["arguments"])
                else:
                    # Try alternative format that Ollama might return
                    function_name = tool_call.get("name", "unknown_function")
                    arguments_str = tool_call.get("arguments", "{}")
                    arguments = json.loads(arguments_str) if arguments_str else {}
                tool_call_id = tool_call.get("id", f"tool_{id(tool_call)}")
            else:
                # Standard format for other providers with error handling
                function_name = tool_call["function"]["name"]
                arguments_str = tool_call["function"]["arguments"]
                arguments = json.loads(arguments_str) if arguments_str else {}
                tool_call_id = tool_call["id"]
                
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logging.error(f"Error parsing tool call arguments: {e}")
            function_name = tool_call.get("name", "unknown_function")
            arguments = {}
            tool_call_id = tool_call.get("id", f"tool_{id(tool_call)}")
            
        return function_name, arguments, tool_call_id

    def _validate_and_filter_ollama_arguments(self, function_name: str, arguments: Dict[str, Any], available_tools: List) -> Dict[str, Any]:
        """
        Validate and filter tool call arguments for Ollama provider.
        
        Ollama sometimes generates tool calls with mixed parameters where arguments
        from different functions are combined. This method validates arguments against
        the actual function signature and removes invalid parameters.
        
        Args:
            function_name: Name of the function to call
            arguments: Arguments provided in the tool call
            available_tools: List of available tool functions
            
        Returns:
            Filtered arguments dictionary with only valid parameters
        """
        if not available_tools:
            logging.debug(f"[OLLAMA_FIX] No available tools provided for validation")
            return arguments
            
        # Find the target function
        target_function = None
        for tool in available_tools:
            tool_name = getattr(tool, '__name__', str(tool))
            if tool_name == function_name:
                target_function = tool
                break
                
        if not target_function:
            logging.debug(f"[OLLAMA_FIX] Function {function_name} not found in available tools")
            return arguments
            
        try:
            # Get function signature
            sig = inspect.signature(target_function)
            valid_params = set(sig.parameters.keys())
            
            # Filter arguments to only include valid parameters
            filtered_args = {}
            invalid_params = []
            
            for param_name, param_value in arguments.items():
                if param_name in valid_params:
                    # Cast parameter value to the expected type
                    param = sig.parameters[param_name]
                    if param.annotation != inspect.Parameter.empty:
                        try:
                            if param.annotation == int and isinstance(param_value, str):
                                filtered_args[param_name] = int(param_value)
                            elif param.annotation == float and isinstance(param_value, str):
                                filtered_args[param_name] = float(param_value)
                            elif param.annotation == bool and isinstance(param_value, str):
                                filtered_args[param_name] = param_value.lower() in ('true', '1', 'yes')
                            else:
                                filtered_args[param_name] = param_value
                        except (ValueError, TypeError):
                            filtered_args[param_name] = param_value
                    else:
                        filtered_args[param_name] = param_value
                else:
                    invalid_params.append(param_name)
                    
            if invalid_params:
                logging.debug(f"[OLLAMA_FIX] Function {function_name} received invalid parameters: {invalid_params}")
                logging.debug(f"[OLLAMA_FIX] Valid parameters for {function_name}: {list(valid_params)}")
                logging.debug(f"[OLLAMA_FIX] Original arguments: {arguments}")
                logging.debug(f"[OLLAMA_FIX] Filtered arguments: {filtered_args}")
                
            return filtered_args
            
        except Exception as e:
            logging.debug(f"[OLLAMA_FIX] Error validating arguments for {function_name}: {e}")
            return arguments

    def _handle_ollama_sequential_logic(self, iteration_count: int, accumulated_tool_results: List[Any], 
                                      response_text: str, messages: List[Dict]) -> tuple:
        """
        Handle Ollama sequential tool execution logic to prevent premature tool summary generation.
        
        This method implements the two-step process:
        1. After reaching threshold with tool results, add explicit final answer prompt
        2. Only generate tool summary if LLM still doesn't respond after explicit prompt
        
        Args:
            iteration_count: Current iteration count
            accumulated_tool_results: List of tool results from all iterations
            response_text: Current LLM response text
            messages: Message history list to potentially modify
            
        Returns:
            tuple: (should_break, final_response_text, iteration_count)
                - should_break: Whether to break the iteration loop
                - final_response_text: Text to use as final response (None if continuing)
                - iteration_count: Updated iteration count
        """
        if not (self._is_ollama_provider() and iteration_count >= self.OLLAMA_SUMMARY_ITERATION_THRESHOLD):
            return False, None, iteration_count
            
        # For Ollama: if we have meaningful tool results, generate summary immediately
        # Don't wait for more iterations as Ollama tends to repeat tool calls
        if accumulated_tool_results and iteration_count >= self.OLLAMA_SUMMARY_ITERATION_THRESHOLD:
            # Generate summary from tool results
            tool_summary = self._generate_ollama_tool_summary(accumulated_tool_results, response_text)
            if tool_summary:
                return True, tool_summary, iteration_count
                
        return False, None, iteration_count

    def _needs_system_message_skip(self) -> bool:
        """Check if this model requires skipping system messages"""
        if not self.model:
            return False
        
        # Only skip for specific legacy o1 models that don't support system messages
        legacy_o1_models = [
            "o1-preview",           # 2024-09-12 version
            "o1-mini",              # 2024-09-12 version  
            "o1-mini-2024-09-12"    # Explicit dated version
        ]
        
        return self.model in legacy_o1_models
    
    def _supports_streaming_tools(self) -> bool:
        """
        Check if the current provider supports streaming with tools.
        
        Most providers that support tool calling also support streaming with tools,
        but some providers (like Ollama and certain local models) require non-streaming
        calls when tools are involved.
        
        Returns:
            bool: True if provider supports streaming with tools, False otherwise
        """
        if not self.model:
            return False
        
        # Ollama doesn't reliably support streaming with tools
        if self._is_ollama_provider():
            return False
        
        # Import the capability check function
        from .model_capabilities import supports_streaming_with_tools
        
        # Check if this model supports streaming with tools
        if supports_streaming_with_tools(self.model):
            return True
        
        # Anthropic Claude models support streaming with tools
        if self.model.startswith("claude-"):
            return True
        
        # Google Gemini models support streaming with tools
        if any(self.model.startswith(prefix) for prefix in ["gemini-", "gemini/"]):
            return True
        
        # Qwen models support streaming with tools
        if self._is_qwen_provider():
            return True
        
        # For other providers, default to False to be safe
        # This ensures we make a single non-streaming call rather than risk
        # missing tool calls or making duplicate calls
        return False
    
    def _build_messages(self, prompt, system_prompt=None, chat_history=None, output_json=None, output_pydantic=None, tools=None):
        """Build messages list for LLM completion. Works for both sync and async.
        
        Args:
            prompt: The user prompt (str or list)
            system_prompt: Optional system prompt
            chat_history: Optional list of previous messages
            output_json: Optional Pydantic model for JSON output
            output_pydantic: Optional Pydantic model for JSON output (alias)
            tools: Optional list of tools available
            
        Returns:
            tuple: (messages list, original prompt)
        """
        messages = []
        
        # Check if this is a Gemini model that supports native structured outputs
        is_gemini_with_structured_output = False
        if output_json or output_pydantic:
            from .model_capabilities import supports_structured_outputs
            is_gemini_with_structured_output = (
                self._is_gemini_model() and
                supports_structured_outputs(self.model)
            )
        
        # Handle system prompt
        if system_prompt:
            # Only append JSON schema for non-Gemini models or Gemini models without structured output support
            if (output_json or output_pydantic) and not is_gemini_with_structured_output:
                schema_model = output_json or output_pydantic
                if schema_model and hasattr(schema_model, 'model_json_schema'):
                    system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(schema_model.model_json_schema())}"
            
            # Skip system messages for legacy o1 models as they don't support them
            if not self._needs_system_message_skip():
                messages.append({"role": "system", "content": system_prompt})
        
        # Add chat history if provided
        if chat_history:
            messages.extend(chat_history)
        
        # Handle prompt modifications for JSON output
        original_prompt = prompt
        if (output_json or output_pydantic) and not is_gemini_with_structured_output:
            # Only modify prompt for non-Gemini models
            if isinstance(prompt, str):
                prompt = prompt + "\nReturn ONLY a valid JSON object. No other text or explanation."
            elif isinstance(prompt, list):
                # Create a copy to avoid modifying the original
                prompt = prompt.copy()
                for item in prompt:
                    if item.get("type") == "text":
                        item["text"] = item["text"] + "\nReturn ONLY a valid JSON object. No other text or explanation."
                        break
        
        # Add prompt to messages
        if isinstance(prompt, list):
            messages.append({"role": "user", "content": prompt})
        else:
            messages.append({"role": "user", "content": prompt})
        
        return messages, original_prompt

    def _fix_array_schemas(self, schema: Dict) -> Dict:
        """
        Recursively fix array schemas by adding missing 'items' attribute.
        
        This ensures compatibility with OpenAI's function calling format which
        requires array types to specify the type of items they contain.
        
        Args:
            schema: The schema dictionary to fix
            
        Returns:
            dict: The fixed schema
        """
        if not isinstance(schema, dict):
            return schema
            
        # Create a copy to avoid modifying the original
        fixed_schema = schema.copy()
        
        # Fix array types at the current level
        if fixed_schema.get("type") == "array" and "items" not in fixed_schema:
            # Add a default items schema for arrays without it
            fixed_schema["items"] = {"type": "string"}
            
        # Recursively fix nested schemas in properties
        if "properties" in fixed_schema and isinstance(fixed_schema["properties"], dict):
            fixed_properties = {}
            for prop_name, prop_schema in fixed_schema["properties"].items():
                if isinstance(prop_schema, dict):
                    fixed_properties[prop_name] = self._fix_array_schemas(prop_schema)
                else:
                    fixed_properties[prop_name] = prop_schema
            fixed_schema["properties"] = fixed_properties
            
        # Fix items schema if it exists
        if "items" in fixed_schema and isinstance(fixed_schema["items"], dict):
            fixed_schema["items"] = self._fix_array_schemas(fixed_schema["items"])
            
        return fixed_schema

    def _get_tools_cache_key(self, tools):
        """Generate a cache key for tools list."""
        if tools is None:
            return "none"
        if not tools:
            return "empty"
        # Create a simple hash based on tool names/content
        tool_parts = []
        for tool in tools:
            if isinstance(tool, dict) and 'type' in tool and tool['type'] == 'function':
                if 'function' in tool and isinstance(tool['function'], dict) and 'name' in tool['function']:
                    tool_parts.append(f"openai:{tool['function']['name']}")
            elif callable(tool) and hasattr(tool, '__name__'):
                tool_parts.append(f"callable:{tool.__name__}")
            elif isinstance(tool, str):
                tool_parts.append(f"string:{tool}")
            elif isinstance(tool, dict) and len(tool) == 1:
                tool_name = next(iter(tool.keys()))
                tool_parts.append(f"gemini:{tool_name}")
            else:
                tool_parts.append(f"other:{id(tool)}")
        return "|".join(sorted(tool_parts))

    def _format_tools_for_litellm(self, tools: Optional[List[Any]]) -> Optional[List[Dict]]:
        """Format tools for LiteLLM - handles all tool formats.
        
        Supports:
        - Pre-formatted OpenAI tools (dicts with type='function')
        - Lists of pre-formatted tools
        - Callable functions
        - String function names
        - Gemini internal tools ({"googleSearch": {}}, {"urlContext": {}}, {"codeExecution": {}})
        
        Args:
            tools: List of tools in various formats
            
        Returns:
            List of formatted tools or None
        """
        if not tools:
            return None
        
        # Check cache first
        tools_key = self._get_tools_cache_key(tools)
        if tools_key in self._formatted_tools_cache:
            return self._formatted_tools_cache[tools_key]
            
        formatted_tools = []
        for tool in tools:
            # Check if the tool is already in OpenAI format (e.g. from MCP.to_openai_tool())
            if isinstance(tool, dict) and 'type' in tool and tool['type'] == 'function':
                # Validate nested dictionary structure before accessing
                if 'function' in tool and isinstance(tool['function'], dict) and 'name' in tool['function']:
                    logging.debug(f"Using pre-formatted OpenAI tool: {tool['function']['name']}")
                    # Fix array schemas in the tool parameters
                    fixed_tool = tool.copy()
                    if 'parameters' in fixed_tool['function']:
                        fixed_tool['function']['parameters'] = self._fix_array_schemas(fixed_tool['function']['parameters'])
                    formatted_tools.append(fixed_tool)
                else:
                    logging.debug(f"Skipping malformed OpenAI tool: missing function or name")
            # Handle lists of tools (e.g. from MCP.to_openai_tool())
            elif isinstance(tool, list):
                for subtool in tool:
                    if isinstance(subtool, dict) and 'type' in subtool and subtool['type'] == 'function':
                        # Validate nested dictionary structure before accessing
                        if 'function' in subtool and isinstance(subtool['function'], dict) and 'name' in subtool['function']:
                            logging.debug(f"Using pre-formatted OpenAI tool from list: {subtool['function']['name']}")
                            # Fix array schemas in the tool parameters
                            fixed_tool = subtool.copy()
                            if 'parameters' in fixed_tool['function']:
                                fixed_tool['function']['parameters'] = self._fix_array_schemas(fixed_tool['function']['parameters'])
                            formatted_tools.append(fixed_tool)
                        else:
                            logging.debug(f"Skipping malformed OpenAI tool in list: missing function or name")
            elif callable(tool):
                tool_def = self._generate_tool_definition(tool)
                if tool_def:
                    formatted_tools.append(tool_def)
            elif isinstance(tool, str):
                tool_def = self._generate_tool_definition(tool)
                if tool_def:
                    formatted_tools.append(tool_def)
            # Handle Gemini internal tools (e.g., {"googleSearch": {}}, {"urlContext": {}}, {"codeExecution": {}})
            elif isinstance(tool, dict) and len(tool) == 1:
                tool_name = next(iter(tool.keys()))
                gemini_internal_tools = {'googleSearch', 'urlContext', 'codeExecution'}
                if tool_name in gemini_internal_tools:
                    logging.debug(f"Using Gemini internal tool: {tool_name}")
                    formatted_tools.append(tool)
                else:
                    logging.debug(f"Skipping unknown tool: {tool_name}")
            else:
                logging.debug(f"Skipping tool of unsupported type: {type(tool)}")
                
        # Validate JSON serialization before returning
        if formatted_tools:
            try:
                import json
                json.dumps(formatted_tools)  # Validate serialization
            except (TypeError, ValueError) as e:
                logging.error(f"Tools are not JSON serializable: {e}")
                return None
        
        # Cache the formatted tools
        result = formatted_tools if formatted_tools else None
        if len(self._formatted_tools_cache) < self._max_cache_size:
            self._formatted_tools_cache[tools_key] = result
        return result

    def get_response(
        self,
        prompt: Union[str, List[Dict]],
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict]] = None,
        temperature: float = 0.2,
        tools: Optional[List[Any]] = None,
        output_json: Optional[BaseModel] = None,
        output_pydantic: Optional[BaseModel] = None,
        verbose: bool = True,
        markdown: bool = True,
        self_reflect: bool = False,
        max_reflect: int = 3,
        min_reflect: int = 1,
        console: Optional[Console] = None,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        agent_tools: Optional[List[str]] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        execute_tool_fn: Optional[Callable] = None,
        stream: bool = True,
        **kwargs
    ) -> str:
        """Enhanced get_response with all OpenAI-like features"""
        logging.info(f"Getting response from {self.model}")
        # Log all self values when in debug mode
        self._log_llm_config(
            'LLM instance',
            model=self.model,
            timeout=self.timeout,
            temperature=self.temperature,
            top_p=self.top_p,
            n=self.n,
            max_tokens=self.max_tokens,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
            logit_bias=self.logit_bias,
            response_format=self.response_format,
            seed=self.seed,
            logprobs=self.logprobs,
            top_logprobs=self.top_logprobs,
            api_version=self.api_version,
            stop_phrases=self.stop_phrases,
            api_key=self.api_key,
            base_url=self.base_url,
            verbose=self.verbose,
            markdown=self.markdown,
            self_reflect=self.self_reflect,
            max_reflect=self.max_reflect,
            min_reflect=self.min_reflect,
            reasoning_steps=self.reasoning_steps
        )
        
        # Log the parameter values passed to get_response
        self._log_llm_config(
            'get_response parameters',
            prompt=prompt,
            system_prompt=system_prompt,
            chat_history=chat_history,
            temperature=temperature,
            tools=tools,
            output_json=output_json,
            output_pydantic=output_pydantic,
            verbose=verbose,
            markdown=markdown,
            self_reflect=self_reflect,
            max_reflect=max_reflect,
            min_reflect=min_reflect,
            agent_name=agent_name,
            agent_role=agent_role,
            agent_tools=agent_tools,
            kwargs=str(kwargs)
        )
        try:
            import litellm
            # This below **kwargs** is passed to .completion() directly. so reasoning_steps has to be popped. OR find alternate best way of handling this.
            reasoning_steps = kwargs.pop('reasoning_steps', self.reasoning_steps) 
            # Disable litellm debug messages
            litellm.set_verbose = False
            
            # Format tools if provided
            formatted_tools = self._format_tools_for_litellm(tools)
            
            # Build messages list using shared helper
            messages, original_prompt = self._build_messages(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                output_json=output_json,
                output_pydantic=output_pydantic
            )

            start_time = time.time()
            reflection_count = 0
            callback_executed = False  # Track if callback has been executed for this interaction
            interaction_displayed = False  # Track if interaction has been displayed

            # Display initial instruction once
            if verbose:
                display_text = prompt
                if isinstance(prompt, list):
                    display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                
                if display_text and str(display_text).strip():
                    display_instruction(
                        f"Agent {agent_name} is processing prompt: {display_text}",
                        console=self.console,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools
                    )

            # Sequential tool calling loop - similar to agent.py
            max_iterations = 10  # Prevent infinite loops
            iteration_count = 0
            final_response_text = ""
            stored_reasoning_content = None  # Store reasoning content from tool execution
            accumulated_tool_results = []  # Store all tool results across iterations

            while iteration_count < max_iterations:
                try:
                    # Get response from LiteLLM
                    current_time = time.time()

                    # If reasoning_steps is True, do a single non-streaming call
                    if reasoning_steps:
                        resp = litellm.completion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=False,  # force non-streaming
                                tools=formatted_tools,
                                output_json=output_json,
                                output_pydantic=output_pydantic,
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                            )
                        )
                        reasoning_content = resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                        response_text = resp["choices"][0]["message"]["content"]
                        final_response = resp
                        
                        # Track token usage
                        if self.metrics:
                            self._track_token_usage(final_response, self.model)
                        
                        # Execute callbacks and display based on verbose setting
                        generation_time_val = time.time() - current_time
                        response_content = f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}" if reasoning_content else response_text
                        
                        # Optionally display reasoning if present
                        if verbose and reasoning_content and not interaction_displayed:
                            display_interaction(
                                original_prompt,
                                f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}",
                                markdown=markdown,
                                generation_time=generation_time_val,
                                console=self.console,
                                agent_name=agent_name,
                                agent_role=agent_role,
                                agent_tools=agent_tools,
                                task_name=task_name,
                                task_description=task_description,
                                task_id=task_id
                            )
                            interaction_displayed = True
                            callback_executed = True
                        elif verbose and not interaction_displayed:
                            display_interaction(
                                original_prompt,
                                response_text,
                                markdown=markdown,
                                generation_time=generation_time_val,
                                console=self.console,
                                agent_name=agent_name,
                                agent_role=agent_role,
                                agent_tools=agent_tools,
                                task_name=task_name,
                                task_description=task_description,
                                task_id=task_id
                            )
                            interaction_displayed = True
                            callback_executed = True
                        elif not callback_executed:
                            # Only execute callback if display_interaction hasn't been called (which would trigger callbacks internally)
                            execute_sync_callback(
                                'interaction',
                                message=original_prompt,
                                response=response_content,
                                markdown=markdown,
                                generation_time=generation_time_val,
                                agent_name=agent_name,
                                agent_role=agent_role,
                                agent_tools=agent_tools,
                                task_name=task_name,
                                task_description=task_description,
                                task_id=task_id
                            )
                            callback_executed = True
                    
                    # Otherwise do the existing streaming approach
                    else:
                        # Determine if we should use streaming based on tool support
                        use_streaming = stream
                        if formatted_tools and not self._supports_streaming_tools():
                            # Provider doesn't support streaming with tools, use non-streaming
                            use_streaming = False
                        
                        # Gemini has issues with streaming + tools, disable streaming for Gemini when tools are present
                        if use_streaming and formatted_tools and self._is_gemini_model():
                            logging.debug("Disabling streaming for Gemini model with tools due to JSON parsing issues")
                            use_streaming = False
                        
                        # Track whether fallback was successful to avoid duplicate API calls
                        fallback_completed = False
                        
                        if use_streaming:
                            # Streaming approach (with or without tools)
                            tool_calls = []
                            response_text = ""
                            streaming_success = False
                            
                            # Wrap streaming with error handling for LiteLLM JSON parsing errors
                            try:
                                if verbose:
                                    # Verbose streaming: show display_generating during streaming
                                    with Live(display_generating("", current_time), console=self.console, refresh_per_second=4) as live:
                                        for chunk in litellm.completion(
                                            **self._build_completion_params(
                                                messages=messages,
                                                tools=formatted_tools,
                                                temperature=temperature,
                                                stream=True,
                                                output_json=output_json,
                                                output_pydantic=output_pydantic,
                                                **kwargs
                                            )
                                        ):
                                            if chunk and chunk.choices and chunk.choices[0].delta:
                                                delta = chunk.choices[0].delta
                                                response_text, tool_calls = self._process_stream_delta(
                                                    delta, response_text, tool_calls, formatted_tools
                                                )
                                                live.update(display_generating(response_text, current_time))
                                else:
                                    # Non-verbose streaming: no display_generating during streaming
                                    for chunk in litellm.completion(
                                        **self._build_completion_params(
                                            messages=messages,
                                            tools=formatted_tools,
                                            temperature=temperature,
                                            stream=True,
                                            output_json=output_json,
                                            output_pydantic=output_pydantic,
                                            **kwargs
                                        )
                                    ):
                                        if chunk and chunk.choices and chunk.choices[0].delta:
                                            delta = chunk.choices[0].delta
                                            response_text, tool_calls = self._process_stream_delta(
                                                delta, response_text, tool_calls, formatted_tools
                                            )
                                streaming_success = True
                            except Exception as streaming_error:
                                # Handle streaming errors with recovery logic
                                if self._is_streaming_error_recoverable(streaming_error):
                                    if verbose:
                                        logging.warning(f"Streaming error (recoverable): {streaming_error}")
                                        logging.warning("Falling back to non-streaming mode")
                                    # Immediately perform non-streaming fallback with actual API call
                                    try:
                                        if verbose:
                                            # When verbose=True, always use streaming for better UX
                                            with Live(display_generating("", current_time), console=self.console, refresh_per_second=4, transient=True) as live:
                                                response_text = ""
                                                tool_calls = []
                                                # Use streaming when verbose for progressive display
                                                for chunk in litellm.completion(
                                                    **self._build_completion_params(
                                                        messages=messages,
                                                        tools=formatted_tools,
                                                        temperature=temperature,
                                                        stream=True,  # Always stream when verbose=True
                                                        output_json=output_json,
                                                        output_pydantic=output_pydantic,
                                                        **kwargs
                                                    )
                                                ):
                                                    if chunk and chunk.choices and chunk.choices[0].delta:
                                                        delta = chunk.choices[0].delta
                                                        response_text, tool_calls = self._process_stream_delta(
                                                            delta, response_text, tool_calls, formatted_tools
                                                        )
                                                        live.update(display_generating(response_text, current_time))
                                            
                                            # Clear the live display after completion
                                            self.console.print()
                                            
                                            # Create final response structure
                                            final_response = {
                                                "choices": [{
                                                    "message": {
                                                        "content": response_text,
                                                        "tool_calls": tool_calls if tool_calls else None
                                                    }
                                                }]
                                            }
                                        else:
                                            # For non-streaming + non-verbose: no display_generating (per user requirements)
                                            final_response = litellm.completion(
                                                **self._build_completion_params(
                                                    messages=messages,
                                                    tools=formatted_tools,
                                                    temperature=temperature,
                                                    stream=False,
                                                    output_json=output_json,
                                                    output_pydantic=output_pydantic,
                                                    **kwargs
                                                )
                                            )
                                            # Handle None content from Gemini
                                            response_content = final_response["choices"][0]["message"].get("content")
                                            response_text = response_content if response_content is not None else ""
                                            
                                            # Track token usage
                                            if self.metrics:
                                                self._track_token_usage(final_response, self.model)
                                        
                                        # Execute callbacks and display based on verbose setting
                                        if verbose and not interaction_displayed:
                                            # Display the complete response at once (this will trigger callbacks internally)
                                            display_interaction(
                                                original_prompt,
                                                response_text,
                                                markdown=markdown,
                                                generation_time=time.time() - current_time,
                                                console=self.console,
                                                agent_name=agent_name,
                                                agent_role=agent_role,
                                                agent_tools=agent_tools,
                                                task_name=task_name,
                                                task_description=task_description,
                                                task_id=task_id
                                            )
                                            interaction_displayed = True
                                            callback_executed = True
                                        elif not callback_executed:
                                            # Only execute callback if display_interaction hasn't been called
                                            execute_sync_callback(
                                                'interaction',
                                                message=original_prompt,
                                                response=response_text,
                                                markdown=markdown,
                                                generation_time=time.time() - current_time,
                                                agent_name=agent_name,
                                                agent_role=agent_role,
                                                agent_tools=agent_tools,
                                                task_name=task_name,
                                                task_description=task_description,
                                                task_id=task_id
                                            )
                                            callback_executed = True
                                        
                                        # Mark that fallback completed successfully
                                        fallback_completed = True
                                        streaming_success = False
                                        
                                    except Exception as fallback_error:
                                        # If non-streaming also fails, create a graceful fallback with partial streaming data
                                        logging.warning(f"Non-streaming fallback also failed: {fallback_error}")
                                        logging.warning("Using partial streaming response data")
                                        response_text = response_text or ""
                                        # Create a mock response with whatever partial data we have
                                        final_response = {
                                            "choices": [{
                                                "message": {
                                                    "content": response_text,
                                                    "tool_calls": tool_calls if tool_calls else None
                                                }
                                            }]
                                        }
                                        fallback_completed = True
                                        streaming_success = False
                                else:
                                    # For non-recoverable errors, re-raise immediately
                                    logging.error(f"Non-recoverable streaming error: {streaming_error}")
                                    raise streaming_error
                            
                            if streaming_success:
                                response_text = response_text.strip() if response_text else ""
                                
                                # Execute callbacks after streaming completes (only if not verbose, since verbose will call display_interaction later)
                                if not verbose and not callback_executed:
                                    execute_sync_callback(
                                        'interaction',
                                        message=original_prompt,
                                        response=response_text,
                                        markdown=markdown,
                                        generation_time=time.time() - current_time,
                                        agent_name=agent_name,
                                        agent_role=agent_role,
                                        agent_tools=agent_tools,
                                        task_name=task_name,
                                        task_description=task_description,
                                        task_id=task_id
                                    )
                                    callback_executed = True

                                # Create a mock final_response with the captured data
                                final_response = {
                                    "choices": [{
                                        "message": {
                                            "content": response_text,
                                            "tool_calls": tool_calls if tool_calls else None
                                        }
                                    }]
                                }
                        
                        # Only execute non-streaming if we haven't used streaming AND fallback hasn't completed
                        if not use_streaming and not fallback_completed:
                            # Non-streaming approach (when tools require it, streaming is disabled, or streaming fallback)
                            if verbose:
                                # When verbose=True, always use streaming for better UX
                                with Live(display_generating("", current_time), console=self.console, refresh_per_second=4, transient=True) as live:
                                    response_text = ""
                                    tool_calls = []
                                    # Use streaming when verbose for progressive display
                                    for chunk in litellm.completion(
                                        **self._build_completion_params(
                                            messages=messages,
                                            tools=formatted_tools,
                                            temperature=temperature,
                                            stream=True,  # Always stream when verbose=True
                                            output_json=output_json,
                                            output_pydantic=output_pydantic,
                                            **kwargs
                                        )
                                    ):
                                        if chunk and chunk.choices and chunk.choices[0].delta:
                                            delta = chunk.choices[0].delta
                                            response_text, tool_calls = self._process_stream_delta(
                                                delta, response_text, tool_calls, formatted_tools
                                            )
                                            live.update(display_generating(response_text, current_time))
                                
                                # Clear the live display after completion
                                self.console.print()
                                
                                # Create final response structure
                                final_response = {
                                    "choices": [{
                                        "message": {
                                            "content": response_text,
                                            "tool_calls": tool_calls if tool_calls else None
                                        }
                                    }]
                                }
                            else:
                                # For non-streaming + non-verbose: no display_generating (per user requirements)
                                final_response = litellm.completion(
                                    **self._build_completion_params(
                                        messages=messages,
                                        tools=formatted_tools,
                                        temperature=temperature,
                                        stream=False,
                                        output_json=output_json,
                                        output_pydantic=output_pydantic,
                                        **kwargs
                                    )
                                )
                                # Handle None content from Gemini
                                response_content = final_response["choices"][0]["message"].get("content")
                                response_text = response_content if response_content is not None else ""
                                
                                # Track token usage
                                if self.metrics:
                                    self._track_token_usage(final_response, self.model)
                            
                            # Execute callbacks and display based on verbose setting
                            if verbose and not interaction_displayed:
                                # Display the complete response at once (this will trigger callbacks internally)
                                display_interaction(
                                    original_prompt,
                                    response_text,
                                    markdown=markdown,
                                    generation_time=time.time() - current_time,
                                    console=self.console,
                                    agent_name=agent_name,
                                    agent_role=agent_role,
                                    agent_tools=agent_tools,
                                    task_name=task_name,
                                    task_description=task_description,
                                    task_id=task_id
                                )
                                interaction_displayed = True
                                callback_executed = True
                            elif not callback_executed:
                                # Only execute callback if display_interaction hasn't been called
                                execute_sync_callback(
                                    'interaction',
                                    message=original_prompt,
                                    response=response_text,
                                    markdown=markdown,
                                    generation_time=time.time() - current_time,
                                    agent_name=agent_name,
                                    agent_role=agent_role,
                                    agent_tools=agent_tools,
                                    task_name=task_name,
                                    task_description=task_description,
                                    task_id=task_id
                                )
                                callback_executed = True
                    
                    tool_calls = final_response["choices"][0]["message"].get("tool_calls")
                    
                    
                    # For Ollama, parse tool calls from response text if not in tool_calls field
                    if self._is_ollama_provider() and not tool_calls and response_text and formatted_tools:
                        # Try to parse JSON tool call from response text
                        try:
                            response_json = json.loads(response_text.strip())
                            if isinstance(response_json, dict) and "name" in response_json:
                                # Convert Ollama format to standard tool_calls format
                                tool_calls = [{
                                    "id": f"tool_{iteration_count}",
                                    "type": "function",
                                    "function": {
                                        "name": response_json["name"],
                                        "arguments": json.dumps(response_json.get("arguments", {}))
                                    }
                                }]
                                logging.debug(f"Parsed Ollama tool call from response: {tool_calls}")
                            elif isinstance(response_json, list):
                                # Handle multiple tool calls
                                tool_calls = []
                                for idx, tool_json in enumerate(response_json):
                                    if isinstance(tool_json, dict) and "name" in tool_json:
                                        tool_calls.append({
                                            "id": f"tool_{iteration_count}_{idx}",
                                            "type": "function",
                                            "function": {
                                                "name": tool_json["name"],
                                                "arguments": json.dumps(tool_json.get("arguments", {}))
                                            }
                                        })
                                if tool_calls:
                                    logging.debug(f"Parsed multiple Ollama tool calls from response: {tool_calls}")
                        except (json.JSONDecodeError, KeyError) as e:
                            logging.debug(f"Could not parse Ollama tool call from response: {e}")
                    
                    # For Qwen, parse tool calls from XML format in response text
                    if self._is_qwen_provider() and not tool_calls and response_text and formatted_tools:
                        # Look for <tool_call> XML tags
                        tool_call_pattern = r'<tool_call>\s*({.*?})\s*</tool_call>'
                        matches = re.findall(tool_call_pattern, response_text, re.DOTALL)
                        
                        if matches:
                            tool_calls = []
                            for idx, match in enumerate(matches):
                                try:
                                    # Parse the JSON inside the XML tag
                                    tool_json = json.loads(match.strip())
                                    if isinstance(tool_json, dict) and "name" in tool_json:
                                        tool_calls.append({
                                            "id": f"tool_{iteration_count}_{idx}",
                                            "type": "function",
                                            "function": {
                                                "name": tool_json["name"],
                                                "arguments": json.dumps(tool_json.get("arguments", {}))
                                            }
                                        })
                                except (json.JSONDecodeError, KeyError) as e:
                                    logging.debug(f"Could not parse Qwen tool call from XML: {e}")
                                    continue
                            
                            if tool_calls:
                                logging.debug(f"Parsed Qwen tool calls from XML response: {tool_calls}")
                    
                    # For Ollama, if response is empty but we have tools, prompt for tool usage
                    if self._is_ollama_provider() and (not response_text or response_text.strip() == "") and formatted_tools and iteration_count == 0:
                        messages.append({
                            "role": "user",
                            "content": self.OLLAMA_TOOL_USAGE_PROMPT
                        })
                        iteration_count += 1
                        continue
                    
                    # Handle tool calls - Sequential tool calling logic
                    if tool_calls and execute_tool_fn:
                        # Convert tool_calls to a serializable format for all providers
                        serializable_tool_calls = self._serialize_tool_calls(tool_calls)
                        # Check if this is Ollama provider
                        if self._is_ollama_provider():
                            # For Ollama, only include role and content
                            messages.append({
                                "role": "assistant",
                                "content": response_text
                            })
                        else:
                            # For other providers, include tool_calls
                            messages.append({
                                "role": "assistant",
                                "content": response_text,
                                "tool_calls": serializable_tool_calls
                            })
                        
                        should_continue = False
                        tool_results = []  # Store current iteration tool results
                        tool_result_mapping = {}  # Store function results by name for Ollama chaining
                        
                        for tool_call in tool_calls:
                            # Handle both object and dict access patterns
                            is_ollama = self._is_ollama_provider()
                            function_name, arguments, tool_call_id = self._extract_tool_call_info(tool_call, is_ollama)

                            # Validate and filter arguments for Ollama provider
                            if is_ollama and tools:
                                # First check if any argument references a previous tool result
                                if is_ollama and tool_result_mapping:
                                    # Replace function names with their results in arguments
                                    for arg_name, arg_value in list(arguments.items()):
                                        if isinstance(arg_value, str) and arg_value in tool_result_mapping:
                                            # Replace function name with its result
                                            arguments[arg_name] = tool_result_mapping[arg_value]
                                            logging.debug(f"[OLLAMA_FIX] Replaced {arg_value} with {tool_result_mapping[arg_value]} in {function_name} arguments")
                                
                                arguments = self._validate_and_filter_ollama_arguments(function_name, arguments, tools)

                            logging.debug(f"[TOOL_EXEC_DEBUG] About to execute tool {function_name} with args: {arguments}")
                            tool_result = execute_tool_fn(function_name, arguments)
                            logging.debug(f"[TOOL_EXEC_DEBUG] Tool execution result: {tool_result}")
                            tool_results.append(tool_result)  # Store the result
                            accumulated_tool_results.append(tool_result)  # Accumulate across iterations
                            
                            # For Ollama, store the result for potential chaining
                            if is_ollama:
                                # Extract numeric value from result if it contains one
                                if isinstance(tool_result, (int, float)):
                                    tool_result_mapping[function_name] = tool_result
                                elif isinstance(tool_result, str):
                                    import re
                                    match = re.search(r'\b(\d+)\b', tool_result)
                                    if match:
                                        tool_result_mapping[function_name] = int(match.group(1))
                                    else:
                                        tool_result_mapping[function_name] = tool_result

                            if verbose:
                                display_message = f"Agent {agent_name} called function '{function_name}' with arguments: {arguments}\n"
                                if tool_result:
                                    display_message += f"Function returned: {tool_result}"
                                    logging.debug(f"[TOOL_EXEC_DEBUG] Display message with result: {display_message}")
                                else:
                                    display_message += "Function returned no output"
                                    logging.debug("[TOOL_EXEC_DEBUG] Tool returned no output")
                                
                                logging.debug(f"[TOOL_EXEC_DEBUG] About to display tool call with message: {display_message}")
                                display_tool_call(display_message, console=self.console)
                                
                            # Check if this is Ollama provider
                            if self._is_ollama_provider():
                                # For Ollama, use user role and format as natural language
                                messages.append(self._format_ollama_tool_result_message(function_name, tool_result))
                            else:
                                # For other providers, use tool role with tool_call_id
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": json.dumps(tool_result) if tool_result is not None else "Function returned an empty output"
                                })

                            # Check if we should continue (for tools like sequential thinking)
                            # This mimics the logic from agent.py lines 1004-1007
                            if function_name == "sequentialthinking" and arguments.get("nextThoughtNeeded", False):
                                should_continue = True
                        
                        # If we should continue, increment iteration and continue loop
                        if should_continue:
                            iteration_count += 1
                            continue

                        # For most providers (including Gemini), we need to continue the loop
                        # to get a final response that incorporates the tool results
                        # Only break if the response explicitly indicates completion
                        if response_text and len(response_text.strip()) > 50 and "final answer" in response_text.lower():
                            # LLM provided an explicit final answer, don't continue
                            final_response_text = response_text.strip()
                            break
                        
                        
                        # Special handling for Ollama to prevent infinite loops
                        # Only generate summary after multiple iterations to allow sequential execution
                        should_break, tool_summary_text, iteration_count = self._handle_ollama_sequential_logic(
                            iteration_count, accumulated_tool_results, response_text, messages
                        )
                        if should_break:
                            final_response_text = tool_summary_text
                            # Reset interaction_displayed to ensure final summary is shown
                            interaction_displayed = False
                            break
                        elif tool_summary_text is None and iteration_count > self.OLLAMA_SUMMARY_ITERATION_THRESHOLD:
                            # Continue iteration after adding final answer prompt
                            continue
                        
                        # Safety check: prevent infinite loops for any provider
                        if iteration_count >= 5:
                            if tool_results:
                                final_response_text = "Task completed successfully based on tool execution results."
                            else:
                                final_response_text = response_text.strip() if response_text else "Task completed."
                            break
                        
                        # Otherwise, continue the loop to get final response with tool results
                        iteration_count += 1
                        # Clear response_text so we don't accidentally use the initial response
                        response_text = ""
                        continue
                    else:
                        # No tool calls, we're done with this iteration
                        
                        # Special early stopping logic for Ollama when tool results are available
                        # Ollama often provides empty responses after successful tool execution
                        if (self._is_ollama_provider() and accumulated_tool_results and iteration_count >= 1 and 
                            (not response_text or response_text.strip() == "")):
                            # Generate coherent response from tool results
                            tool_summary = self._generate_ollama_tool_summary(accumulated_tool_results, response_text)
                            if tool_summary:
                                final_response_text = tool_summary
                                # Reset interaction_displayed to ensure final summary is shown
                                interaction_displayed = False
                                break
                        
                        # If we've executed tools in previous iterations, this response contains the final answer
                        if iteration_count > 0:
                            final_response_text = response_text.strip() if response_text else ""
                            break
                        
                        # First iteration with no tool calls - just return the response
                        final_response_text = response_text.strip() if response_text else ""
                        break
                        
                except Exception as e:
                    logging.error(f"Error in LLM iteration {iteration_count}: {e}")
                    break
                    
            # End of while loop - return final response
            if final_response_text:
                # Display the final response if verbose mode is enabled
                if verbose and not interaction_displayed:
                    generation_time_val = time.time() - start_time
                    display_interaction(
                        original_prompt,
                        final_response_text,
                        markdown=markdown,
                        generation_time=generation_time_val,
                        console=self.console,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
                    interaction_displayed = True
                    callback_executed = True
                elif not callback_executed:
                    # Execute callback if not already done
                    execute_sync_callback(
                        'interaction',
                        message=original_prompt,
                        response=final_response_text,
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
                    callback_executed = True
                return final_response_text
            
            # No tool calls were made in this iteration, return the response
            generation_time_val = time.time() - start_time
            response_content = f"Reasoning:\n{stored_reasoning_content}\n\nAnswer:\n{response_text}" if stored_reasoning_content else response_text
            
            if verbose and not interaction_displayed:
                # If we have stored reasoning content from tool execution, display it
                if stored_reasoning_content:
                    display_interaction(
                        original_prompt,
                        f"Reasoning:\n{stored_reasoning_content}\n\nAnswer:\n{response_text}",
                        markdown=markdown,
                        generation_time=generation_time_val,
                        console=self.console,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
                else:
                    display_interaction(
                        original_prompt,
                        response_text,
                        markdown=markdown,
                        generation_time=generation_time_val,
                        console=self.console,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
                interaction_displayed = True
                callback_executed = True
            elif not callback_executed:
                # Only execute callback if display_interaction hasn't been called
                execute_sync_callback(
                    'interaction',
                    message=original_prompt,
                    response=response_content,
                    markdown=markdown,
                    generation_time=generation_time_val,
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_tools=agent_tools,
                    task_name=task_name,
                    task_description=task_description,
                    task_id=task_id
                )
                callback_executed = True
            
            response_text = response_text.strip() if response_text else ""
            
            # Return reasoning content if reasoning_steps is True and we have it
            if reasoning_steps and stored_reasoning_content:
                return stored_reasoning_content
            
            # Handle output formatting
            if output_json or output_pydantic:
                self.chat_history.append({"role": "user", "content": original_prompt})
                self.chat_history.append({"role": "assistant", "content": response_text})
                
                if verbose and not interaction_displayed:
                    display_interaction(original_prompt, response_text, markdown=markdown,
                                     generation_time=time.time() - start_time, console=self.console,
                                     agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                     task_name=task_name, task_description=task_description, task_id=task_id)
                    interaction_displayed = True
                    callback_executed = True
                elif not callback_executed:
                    # Only execute callback if display_interaction hasn't been called
                    execute_sync_callback(
                        'interaction',
                        message=original_prompt,
                        response=response_text,
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
                    callback_executed = True
                return response_text

            if not self_reflect:
                if verbose and not interaction_displayed:
                    display_interaction(original_prompt, response_text, markdown=markdown,
                                     generation_time=time.time() - start_time, console=self.console,
                                     agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                     task_name=task_name, task_description=task_description, task_id=task_id)
                    interaction_displayed = True
                    callback_executed = True
                elif not callback_executed:
                    # Only execute callback if display_interaction hasn't been called
                    execute_sync_callback(
                        'interaction',
                        message=original_prompt,
                        response=response_text,
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
                    callback_executed = True
                
                # Return reasoning content if reasoning_steps is True
                if reasoning_steps and stored_reasoning_content:
                    return stored_reasoning_content
                return response_text

            # Handle self-reflection loop
            while reflection_count < max_reflect:
                # Handle self-reflection
                reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
Identify any flaws, improvements, or actions.
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
                """
                
                reflection_messages = messages + [
                    {"role": "assistant", "content": response_text},
                    {"role": "user", "content": reflection_prompt}
                ]

                # If reasoning_steps is True, do a single non-streaming call to capture reasoning
                if reasoning_steps:
                    reflection_resp = litellm.completion(
                        **self._build_completion_params(
                            messages=reflection_messages,
                            temperature=temperature,
                            stream=False,  # Force non-streaming
                            response_format={"type": "json_object"},
                            output_json=output_json,
                            output_pydantic=output_pydantic,
                            **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                        )
                    )
                    # Grab reflection text and optional reasoning
                    reasoning_content = reflection_resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                    reflection_text = reflection_resp["choices"][0]["message"]["content"]

                    # Optionally display reasoning if present
                    if verbose and reasoning_content:
                        display_interaction(
                            "Reflection reasoning:",
                            f"{reasoning_content}\n\nReflection result:\n{reflection_text}",
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=self.console,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            agent_tools=agent_tools,
                            task_name=task_name,
                            task_description=task_description,
                            task_id=task_id
                        )
                    elif verbose:
                        display_interaction(
                            "Self-reflection (non-streaming):",
                            reflection_text,
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=self.console,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            agent_tools=agent_tools,
                            task_name=task_name,
                            task_description=task_description,
                            task_id=task_id
                        )
                else:
                    # Existing streaming approach
                    if verbose:
                        with Live(display_generating("", start_time), console=self.console, refresh_per_second=4) as live:
                            reflection_text = ""
                            for chunk in litellm.completion(
                                **self._build_completion_params(
                                    messages=reflection_messages,
                                    temperature=temperature,
                                    stream=stream,
                                    response_format={"type": "json_object"},
                                    output_json=output_json,
                                    output_pydantic=output_pydantic,
                                    **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    content = chunk.choices[0].delta.content
                                    reflection_text += content
                                    live.update(display_generating(reflection_text, start_time))
                    else:
                        reflection_text = ""
                        for chunk in litellm.completion(
                            **self._build_completion_params(
                                messages=reflection_messages,
                                temperature=temperature,
                                stream=stream,
                                response_format={"type": "json_object"},
                                output_json=output_json,
                                output_pydantic=output_pydantic,
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                            )
                        ):
                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                reflection_text += chunk.choices[0].delta.content

                try:
                    reflection_data = json.loads(reflection_text)
                    satisfactory = reflection_data.get("satisfactory", "no").lower() == "yes"

                    if verbose:
                        display_self_reflection(
                            f"Agent {agent_name} self reflection: reflection='{reflection_data['reflection']}' satisfactory='{reflection_data['satisfactory']}'",
                            console=self.console
                        )

                    if satisfactory and reflection_count >= min_reflect - 1:
                        if verbose and not interaction_displayed:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=self.console,
                                             agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                             task_name=task_name, task_description=task_description, task_id=task_id)
                            interaction_displayed = True
                        return response_text

                    if reflection_count >= max_reflect - 1:
                        if verbose and not interaction_displayed:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=self.console,
                                             agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                             task_name=task_name, task_description=task_description, task_id=task_id)
                            interaction_displayed = True
                        return response_text

                    reflection_count += 1
                    messages.extend([
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": reflection_prompt},
                        {"role": "assistant", "content": reflection_text},
                        {"role": "user", "content": "Now regenerate your response using the reflection you made"}
                    ])
                    
                    # Get new response after reflection
                    if verbose:
                        with Live(display_generating("", time.time()), console=self.console, refresh_per_second=4) as live:
                            response_text = ""
                            for chunk in litellm.completion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=True,
                                    tools=formatted_tools,
                                    output_json=output_json,
                                    output_pydantic=output_pydantic,
                                    **kwargs
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    content = chunk.choices[0].delta.content
                                    response_text += content
                                    live.update(display_generating(response_text, time.time()))
                    else:
                        response_text = ""
                        for chunk in litellm.completion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=True,
                                tools=formatted_tools,
                                output_json=output_json,
                                output_pydantic=output_pydantic,
                                **kwargs
                            )
                        ):
                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                response_text += chunk.choices[0].delta.content
                    
                    response_text = response_text.strip() if response_text else ""
                    continue

                except json.JSONDecodeError:
                    reflection_count += 1
                    if reflection_count >= max_reflect:
                        if verbose and not interaction_displayed:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=self.console,
                                             agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                             task_name=task_name, task_description=task_description, task_id=task_id)
                            interaction_displayed = True
                        return response_text
                    continue
                except Exception as e:
                    display_error(f"Error in LLM response: {str(e)}")
                    return None
            
            # If we've exhausted reflection attempts
            if verbose and not interaction_displayed:
                display_interaction(prompt, response_text, markdown=markdown,
                                 generation_time=time.time() - start_time, console=self.console)
                interaction_displayed = True
            return response_text

        except Exception as error:
            display_error(f"Error in get_response: {str(error)}")
            raise
        
        # Log completion time if in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            total_time = time.time() - start_time
            logging.debug(f"get_response completed in {total_time:.2f} seconds")

    def get_response_stream(
        self,
        prompt: Union[str, List[Dict]],
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict]] = None,
        temperature: float = 0.2,
        tools: Optional[List[Any]] = None,
        output_json: Optional[BaseModel] = None,
        output_pydantic: Optional[BaseModel] = None,
        verbose: bool = False,  # Default to non-verbose for streaming
        markdown: bool = True,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        agent_tools: Optional[List[str]] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        execute_tool_fn: Optional[Callable] = None,
        **kwargs
    ):
        """Generator that yields real-time response chunks from the LLM.
        
        This method provides true streaming by yielding content chunks as they
        are received from the underlying LLM, enabling real-time display of
        responses without waiting for the complete response.
        
        Args:
            prompt: The prompt to send to the LLM
            system_prompt: Optional system prompt
            chat_history: Optional chat history
            temperature: Sampling temperature
            tools: Optional list of tools for function calling
            output_json: Optional JSON schema for structured output
            output_pydantic: Optional Pydantic model for structured output
            verbose: Whether to enable verbose logging (default False for streaming)
            markdown: Whether to enable markdown processing
            agent_name: Optional agent name for logging
            agent_role: Optional agent role for logging
            agent_tools: Optional list of agent tools for logging
            task_name: Optional task name for logging
            task_description: Optional task description for logging
            task_id: Optional task ID for logging
            execute_tool_fn: Optional function for executing tools
            **kwargs: Additional parameters
            
        Yields:
            str: Individual content chunks as they are received from the LLM
            
        Raises:
            Exception: If streaming fails or LLM call encounters an error
        """
        try:
            import litellm
            
            # Build messages using existing logic
            messages, original_prompt = self._build_messages(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                output_json=output_json,
                output_pydantic=output_pydantic
            )
            
            # Format tools for litellm
            formatted_tools = self._format_tools_for_litellm(tools)
            
            # Determine if we should use streaming based on tool support
            use_streaming = True
            if formatted_tools and not self._supports_streaming_tools():
                # Provider doesn't support streaming with tools, fall back to non-streaming
                use_streaming = False
                
            if use_streaming:
                # Real-time streaming approach with tool call support
                try:
                    tool_calls = []
                    response_text = ""
                    consecutive_errors = 0
                    max_consecutive_errors = 3  # Fallback to non-streaming after 3 consecutive errors
                    
                    stream_iterator = litellm.completion(
                        **self._build_completion_params(
                            messages=messages,
                            tools=formatted_tools,
                            temperature=temperature,
                            stream=True,
                            output_json=output_json,
                            output_pydantic=output_pydantic,
                            **kwargs
                        )
                    )
                    
                    # Wrap the iteration with additional error handling for LiteLLM JSON parsing errors
                    try:
                        for chunk in stream_iterator:
                            try:
                                if chunk and chunk.choices and chunk.choices[0].delta:
                                    delta = chunk.choices[0].delta
                                    
                                    # Process both content and tool calls using existing helper
                                    response_text, tool_calls = self._process_stream_delta(
                                        delta, response_text, tool_calls, formatted_tools
                                    )
                                    
                                    # Yield content chunks in real-time as they arrive
                                    if delta.content:
                                        yield delta.content
                                
                                # Reset consecutive error counter only after successful chunk processing
                                consecutive_errors = 0
                                        
                            except Exception as chunk_error:
                                consecutive_errors += 1
                                
                                # Log the specific error for debugging
                                if verbose:
                                    logging.warning(f"Chunk processing error ({consecutive_errors}/{max_consecutive_errors}): {chunk_error}")
                                
                                # Check if this error is recoverable using our helper method
                                if self._is_streaming_error_recoverable(chunk_error):
                                    if verbose:
                                        logging.warning("Recoverable streaming error detected, skipping malformed chunk and continuing")
                                    
                                    # Skip this malformed chunk and continue if we haven't hit the limit
                                    if consecutive_errors < max_consecutive_errors:
                                        continue
                                    else:
                                        # Too many recoverable errors, fallback to non-streaming
                                        logging.warning(f"Too many consecutive streaming errors ({consecutive_errors}), falling back to non-streaming mode")
                                        raise Exception(f"Streaming failed with {consecutive_errors} consecutive errors") from chunk_error
                                else:
                                    # For non-recoverable errors, re-raise immediately
                                    logging.error(f"Non-recoverable streaming error: {chunk_error}")
                                    raise chunk_error
                    
                    except Exception as iterator_error:
                        # Handle errors that occur during stream iteration itself (e.g., JSON parsing in LiteLLM)
                        error_msg = str(iterator_error).lower()
                        
                        # Check if this is a recoverable streaming error (including JSON parsing errors)
                        if self._is_streaming_error_recoverable(iterator_error):
                            if verbose:
                                logging.warning(f"Stream iterator error detected (recoverable): {iterator_error}")
                                logging.warning("Falling back to non-streaming mode due to stream iteration failure")
                            
                            # Force fallback to non-streaming for iterator-level errors
                            raise Exception("Stream iteration failed with recoverable error, falling back to non-streaming") from iterator_error
                        else:
                            # For non-recoverable errors, re-raise immediately
                            logging.error(f"Non-recoverable stream iterator error: {iterator_error}")
                            raise iterator_error
                    
                    # After streaming completes, handle tool calls if present
                    if tool_calls and execute_tool_fn:
                        # Add assistant message with tool calls to conversation
                        if self._is_ollama_provider():
                            messages.append({
                                "role": "assistant",
                                "content": response_text
                            })
                        else:
                            serializable_tool_calls = self._serialize_tool_calls(tool_calls)
                            messages.append({
                                "role": "assistant",
                                "content": response_text,
                                "tool_calls": serializable_tool_calls
                            })
                        
                        # Execute tool calls and add results to conversation
                        for tool_call in tool_calls:
                            is_ollama = self._is_ollama_provider()
                            function_name, arguments, tool_call_id = self._extract_tool_call_info(tool_call, is_ollama)
                            
                            try:
                                # Execute the tool
                                tool_result = execute_tool_fn(function_name, arguments)
                                
                                # Add tool result to messages
                                tool_message = self._create_tool_message(function_name, tool_result, tool_call_id, is_ollama)
                                messages.append(tool_message)
                                
                            except Exception as e:
                                logging.error(f"Tool execution error for {function_name}: {e}")
                                # Add error message to conversation
                                error_message = self._create_tool_message(
                                    function_name, f"Error executing tool: {e}", tool_call_id, is_ollama
                                )
                                messages.append(error_message)
                        
                        # Continue conversation after tool execution - get follow-up response
                        try:
                            follow_up_response = litellm.completion(
                                **self._build_completion_params(
                                    messages=messages,
                                    tools=formatted_tools,
                                    temperature=temperature,
                                    stream=False,
                                    **kwargs
                                )
                            )
                            
                            if follow_up_response and follow_up_response.choices:
                                follow_up_content = follow_up_response.choices[0].message.content
                                if follow_up_content:
                                    # Yield the follow-up response after tool execution
                                    yield follow_up_content
                        except Exception as e:
                            logging.error(f"Follow-up response failed: {e}")
                            
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # Provide more specific error messages based on the error type
                    if any(keyword in error_msg for keyword in ['json', 'expecting property name', 'parse', 'decode']):
                        logging.warning(f"Streaming failed due to JSON parsing errors (likely malformed chunks from provider): {e}")
                    elif 'connection' in error_msg or 'timeout' in error_msg:
                        logging.warning(f"Streaming failed due to connection issues: {e}")
                    else:
                        logging.error(f"Streaming failed with unexpected error: {e}")
                    
                    # Fall back to non-streaming if streaming fails
                    use_streaming = False
            
            if not use_streaming:
                # Fall back to non-streaming and yield the complete response
                try:
                    response = litellm.completion(
                        **self._build_completion_params(
                            messages=messages,
                            tools=formatted_tools,
                            temperature=temperature,
                            stream=False,
                            output_json=output_json,
                            output_pydantic=output_pydantic,
                            **kwargs
                        )
                    )
                    
                    if response and response.choices:
                        content = response.choices[0].message.content
                        if content:
                            # Yield the complete response as a single chunk
                            yield content
                            
                except Exception as e:
                    logging.error(f"Non-streaming fallback failed: {e}")
                    raise
                    
        except Exception as e:
            logging.error(f"Error in get_response_stream: {e}")
            raise

    def _is_gemini_model(self) -> bool:
        """Check if the model is a Gemini model."""
        if not self.model:
            return False
        return any(prefix in self.model.lower() for prefix in ['gemini', 'gemini/', 'google/gemini'])
    
    def _is_streaming_error_recoverable(self, error: Exception) -> bool:
        """Check if a streaming error is recoverable (e.g., malformed chunk vs connection error)."""
        error_msg = str(error).lower()
        
        # JSON parsing errors are often recoverable (skip malformed chunk and continue)
        json_error_keywords = ['json', 'expecting property name', 'parse', 'decode', 'invalid json']
        if any(keyword in error_msg for keyword in json_error_keywords):
            return True
            
        # Connection errors might be temporary but are less recoverable in streaming context
        connection_error_keywords = ['connection', 'timeout', 'network', 'http']
        if any(keyword in error_msg for keyword in connection_error_keywords):
            return False
            
        # Other errors are generally not recoverable
        return False

    async def get_response_async(
        self,
        prompt: Union[str, List[Dict]],
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict]] = None,
        temperature: float = 0.2,
        tools: Optional[List[Any]] = None,
        output_json: Optional[BaseModel] = None,
        output_pydantic: Optional[BaseModel] = None,
        verbose: bool = True,
        markdown: bool = True,
        self_reflect: bool = False,
        max_reflect: int = 3,
        min_reflect: int = 1,
        console: Optional[Console] = None,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        agent_tools: Optional[List[str]] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        execute_tool_fn: Optional[Callable] = None,
        stream: bool = True,
        **kwargs
    ) -> str:
        """Async version of get_response with identical functionality."""
        try:
            import litellm
            logging.info(f"Getting async response from {self.model}")
            # Log all self values when in debug mode
            self._log_llm_config(
                'get_response_async',
                model=self.model,
                timeout=self.timeout,
                temperature=self.temperature,
                top_p=self.top_p,
                n=self.n,
                max_tokens=self.max_tokens,
                presence_penalty=self.presence_penalty,
                frequency_penalty=self.frequency_penalty,
                logit_bias=self.logit_bias,
                response_format=self.response_format,
                seed=self.seed,
                logprobs=self.logprobs,
                top_logprobs=self.top_logprobs,
                api_version=self.api_version,
                stop_phrases=self.stop_phrases,
                api_key=self.api_key,
                base_url=self.base_url,
                verbose=self.verbose,
                markdown=self.markdown,
                self_reflect=self.self_reflect,
                max_reflect=self.max_reflect,
                min_reflect=self.min_reflect,
                reasoning_steps=self.reasoning_steps
            )
            
            # Log the parameter values passed to get_response_async
            self._log_llm_config(
                'get_response_async parameters',
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                temperature=temperature,
                tools=tools,
                output_json=output_json,
                output_pydantic=output_pydantic,
                verbose=verbose,
                markdown=markdown,
                self_reflect=self_reflect,
                max_reflect=max_reflect,
                min_reflect=min_reflect,
                agent_name=agent_name,
                agent_role=agent_role,
                agent_tools=agent_tools,
                kwargs=str(kwargs)
            )
            reasoning_steps = kwargs.pop('reasoning_steps', self.reasoning_steps)
            litellm.set_verbose = False

            # Build messages list using shared helper
            messages, original_prompt = self._build_messages(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                output_json=output_json,
                output_pydantic=output_pydantic
            )

            start_time = time.time()
            reflection_count = 0
            callback_executed = False  # Track if callback has been executed for this interaction
            interaction_displayed = False  # Track if interaction has been displayed

            # Format tools for LiteLLM using the shared helper
            formatted_tools = self._format_tools_for_litellm(tools)

            # Initialize variables for iteration loop
            max_iterations = 10  # Prevent infinite loops
            iteration_count = 0
            final_response_text = ""
            stored_reasoning_content = None  # Store reasoning content from tool execution
            accumulated_tool_results = []  # Store all tool results across iterations

            while iteration_count < max_iterations:
                response_text = ""
                reasoning_content = None
                tool_calls = []
                
                if reasoning_steps and iteration_count == 0:
                    # Non-streaming call to capture reasoning
                    resp = await litellm.acompletion(
                        **self._build_completion_params(
                            messages=messages,
                            temperature=temperature,
                            stream=False,  # force non-streaming
                            output_json=output_json,
                            output_pydantic=output_pydantic,
                            **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                        )
                    )
                    reasoning_content = resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                    response_text = resp["choices"][0]["message"]["content"]
                    
                    if verbose and reasoning_content and not interaction_displayed:
                        display_interaction(
                            "Initial reasoning:",
                            f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}",
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=self.console,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            agent_tools=agent_tools,
                            task_name=task_name,
                            task_description=task_description,
                            task_id=task_id
                        )
                        interaction_displayed = True
                    elif verbose and not interaction_displayed:
                        display_interaction(
                            "Initial response:",
                            response_text,
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=self.console,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            agent_tools=agent_tools,
                            task_name=task_name,
                            task_description=task_description,
                            task_id=task_id
                        )
                        interaction_displayed = True
                else:
                    # Determine if we should use streaming based on tool support
                    use_streaming = stream
                    if formatted_tools and not self._supports_streaming_tools():
                        # Provider doesn't support streaming with tools, use non-streaming
                        use_streaming = False
                    
                    if use_streaming:
                        # Streaming approach (with or without tools)
                        tool_calls = []
                        
                        if verbose:
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=True,
                                    tools=formatted_tools,
                                    output_json=output_json,
                                    output_pydantic=output_pydantic,
                                    **kwargs
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta:
                                    delta = chunk.choices[0].delta
                                    response_text, tool_calls = self._process_stream_delta(
                                        delta, response_text, tool_calls, formatted_tools
                                    )
                                    if delta.content:
                                        print("\033[K", end="\r")  
                                        print(f"Generating... {time.time() - start_time:.1f}s", end="\r")

                        else:
                            # Non-verbose streaming
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=True,
                                    tools=formatted_tools,
                                    output_json=output_json,
                                    output_pydantic=output_pydantic,
                                    **kwargs
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta:
                                    delta = chunk.choices[0].delta
                                    if delta.content:
                                        response_text += delta.content
                                    
                                    # Capture tool calls from streaming chunks if provider supports it
                                    if formatted_tools and self._supports_streaming_tools():
                                        tool_calls = self._process_tool_calls_from_stream(delta, tool_calls)
                        
                        response_text = response_text.strip() if response_text else ""
                        
                        # We already have tool_calls from streaming if supported
                        # No need for a second API call!
                    else:
                        # Non-streaming approach (when tools require it or streaming is disabled)
                        tool_response = await litellm.acompletion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=False,
                                tools=formatted_tools,
                                output_json=output_json,
                                output_pydantic=output_pydantic,
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                            )
                        )
                        # Handle None content from Gemini
                        response_content = tool_response.choices[0].message.get("content")
                        response_text = response_content if response_content is not None else ""
                        tool_calls = tool_response.choices[0].message.get("tool_calls", [])
                        
                        # Debug logging for Gemini responses
                        if self._is_gemini_model():
                            logging.debug(f"Gemini response content: {response_content} -> {response_text}")
                            logging.debug(f"Gemini tool calls: {tool_calls}")
                        
                        if verbose and not interaction_displayed:
                            # Display the complete response at once
                            display_interaction(
                                original_prompt,
                                response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=self.console,
                                agent_name=agent_name,
                                agent_role=agent_role,
                                agent_tools=agent_tools,
                                task_name=task_name,
                                task_description=task_description,
                                task_id=task_id
                            )
                            interaction_displayed = True

                # For Ollama, if response is empty but we have tools, prompt for tool usage
                if self._is_ollama_provider() and (not response_text or response_text.strip() == "") and formatted_tools and iteration_count == 0:
                    messages.append({
                        "role": "user",
                        "content": self.OLLAMA_TOOL_USAGE_PROMPT
                    })
                    iteration_count += 1
                    continue
                
                # Now handle tools if we have them (either from streaming or non-streaming)
                if tools and execute_tool_fn and tool_calls:
                    # Convert tool_calls to a serializable format for all providers
                    serializable_tool_calls = self._serialize_tool_calls(tool_calls)
                    # Check if it's Ollama provider
                    if self._is_ollama_provider():
                        # For Ollama, only include role and content
                        messages.append({
                            "role": "assistant",
                            "content": response_text
                        })
                    else:
                        # For other providers, include tool_calls
                        messages.append({
                            "role": "assistant",
                            "content": response_text,
                            "tool_calls": serializable_tool_calls
                        })
                    
                    tool_results = []  # Store current iteration tool results
                    for tool_call in tool_calls:
                        # Handle both object and dict access patterns
                        is_ollama = self._is_ollama_provider()
                        function_name, arguments, tool_call_id = self._extract_tool_call_info(tool_call, is_ollama)

                        # Validate and filter arguments for Ollama provider
                        if is_ollama and tools:
                            arguments = self._validate_and_filter_ollama_arguments(function_name, arguments, tools)

                        tool_result = await execute_tool_fn(function_name, arguments)
                        tool_results.append(tool_result)  # Store the result
                        accumulated_tool_results.append(tool_result)  # Accumulate across iterations

                        if verbose:
                            display_message = f"Agent {agent_name} called function '{function_name}' with arguments: {arguments}\n"
                            if tool_result:
                                display_message += f"Function returned: {tool_result}"
                            else:
                                display_message += "Function returned no output"
                            display_tool_call(display_message, console=self.console)
                        # Check if it's Ollama provider
                        if self._is_ollama_provider():
                            # For Ollama, use user role and format as natural language
                            messages.append(self._format_ollama_tool_result_message(function_name, tool_result))
                        else:
                            # For other providers, use tool role with tool_call_id
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": json.dumps(tool_result) if tool_result is not None else "Function returned an empty output"
                            })

                    # For Ollama, add explicit prompt if we need a final answer
                    if self._is_ollama_provider() and iteration_count > 0:
                        # Add an explicit prompt for Ollama to generate the final answer
                        messages.append({
                            "role": "user", 
                            "content": self.OLLAMA_FINAL_ANSWER_PROMPT
                        })
                    
                    # Get response after tool calls
                    response_text = ""
                    
                    # If no special handling was needed
                    if reasoning_steps:
                        # Non-streaming call to capture reasoning
                        resp = await litellm.acompletion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=False,  # force non-streaming
                                tools=formatted_tools,  # Include tools
                                output_json=output_json,
                                output_pydantic=output_pydantic,
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                            )
                        )
                        reasoning_content = resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                        response_text = resp["choices"][0]["message"]["content"]
                        
                        if verbose and reasoning_content and not interaction_displayed:
                            display_interaction(
                                "Tool response reasoning:",
                                f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}",
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=self.console,
                                agent_name=agent_name,
                                agent_role=agent_role,
                                agent_tools=agent_tools,
                                task_name=task_name,
                                task_description=task_description,
                                task_id=task_id
                            )
                            interaction_displayed = True
                        elif verbose and not interaction_displayed:
                            display_interaction(
                                "Tool response:",
                                response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=self.console,
                                agent_name=agent_name,
                                agent_role=agent_role,
                                agent_tools=agent_tools,
                                task_name=task_name,
                                task_description=task_description,
                                task_id=task_id
                            )
                            interaction_displayed = True
                    else:
                        # Get response after tool calls with streaming if not already handled
                        if verbose:
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=stream,
                                    tools=formatted_tools,
                                    output_json=output_json,
                                    output_pydantic=output_pydantic,
                                    **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    content = chunk.choices[0].delta.content
                                    response_text += content
                                    print("\033[K", end="\r")
                                    print(f"Reflecting... {time.time() - start_time:.1f}s", end="\r")
                        else:
                            response_text = ""
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=stream,
                                    output_json=output_json,
                                    output_pydantic=output_pydantic,
                                    **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    response_text += chunk.choices[0].delta.content

                    response_text = response_text.strip() if response_text else ""
                    
                    # After tool execution, update messages and continue the loop
                    if response_text:
                        messages.append({
                            "role": "assistant",
                            "content": response_text
                        })
                    
                    # Store reasoning content if captured
                    if reasoning_steps and reasoning_content:
                        stored_reasoning_content = reasoning_content
                    
                    # Check if the LLM provided a final answer alongside the tool calls
                    # If response_text contains substantive content, treat it as the final answer
                    if response_text and len(response_text.strip()) > 10:
                        # LLM provided a final answer after tool execution, don't continue
                        final_response_text = response_text.strip()
                        break
                    
                    
                    # Special handling for Ollama to prevent infinite loops
                    # Only generate summary after multiple iterations to allow sequential execution
                    should_break, tool_summary_text, iteration_count = self._handle_ollama_sequential_logic(
                        iteration_count, accumulated_tool_results, response_text, messages
                    )
                    if should_break:
                        final_response_text = tool_summary_text
                        # Reset interaction_displayed to ensure final summary is shown
                        interaction_displayed = False
                        break
                    elif tool_summary_text is None and iteration_count > self.OLLAMA_SUMMARY_ITERATION_THRESHOLD:
                        # Continue iteration after adding final answer prompt
                        continue
                    
                    # Safety check: prevent infinite loops for any provider
                    if iteration_count >= 5:
                        if tool_results:
                            final_response_text = "Task completed successfully based on tool execution results."
                        else:
                            final_response_text = response_text.strip() if response_text else "Task completed."
                        break
                    
                    # Continue the loop to check if more tools are needed
                    iteration_count += 1
                    continue
                else:
                    # No tool calls, we're done with this iteration
                    
                    # Special early stopping logic for Ollama when tool results are available
                    # Ollama often provides empty responses after successful tool execution
                    if (self._is_ollama_provider() and accumulated_tool_results and iteration_count >= 1 and 
                        (not response_text or response_text.strip() == "")):
                        # Generate coherent response from tool results
                        tool_summary = self._generate_ollama_tool_summary(accumulated_tool_results, response_text)
                        if tool_summary:
                            final_response_text = tool_summary
                            # Reset interaction_displayed to ensure final summary is shown
                            interaction_displayed = False
                            break
                    
                    # If we've executed tools in previous iterations, this response contains the final answer
                    if iteration_count > 0 and not final_response_text:
                        final_response_text = response_text.strip()
                    break

            # Handle output formatting
            if output_json or output_pydantic:
                self.chat_history.append({"role": "user", "content": original_prompt})
                self.chat_history.append({"role": "assistant", "content": response_text})
                if verbose and not interaction_displayed:
                    display_interaction(original_prompt, response_text, markdown=markdown,
                                     generation_time=time.time() - start_time, console=self.console,
                                     agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                     task_name=task_name, task_description=task_description, task_id=task_id)
                    interaction_displayed = True
                return response_text

            if not self_reflect:
                # Use final_response_text if we went through tool iterations
                display_text = final_response_text if final_response_text else response_text
                
                # Display with stored reasoning content if available
                if verbose and not interaction_displayed:
                    if stored_reasoning_content:
                        display_interaction(
                            original_prompt,
                            f"Reasoning:\n{stored_reasoning_content}\n\nAnswer:\n{display_text}",
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=self.console,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            agent_tools=agent_tools,
                            task_name=task_name,
                            task_description=task_description,
                            task_id=task_id
                        )
                    else:
                        display_interaction(original_prompt, display_text, markdown=markdown,
                                         generation_time=time.time() - start_time, console=self.console,
                                         agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                         task_name=task_name, task_description=task_description, task_id=task_id)
                    interaction_displayed = True
                
                # Return reasoning content if reasoning_steps is True and we have it
                if reasoning_steps and stored_reasoning_content:
                    return stored_reasoning_content
                return display_text

            # Handle self-reflection
            reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
Identify any flaws, improvements, or actions.
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
            """
            
            reflection_messages = messages + [
                {"role": "assistant", "content": response_text},
                {"role": "user", "content": reflection_prompt}
            ]

            # If reasoning_steps is True, do a single non-streaming call to capture reasoning
            if reasoning_steps:
                reflection_resp = await litellm.acompletion(
                    **self._build_completion_params(
                        messages=reflection_messages,
                        temperature=temperature,
                        stream=False,  # Force non-streaming
                        response_format={"type": "json_object"},
                        output_json=output_json,
                        output_pydantic=output_pydantic,
                        **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                    )
                )
                # Grab reflection text and optional reasoning
                reasoning_content = reflection_resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                reflection_text = reflection_resp["choices"][0]["message"]["content"]

                # Optionally display reasoning if present
                if verbose and reasoning_content:
                    display_interaction(
                        "Reflection reasoning:",
                        f"{reasoning_content}\n\nReflection result:\n{reflection_text}",
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        console=self.console,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
                elif verbose:
                    display_interaction(
                        "Self-reflection (non-streaming):",
                        reflection_text,
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        console=self.console,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        agent_tools=agent_tools,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id
                    )
            else:
                # Existing streaming approach
                if verbose:
                    with Live(display_generating("", start_time), console=self.console, refresh_per_second=4) as live:
                        reflection_text = ""
                        async for chunk in await litellm.acompletion(
                            **self._build_completion_params(
                                messages=reflection_messages,
                                temperature=temperature,
                                stream=stream,
                                response_format={"type": "json_object"},
                                output_json=output_json,
                                output_pydantic=output_pydantic,
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                            )
                        ):
                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                reflection_text += content
                                live.update(display_generating(reflection_text, start_time))
                else:
                    reflection_text = ""
                    async for chunk in await litellm.acompletion(
                        **self._build_completion_params(
                            messages=reflection_messages,
                            temperature=temperature,
                            stream=stream,
                            response_format={"type": "json_object"},
                            output_json=output_json,
                            output_pydantic=output_pydantic,
                            **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                        )
                    ):
                        if chunk and chunk.choices and chunk.choices[0].delta.content:
                            reflection_text += chunk.choices[0].delta.content

            while True:  # Add loop for reflection handling
                try:
                    reflection_data = json.loads(reflection_text)
                    satisfactory = reflection_data.get("satisfactory", "no").lower() == "yes"

                    if verbose:
                        display_self_reflection(
                            f"Agent {agent_name} self reflection: reflection='{reflection_data['reflection']}' satisfactory='{reflection_data['satisfactory']}'",
                            console=self.console
                        )

                    if satisfactory and reflection_count >= min_reflect - 1:
                        if verbose and not interaction_displayed:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=self.console,
                                             agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                             task_name=task_name, task_description=task_description, task_id=task_id)
                            interaction_displayed = True
                        return response_text

                    if reflection_count >= max_reflect - 1:
                        if verbose and not interaction_displayed:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=self.console,
                                             agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools,
                                             task_name=task_name, task_description=task_description, task_id=task_id)
                            interaction_displayed = True
                        return response_text

                    reflection_count += 1
                    messages.extend([
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": reflection_prompt},
                        {"role": "assistant", "content": reflection_text},
                        {"role": "user", "content": "Now regenerate your response using the reflection you made"}
                    ])
                    continue  # Now properly in a loop

                except json.JSONDecodeError:
                    reflection_count += 1
                    if reflection_count >= max_reflect:
                        return response_text
                    continue  # Now properly in a loop
            
        except Exception as error:
            if LLMContextLengthExceededException(str(error))._is_context_limit_error(str(error)):
                raise LLMContextLengthExceededException(str(error))
            display_error(f"Error in get_response_async: {str(error)}")
            raise
            
        # Log completion time if in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            total_time = time.time() - start_time
            logging.debug(f"get_response_async completed in {total_time:.2f} seconds")

    def can_use_tools(self) -> bool:
        """Check if this model can use tool functions"""
        try:
            import litellm
            allowed_params = litellm.get_supported_openai_params(model=self.model)
            return "response_format" in allowed_params
        except ImportError:
            raise ImportError(
                "LiteLLM is required but not installed. "
                "Please install it with: pip install 'praisonaiagents[llm]'"
            )
        except:
            return False

    def can_use_stop_words(self) -> bool:
        """Check if this model supports stop words"""
        try:
            import litellm
            allowed_params = litellm.get_supported_openai_params(model=self.model)
            return "stop" in allowed_params
        except ImportError:
            raise ImportError(
                "LiteLLM is required but not installed. "
                "Please install it with: pip install 'praisonaiagents[llm]'"
            )
        except:
            return False

    def get_context_size(self) -> int:
        """Get safe input size limit for this model"""
        for model_prefix, size in self.MODEL_WINDOWS.items():
            if self.model.startswith(model_prefix):
                return size
        return 4000  # Safe default

    def _setup_event_tracking(self, events: List[Any]) -> None:
        """Setup callback functions for tracking model usage"""
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "LiteLLM is required but not installed. "
                "Please install it with: pip install 'praisonaiagents[llm]'"
            )

        event_types = [type(event) for event in events]
        
        # Remove old events of same type
        for event in litellm.success_callback[:]:
            if type(event) in event_types:
                litellm.success_callback.remove(event)
                
        for event in litellm._async_success_callback[:]:
            if type(event) in event_types:
                litellm._async_success_callback.remove(event)
                
        litellm.callbacks = events

    def _track_token_usage(self, response: Dict[str, Any], model: str) -> Optional[TokenMetrics]:
        """Extract and track token usage from LLM response."""
        if not TokenMetrics or not _token_collector:
            return None
        
        # Note: metrics check moved to call sites for performance
        # This method should only be called when self.metrics=True
        
        try:
            usage = response.get("usage", {})
            if not usage:
                return None
            
            # Extract token counts
            metrics = TokenMetrics(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                cached_tokens=usage.get("cached_tokens", 0),
                reasoning_tokens=usage.get("reasoning_tokens", 0),
                audio_input_tokens=usage.get("audio_input_tokens", 0),
                audio_output_tokens=usage.get("audio_output_tokens", 0)
            )
            
            # Store metrics
            self.last_token_metrics = metrics
            
            # Update session metrics
            if not self.session_token_metrics:
                self.session_token_metrics = TokenMetrics()
            self.session_token_metrics = self.session_token_metrics + metrics
            
            # Track in global collector
            _token_collector.track_tokens(
                model=model,
                agent=self.current_agent_name,
                metrics=metrics,
                metadata={
                    "provider": self.provider,
                    "stream": False
                }
            )
            
            return metrics
            
        except Exception as e:
            if self.verbose:
                logging.warning(f"Failed to track token usage: {e}")
            return None
    
    def set_current_agent(self, agent_name: Optional[str]):
        """Set the current agent name for token tracking."""
        self.current_agent_name = agent_name

    def _build_completion_params(self, **override_params) -> Dict[str, Any]:
        """Build parameters for litellm completion calls with all necessary config"""
        params = {
            "model": self.model,
        }
        
        # Add optional parameters if they exist
        if self.base_url:
            params["base_url"] = self.base_url
        if self.api_key:
            params["api_key"] = self.api_key
        if self.api_version:
            params["api_version"] = self.api_version
        if self.timeout:
            params["timeout"] = self.timeout
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens
        if self.top_p:
            params["top_p"] = self.top_p
        if self.presence_penalty:
            params["presence_penalty"] = self.presence_penalty
        if self.frequency_penalty:
            params["frequency_penalty"] = self.frequency_penalty
        if self.logit_bias:
            params["logit_bias"] = self.logit_bias
        if self.response_format:
            params["response_format"] = self.response_format
        if self.seed:
            params["seed"] = self.seed
        if self.logprobs:
            params["logprobs"] = self.logprobs
        if self.top_logprobs:
            params["top_logprobs"] = self.top_logprobs
        if self.stop_phrases:
            params["stop"] = self.stop_phrases
        
        # Add extra settings for provider-specific parameters (e.g., num_ctx for Ollama)
        if self.extra_settings:
            params.update(self.extra_settings)
        
        # Override with any provided parameters
        params.update(override_params)
        
        # Handle structured output parameters
        output_json = override_params.get('output_json')
        output_pydantic = override_params.get('output_pydantic')
        
        # Always remove these from params as they're not native litellm parameters
        params.pop('output_json', None)
        params.pop('output_pydantic', None)
        
        if output_json or output_pydantic:
            
            # Check if this is a Gemini model that supports native structured outputs
            if self._is_gemini_model():
                from .model_capabilities import supports_structured_outputs
                schema_model = output_json or output_pydantic
                
                if schema_model and hasattr(schema_model, 'model_json_schema') and supports_structured_outputs(self.model):
                    schema = schema_model.model_json_schema()
                    
                    # Gemini uses response_mime_type and response_schema
                    params['response_mime_type'] = 'application/json'
                    params['response_schema'] = schema
                    
                    logging.debug(f"Using Gemini native structured output with schema: {json.dumps(schema, indent=2)}")
        
        # Add tool_choice="auto" when tools are provided (unless already specified)
        if 'tools' in params and params['tools'] and 'tool_choice' not in params:
            # For Gemini models, use tool_choice to encourage tool usage
            if self._is_gemini_model():
                try:
                    import litellm
                    # Check if model supports function calling before setting tool_choice
                    if litellm.supports_function_calling(model=self.model):
                        params['tool_choice'] = 'auto'
                except Exception as e:
                    # If check fails, still set tool_choice for known Gemini models
                    logging.debug(f"Could not verify function calling support: {e}. Setting tool_choice anyway.")
                    params['tool_choice'] = 'auto'
        
        return params

    def _prepare_response_logging(self, temperature: float, stream: bool, verbose: bool, markdown: bool, **kwargs) -> Optional[Dict[str, Any]]:
        """Prepare debug logging information for response methods"""
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            debug_info = {
                "model": self.model,
                "timeout": self.timeout,
                "temperature": temperature,
                "top_p": self.top_p,
                "n": self.n,
                "max_tokens": self.max_tokens,
                "presence_penalty": self.presence_penalty,
                "frequency_penalty": self.frequency_penalty,
                "stream": stream,
                "verbose": verbose,
                "markdown": markdown,
                "kwargs": str(kwargs)
            }
            return debug_info
        return None

    def _process_streaming_chunk(self, chunk) -> Optional[str]:
        """Extract content from a streaming chunk"""
        if chunk and chunk.choices and chunk.choices[0].delta.content:
            return chunk.choices[0].delta.content
        return None

    def _process_tool_calls_from_stream(self, delta, tool_calls: List[Dict]) -> List[Dict]:
        """Process tool calls from streaming delta chunks.
        
        This handles the accumulation of tool call data from streaming chunks,
        building up the complete tool call information incrementally.
        """
        if hasattr(delta, 'tool_calls') and delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.index >= len(tool_calls):
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": "", "arguments": ""}
                    })
                if tc.function.name:
                    tool_calls[tc.index]["function"]["name"] = tc.function.name
                if tc.function.arguments:
                    tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
        return tool_calls

    def _serialize_tool_calls(self, tool_calls) -> List[Dict]:
        """Convert tool calls to a serializable format for all providers."""
        serializable_tool_calls = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                serializable_tool_calls.append(tc)  # Already a dict
            else:
                # Convert object to dict
                serializable_tool_calls.append({
                    "id": tc.id,
                    "type": getattr(tc, 'type', "function"),
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })
        return serializable_tool_calls

    def _extract_tool_call_info(self, tool_call, is_ollama: bool = False) -> tuple:
        """Extract function name, arguments, and tool_call_id from a tool call.
        
        Handles both dict and object formats for tool calls.
        """
        if isinstance(tool_call, dict):
            return self._parse_tool_call_arguments(tool_call, is_ollama)
        else:
            # Handle object-style tool calls
            try:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                tool_call_id = tool_call.id
            except (json.JSONDecodeError, AttributeError) as e:
                logging.error(f"Error parsing object-style tool call: {e}")
                function_name = "unknown_function"
                arguments = {}
                tool_call_id = f"tool_{id(tool_call)}"
            return function_name, arguments, tool_call_id

    # Response without tool calls
    def response(
        self,
        prompt: Union[str, List[Dict]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream: bool = True,
        verbose: bool = True,
        markdown: bool = True,
        console: Optional[Console] = None,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        agent_tools: Optional[List[str]] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Simple function to get model response without tool calls or complex features"""
        try:
            import litellm
            import logging
            logger = logging.getLogger(__name__)
            
            litellm.set_verbose = False
            start_time = time.time()
            
            logger.debug("Using synchronous response function")
            
            # Log all self values when in debug mode
            self._log_llm_config(
                'Response method',
                model=self.model,
                timeout=self.timeout,
                temperature=temperature,
                top_p=self.top_p,
                n=self.n,
                max_tokens=self.max_tokens,
                presence_penalty=self.presence_penalty,
                frequency_penalty=self.frequency_penalty,
                stream=stream,
                verbose=verbose,
                markdown=markdown,
                kwargs=str(kwargs)
            )
            
            # Build messages list using shared helper (simplified version without JSON output)
            messages, _ = self._build_messages(
                prompt=prompt,
                system_prompt=system_prompt
            )

            # Get response from LiteLLM
            response_text = ""
            completion_params = self._build_completion_params(
                messages=messages,
                temperature=temperature,
                stream=stream,
                **kwargs
            )
            
            if stream:
                with Live(display_generating("", start_time), console=console or self.console, refresh_per_second=4) as live:
                    for chunk in litellm.completion(**completion_params):
                        content = self._process_streaming_chunk(chunk)
                        if content:
                            response_text += content
                            live.update(display_generating(response_text, start_time))
                        if content:
                            response_text += content
            else:
                response = litellm.completion(**completion_params)
                response_text = response.choices[0].message.content.strip() if response.choices[0].message.content else ""

            if verbose:
                display_interaction(
                    prompt if isinstance(prompt, str) else prompt[0].get("text", ""),
                    response_text,
                    markdown=markdown,
                    generation_time=time.time() - start_time,
                    console=console or self.console,
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_tools=agent_tools,
                    task_name=task_name,
                    task_description=task_description,
                    task_id=task_id
                )
            
            return response_text.strip() if response_text else ""

        except Exception as error:
            display_error(f"Error in response: {str(error)}")
            raise

    # Async version of response function. Response without tool calls
    async def aresponse(
        self,
        prompt: Union[str, List[Dict]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream: bool = True,
        verbose: bool = True,
        markdown: bool = True,
        console: Optional[Console] = None,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        agent_tools: Optional[List[str]] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Async version of response function"""
        try:
            import litellm
            import logging
            logger = logging.getLogger(__name__)
            
            litellm.set_verbose = False
            start_time = time.time()
            
            logger.debug("Using asynchronous response function")
            

            # Log all self values when in debug mode
            self._log_llm_config(
                'Async response method',
                model=self.model,
                timeout=self.timeout,
                temperature=temperature,
                top_p=self.top_p,
                n=self.n,
                max_tokens=self.max_tokens,
                presence_penalty=self.presence_penalty,
                frequency_penalty=self.frequency_penalty,
                stream=stream,
                verbose=verbose,
                markdown=markdown,
                kwargs=str(kwargs)
            )
            
            # Build messages list using shared helper (simplified version without JSON output)
            messages, _ = self._build_messages(
                prompt=prompt,
                system_prompt=system_prompt
            )

            # Get response from LiteLLM
            response_text = ""
            completion_params = self._build_completion_params(
                messages=messages,
                temperature=temperature,
                stream=stream,
                **kwargs
            )
            
            if stream:
                with Live(display_generating("", start_time), console=console or self.console, refresh_per_second=4) as live:
                    async for chunk in await litellm.acompletion(**completion_params):
                        content = self._process_streaming_chunk(chunk)
                        if content:
                            response_text += content
                            live.update(display_generating(response_text, start_time))
                        if content:
                            response_text += content
            else:
                response = await litellm.acompletion(**completion_params)
                response_text = response.choices[0].message.content.strip() if response.choices[0].message.content else ""

            if verbose:
                display_interaction(
                    prompt if isinstance(prompt, str) else prompt[0].get("text", ""),
                    response_text,
                    markdown=markdown,
                    generation_time=time.time() - start_time,
                    console=console or self.console,
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_tools=agent_tools,
                    task_name=task_name,
                    task_description=task_description,
                    task_id=task_id
                )
            
            return response_text.strip() if response_text else ""

        except Exception as error:
            display_error(f"Error in response_async: {str(error)}")
            raise

    def _generate_tool_definition(self, function_or_name) -> Optional[Dict]:
        """Generate a tool definition from a function or function name."""
        if callable(function_or_name):
            # Function object passed directly
            func = function_or_name
            function_name = func.__name__
            logging.debug(f"Generating tool definition for callable: {function_name}")
        else:
            # Function name string passed
            function_name = function_or_name
            logging.debug(f"Attempting to generate tool definition for: {function_name}")
            
            # First try to get the tool definition if it exists
            tool_def_name = f"{function_name}_definition"
            tool_def = globals().get(tool_def_name)
            logging.debug(f"Looking for {tool_def_name} in globals: {tool_def is not None}")
            
            if not tool_def:
                import __main__
                tool_def = getattr(__main__, tool_def_name, None)
                logging.debug(f"Looking for {tool_def_name} in __main__: {tool_def is not None}")
            
            if tool_def:
                logging.debug(f"Found tool definition: {tool_def}")
                return tool_def

            # Try to find the function
            func = globals().get(function_name)
            logging.debug(f"Looking for {function_name} in globals: {func is not None}")
            
            if not func:
                import __main__
                func = getattr(__main__, function_name, None)
                logging.debug(f"Looking for {function_name} in __main__: {func is not None}")
            
            if not func or not callable(func):
                logging.debug(f"Function {function_name} not found or not callable")
                return None

        import inspect
        # Handle Langchain and CrewAI tools
        if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
            original_func = func
            func = func.run
            function_name = original_func.__name__
        elif inspect.isclass(func) and hasattr(func, '_run'):
            original_func = func
            func = func._run
            function_name = original_func.__name__

        sig = inspect.signature(func)
        logging.debug(f"Function signature: {sig}")
        
        # Skip self, *args, **kwargs
        parameters_list = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            parameters_list.append((name, param))

        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Parse docstring for parameter descriptions
        docstring = inspect.getdoc(func)
        logging.debug(f"Function docstring: {docstring}")
        
        param_descriptions = {}
        if docstring:
            import re
            param_section = re.split(r'\s*Args:\s*', docstring)
            logging.debug(f"Param section split: {param_section}")
            if len(param_section) > 1:
                param_lines = param_section[1].split('\n')
                for line in param_lines:
                    line = line.strip()
                    if line and ':' in line:
                        param_name, param_desc = line.split(':', 1)
                        param_descriptions[param_name.strip()] = param_desc.strip()
        
        logging.debug(f"Parameter descriptions: {param_descriptions}")

        for name, param in parameters_list:
            param_type = "string"  # Default type
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == list:
                    param_type = "array"
                elif param.annotation == dict:
                    param_type = "object"
            
            parameters["properties"][name] = {
                "type": param_type,
                "description": param_descriptions.get(name, "Parameter description not available")
            }
            
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(name)
        
        logging.debug(f"Generated parameters: {parameters}")
        tool_def = {
            "type": "function",
            "function": {
                "name": function_name,
                "description": docstring.split('\n\n')[0] if docstring else "No description available",
                "parameters": self._fix_array_schemas(parameters)
            }
        }
        logging.debug(f"Generated tool definition: {tool_def}")
        return tool_def