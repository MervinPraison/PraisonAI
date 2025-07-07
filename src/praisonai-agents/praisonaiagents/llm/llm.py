import logging
import os
import warnings
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
)
from rich.console import Console
from rich.live import Live

# Disable litellm telemetry before any imports
os.environ["LITELLM_TELEMETRY"] = "False"

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
    
    # Default window sizes for different models (75% of actual to be safe)
    MODEL_WINDOWS = {
        # OpenAI
        "gpt-4": 6144,                    # 8,192 actual
        "gpt-4-turbo": 96000,             # 128,000 actual
        "gpt-4-32k": 24576,               # 32,768 actual
        "gpt-3.5-turbo": 3072,            # 4,096 actual
        "gpt-4o": 96000,                  # 128,000 actual
        "gpt-4o-mini": 96000,             # 128,000 actual
        # Anthropic
        "claude-3-opus-20240229": 150000,  # 200,000 actual
        "claude-3-sonnet-20240229": 150000,
        "claude-3-haiku-20240307": 150000,
        "claude-2.1": 150000,
        "claude-2": 75000,
        "claude-instant-1.2": 75000,
        # Google
        "gemini-pro": 24576,              # 32,760 actual
        # Mistral
        "mistral-tiny": 6144,             # 8,192 actual
        "mistral-small": 6144,
        "mistral-medium": 6144,
        "mistral-large": 24576,           # 32,768 actual
    }
    
    # Valid OpenAI parameters
    OPENAI_VALID_PARAMS = {
        "model", "messages", "temperature", "top_p", "n", "stream", "stop",
        "max_tokens", "presence_penalty", "frequency_penalty", "logit_bias",
        "user", "response_format", "seed", "tools", "tool_choice", "logprobs",
        "top_logprobs", "timeout", "api_key", "base_url"
    }
    
    # PraisonAI-specific parameters that should be filtered out
    PRAISONAI_PARAMS = {
        "markdown", "max_reflect", "min_reflect", "reasoning_steps", "self_reflect",
        "verbose", "console", "agent_name", "agent_role", "agent_tools"
    }

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        top_p: Optional[float] = None,
        n: Optional[int] = None,
        timeout: Optional[Union[float, int]] = None,
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
        try:
            import litellm
            # Disable telemetry
            litellm.telemetry = False
            
            # Set litellm options globally
            litellm.set_verbose = False
            litellm.success_callback = []
            litellm._async_success_callback = []
            litellm.callbacks = []
            
            verbose = extra_settings.get('verbose', True)
            
            # Only suppress logs if not in debug mode
            if not isinstance(verbose, bool) and verbose >= 10:
                # Enable detailed debug logging
                logging.getLogger("asyncio").setLevel(logging.DEBUG)
                logging.getLogger("selector_events").setLevel(logging.DEBUG)
                logging.getLogger("litellm.utils").setLevel(logging.DEBUG)
                logging.getLogger("litellm.main").setLevel(logging.DEBUG)
                litellm.suppress_debug_messages = False
                litellm.set_verbose = True
            else:
                # Suppress debug logging for normal operation
                logging.getLogger("asyncio").setLevel(logging.WARNING)
                logging.getLogger("selector_events").setLevel(logging.WARNING)
                logging.getLogger("litellm.utils").setLevel(logging.WARNING)
                logging.getLogger("litellm.main").setLevel(logging.WARNING)
                litellm.suppress_debug_messages = True
                litellm._logging._disable_debugging()
                warnings.filterwarnings("ignore", category=RuntimeWarning)
            
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
        self.console = Console()
        self.chat_history = []
        self.verbose = verbose
        self.markdown = extra_settings.get('markdown', True)
        self.self_reflect = extra_settings.get('self_reflect', False)
        self.max_reflect = extra_settings.get('max_reflect', 3)
        self.min_reflect = extra_settings.get('min_reflect', 1)
        self.reasoning_steps = extra_settings.get('reasoning_steps', False)
        
        # Enable error dropping for cleaner output
        litellm.drop_params = True
        # Enable parameter modification for providers like Anthropic
        litellm.modify_params = True
        self._setup_event_tracking(events)
        
        # Log all initialization parameters when in debug mode
        if not isinstance(verbose, bool) and verbose >= 10:
            debug_info = {
                "model": self.model,
                "timeout": self.timeout,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "n": self.n,
                "max_tokens": self.max_tokens,
                "presence_penalty": self.presence_penalty,
                "frequency_penalty": self.frequency_penalty,
                "logit_bias": self.logit_bias,
                "response_format": self.response_format,
                "seed": self.seed,
                "logprobs": self.logprobs,
                "top_logprobs": self.top_logprobs,
                "api_version": self.api_version,
                "stop_phrases": self.stop_phrases,
                "api_key": "***" if self.api_key else None,  # Mask API key for security
                "base_url": self.base_url,
                "verbose": self.verbose,
                "markdown": self.markdown,
                "self_reflect": self.self_reflect,
                "max_reflect": self.max_reflect,
                "min_reflect": self.min_reflect,
                "reasoning_steps": self.reasoning_steps,
                "extra_settings": {k: v for k, v in self.extra_settings.items() if k not in ["api_key"]}
            }
            logging.debug(f"LLM instance initialized with: {json.dumps(debug_info, indent=2, default=str)}")

    def _build_completion_params(self, **kwargs) -> Dict[str, Any]:
        """
        Build parameters for completion call, filtering out PraisonAI-specific parameters
        that aren't recognized by the underlying LLM providers.
        """
        # Start with instance defaults
        params = {
            "model": self.model,
            "timeout": self.timeout,
            "api_key": self.api_key,
            "base_url": self.base_url,
        }
        
        # Add optional instance parameters if set
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.n is not None:
            params["n"] = self.n
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        if self.presence_penalty is not None:
            params["presence_penalty"] = self.presence_penalty
        if self.frequency_penalty is not None:
            params["frequency_penalty"] = self.frequency_penalty
        if self.logit_bias is not None:
            params["logit_bias"] = self.logit_bias
        if self.response_format is not None:
            params["response_format"] = self.response_format
        if self.seed is not None:
            params["seed"] = self.seed
        if self.logprobs is not None:
            params["logprobs"] = self.logprobs
        if self.top_logprobs is not None:
            params["top_logprobs"] = self.top_logprobs
        if self.stop_phrases is not None:
            params["stop"] = self.stop_phrases
            
        # Override with any provided kwargs
        for key, value in kwargs.items():
            # Filter out PraisonAI-specific parameters
            if key not in self.PRAISONAI_PARAMS:
                params[key] = value
                
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        
        return params

    def _is_ollama_provider(self) -> bool:
        """Detect if this is an Ollama provider regardless of naming convention"""
        if not self.model:
            return False
        
        # Direct ollama/ prefix
        if self.model.startswith("ollama/"):
            return True
            
        # Check environment variables for Ollama base URL
        base_url = os.getenv("OPENAI_BASE_URL", "")
        api_base = os.getenv("OPENAI_API_BASE", "")
        
        # Common Ollama endpoints
        ollama_endpoints = ["localhost:11434", "127.0.0.1:11434", ":11434"]
        
        return any(endpoint in base_url or endpoint in api_base for endpoint in ollama_endpoints)

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
                
                tool_call_id = tool_call.get("id", f"call_{hash(json.dumps(tool_call))}")
                
            else:
                # Standard format (OpenAI, Anthropic, etc.)
                function_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])
                tool_call_id = tool_call["id"]
                
            return function_name, arguments, tool_call_id
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logging.error(f"Error parsing tool call: {str(e)}")
            logging.error(f"Tool call structure: {json.dumps(tool_call, indent=2)}")
            
            # Try to extract what we can
            function_name = "unknown_function"
            if isinstance(tool_call, dict):
                if "function" in tool_call and isinstance(tool_call["function"], dict):
                    function_name = tool_call["function"].get("name", function_name)
                elif "name" in tool_call:
                    function_name = tool_call.get("name", function_name)
                    
            return function_name, {}, tool_call.get("id", f"error_{hash(str(tool_call))}")
            
    def _needs_system_message_skip(self) -> bool:
        """Check if system messages should be skipped for this model"""
        return self.model and (
            self.model.startswith("o1") or 
            self.model in ["gpt-4o", "gpt-4o-mini"]
        )

    def _setup_event_tracking(self, events: List[Any]):
        """Set up event tracking for the LLM instance"""
        self._event_handlers = {}
        for event in events:
            if hasattr(event, 'on') and hasattr(event, 'name'):
                if event.name not in self._event_handlers:
                    self._event_handlers[event.name] = []
                self._event_handlers[event.name].append(event.on)

    def _emit_event(self, event_name: str, data: Any):
        """Emit an event to all registered handlers"""
        if event_name in self._event_handlers:
            for handler in self._event_handlers[event_name]:
                try:
                    handler(data)
                except Exception as e:
                    logging.error(f"Error in event handler for {event_name}: {str(e)}")

    def response(
        self,
        prompt: Union[str, List[Dict]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream: bool = True,
        verbose: bool = True,
        markdown: bool = True,
        console: Optional[Console] = None,
        **kwargs
    ) -> str:
        """
        Get a response from the LLM without tool calling capabilities.
        
        Args:
            prompt: The user prompt (str or list of dicts for multimodal)
            system_prompt: Optional system prompt
            temperature: Temperature for generation
            stream: Whether to stream the response
            verbose: Whether to display output
            markdown: Whether to use markdown formatting
            console: Rich console instance
            **kwargs: Additional parameters passed to the LLM
            
        Returns:
            str: The LLM response
        """
        try:
            import litellm
            import logging
            logger = logging.getLogger(__name__)
            
            litellm.set_verbose = False
            start_time = time.time()
            
            logger.debug("Using synchronous response function")
            
            # Log all self values when in debug mode
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
                logger.debug(f"Response method configuration: {json.dumps(debug_info, indent=2, default=str)}")
            
            # Build messages list
            messages = []
            if system_prompt:
                # Skip system messages for legacy o1 models as they don't support them
                if not self._needs_system_message_skip():
                    messages.append({"role": "system", "content": system_prompt})
            
            # Add prompt to messages
            if isinstance(prompt, list):
                messages.append({"role": "user", "content": prompt})
            else:
                messages.append({"role": "user", "content": prompt})

            # Get response from LiteLLM
            if stream:
                response_text = ""
                if verbose:
                    with Live(display_generating("", start_time), console=console or self.console, refresh_per_second=4) as live:
                        for chunk in litellm.completion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=True,
                                **kwargs
                            )
                        ):
                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                response_text += content
                                live.update(display_generating(response_text, start_time))
                else:
                    for chunk in litellm.completion(
                        **self._build_completion_params(
                            messages=messages,
                            temperature=temperature,
                            stream=True,
                            **kwargs
                        )
                    ):
                        if chunk and chunk.choices and chunk.choices[0].delta.content:
                            response_text += chunk.choices[0].delta.content
            else:
                response = litellm.completion(
                    **self._build_completion_params(
                        messages=messages,
                        temperature=temperature,
                        stream=False,
                        **kwargs
                    )
                )
                response_text = response.choices[0].message.content.strip()

            if verbose:
                display_interaction(
                    prompt if isinstance(prompt, str) else prompt[0].get("text", ""),
                    response_text,
                    markdown=markdown,
                    generation_time=time.time() - start_time,
                    console=console or self.console
                )
            
            return response_text.strip()

        except Exception as error:
            display_error(f"Error in response: {str(error)}")
            raise

    # TODO: add max_retry and fix get_response to be cleaner
    def get_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True,
        temperature: float = 0.2,
        verbose: bool = True,
        markdown: bool = True,
        console: Optional[Console] = None,
        **kwargs
    ) -> Union[str, Dict[str, Any]]:
        """
        Get a response from the LLM with tool calling capabilities.
        
        Args:
            messages: List of message dictionaries
            tools: Optional list of tools the LLM can use
            stream: Whether to stream the response
            temperature: Temperature for generation
            verbose: Whether to display output
            markdown: Whether to use markdown formatting
            console: Rich console instance
            **kwargs: Additional parameters passed to the LLM
            
        Returns:
            Either a string response or a dict containing tool calls
        """
        try:
            import litellm
            import logging
            logger = logging.getLogger(__name__)
            
            # Extract agent info from kwargs if provided
            agent_name = kwargs.pop('agent_name', None)
            agent_role = kwargs.pop('agent_role', None)
            agent_tools = kwargs.pop('agent_tools', None)
            
            # Use provided values or instance defaults
            verbose = kwargs.get('verbose', verbose if verbose is not None else self.verbose)
            markdown = kwargs.get('markdown', markdown if markdown is not None else self.markdown)
            console = console or self.console
            
            litellm.set_verbose = False
            start_time = time.time()
            
            # Extract original prompt for display
            original_prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                original_prompt = item.get("text", "")
                                break
                    else:
                        original_prompt = content
                    if original_prompt:
                        break

            # Format tools if provided
            formatted_tools = None
            if tools:
                formatted_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {})
                        }
                    }
                    for tool in tools
                ]

            # Display instruction if agent info is provided
            if verbose and agent_name:
                # Truncate prompt for display
                display_text = original_prompt
                if len(display_text) > 100:
                    display_text = display_text[:97] + "..."
                    
                if hasattr(console, 'print'):
                    console.print()  # Add a line break before instruction
                else:
                    print()  # Fallback if console doesn't have print method
                    
                display_instruction(
                    f"Agent {agent_name} is processing prompt: {display_text}",
                    console=console,
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_tools=agent_tools
                )

            # Sequential tool calling loop - similar to agent.py
            max_iterations = 10  # Prevent infinite loops
            iteration_count = 0
            final_response_text = ""

            while iteration_count < max_iterations:
                try:
                    # Get response from LiteLLM
                    current_time = time.time()

                    # If reasoning_steps is True, do a single non-streaming call
                    if self.reasoning_steps:
                        resp = litellm.completion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=False,  # force non-streaming
                                tools=formatted_tools,
                                **kwargs
                            )
                        )
                        reasoning_content = resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                        response_text = resp["choices"][0]["message"]["content"]
                        final_response = resp
                        
                        # Optionally display reasoning if present
                        if verbose and reasoning_content:
                            display_interaction(
                                original_prompt,
                                f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}",
                                markdown=markdown,
                                generation_time=time.time() - current_time,
                                console=console
                            )
                        else:
                            display_interaction(
                                original_prompt,
                                response_text,
                                markdown=markdown,
                                generation_time=time.time() - current_time,
                                console=console
                            )
                    
                    # Otherwise do the existing streaming approach
                    else:
                        if verbose:
                            with Live(display_generating("", current_time), console=console, refresh_per_second=4) as live:
                                response_text = ""
                                for chunk in litellm.completion(
                                    **self._build_completion_params(
                                        messages=messages,
                                        tools=formatted_tools,
                                        temperature=temperature,
                                        stream=stream,
                                        **kwargs
                                    )
                                ):
                                    if chunk and chunk.choices and chunk.choices[0].delta.content:
                                        content = chunk.choices[0].delta.content
                                        response_text += content
                                        live.update(display_generating(response_text, current_time))
                        else:
                            # Non-verbose mode, just collect the response
                            response_text = ""
                            for chunk in litellm.completion(
                                **self._build_completion_params(
                                    messages=messages,
                                    tools=formatted_tools,
                                    temperature=temperature,
                                    stream=stream,
                                    **kwargs
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    response_text += chunk.choices[0].delta.content

                        response_text = response_text.strip()

                        # Get final completion to check for tool calls
                        final_response = litellm.completion(
                            **self._build_completion_params(
                                messages=messages,
                                tools=formatted_tools,
                                temperature=temperature,
                                stream=False,  # No streaming for tool call check
                                **kwargs
                            )
                        )
                    
                    tool_calls = final_response["choices"][0]["message"].get("tool_calls")
                    
                    # Handle tool calls - Sequential tool calling logic
                    if tool_calls:
                        # Process tool calls
                        tool_results = []
                        is_ollama = self._is_ollama_provider()
                        
                        for tool_call in tool_calls:
                            function_name, arguments, tool_call_id = self._parse_tool_call_arguments(tool_call, is_ollama)
                            
                            # Find the matching tool
                            matching_tool = None
                            for tool in tools:
                                if tool["name"] == function_name:
                                    matching_tool = tool
                                    break
                            
                            if matching_tool and "function" in matching_tool:
                                try:
                                    # Call the tool function
                                    tool_function = matching_tool["function"]
                                    
                                    # Display tool call if verbose
                                    if verbose:
                                        display_tool_call(
                                            function_name=function_name,
                                            arguments=arguments,
                                            console=console
                                        )
                                    
                                    # Execute the function
                                    start_time_tool = time.time()
                                    result = tool_function(**arguments)
                                    execution_time = time.time() - start_time_tool
                                    
                                    # Create tool result message
                                    tool_result = {
                                        "name": function_name,
                                        "output": str(result),
                                        "tool_call_id": tool_call_id,
                                        "execution_time": execution_time
                                    }
                                    tool_results.append(tool_result)
                                    
                                    # Add tool call and result to messages
                                    # First add the assistant's tool call
                                    messages.append({
                                        "role": "assistant",
                                        "content": response_text if response_text else None,
                                        "tool_calls": [tool_call]
                                    })
                                    
                                    # Then add the tool result
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "name": function_name,
                                        "content": str(result)
                                    })
                                    
                                except Exception as e:
                                    error_msg = f"Error executing {function_name}: {str(e)}"
                                    if verbose:
                                        display_error(error_msg, console=console)
                                    
                                    # Add error result
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "name": function_name,
                                        "content": error_msg
                                    })
                            else:
                                # Tool not found
                                error_msg = f"Tool '{function_name}' not found in available tools"
                                if verbose:
                                    display_error(error_msg, console=console)
                                
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "name": function_name,
                                    "content": error_msg
                                })
                        
                        # Continue to next iteration to process tool results
                        should_continue = True
                        
                        # Check if we should continue (only if we got valid tool results)
                        if tool_results:
                            iteration_count += 1
                            # Continue the loop to get the next response
                            continue
                        else:
                            # No valid tool results, treat as final response
                            should_continue = False
                        
                        if should_continue:
                            iteration_count += 1
                            continue

                        # If we reach here, no more tool calls needed - get final response
                        # Make one more call to get the final summary response
                        # Special handling for Ollama models that don't automatically process tool results
                        ollama_handled = False
                        if self.model and self.model.startswith("ollama/") and tool_results:
                            # For Ollama models, we need to explicitly ask the model to process the tool results
                            # First, check if the response is just a JSON tool call
                            try:
                                # If the response_text is a valid JSON that looks like a tool call,
                                # we need to make a follow-up call to process the results
                                json_response = json.loads(response_text.strip())
                                if ('name' in json_response or 'function' in json_response) and not any(word in response_text.lower() for word in ['summary', 'option', 'result', 'found']):
                                    logging.debug("Detected Ollama returning only tool call JSON, making follow-up call to process results")
                                    
                                    # Create a prompt that asks the model to process the tool results based on original context
                                    # Extract the original user query from messages
                                    original_query = ""
                                    for msg in reversed(messages):  # Look from the end to find the most recent user message
                                        if msg.get("role") == "user":
                                            content = msg.get("content", "")
                                            # Handle list content (multimodal)
                                            if isinstance(content, list):
                                                for item in content:
                                                    if isinstance(item, dict) and item.get("type") == "text":
                                                        original_query = item.get("text", "")
                                                        break
                                            else:
                                                original_query = content
                                            if original_query:
                                                break
                                    
                                    # Create a shorter follow-up prompt with all tool results
                                    # If there's only one result, use it directly; otherwise combine them
                                    if len(tool_results) == 1:
                                        results_text = json.dumps(tool_results[0], indent=2)
                                    else:
                                        results_text = json.dumps(tool_results, indent=2)
                                    
                                    follow_up_prompt = f"Results:\n{results_text}\nProvide Answer to this Original Question based on the above results: '{original_query}'"
                                    logging.debug(f"[OLLAMA_DEBUG] Original query extracted: {original_query}")
                                    logging.debug(f"[OLLAMA_DEBUG] Follow-up prompt: {follow_up_prompt[:200]}...")
                                    
                                    # Make a follow-up call to process the results
                                    follow_up_messages = [
                                        {"role": "user", "content": follow_up_prompt}
                                    ]
                                    
                                    # Get response with streaming
                                    if verbose:
                                        with Live(display_generating("", start_time), console=console, refresh_per_second=4) as live:
                                            response_text = ""
                                            for chunk in litellm.completion(
                                                **self._build_completion_params(
                                                    messages=follow_up_messages,
                                                    temperature=temperature,
                                                    stream=stream
                                                )
                                            ):
                                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                                    content = chunk.choices[0].delta.content
                                                    response_text += content
                                                    live.update(display_generating(response_text, start_time))
                                    else:
                                        response_text = ""
                                        for chunk in litellm.completion(
                                            **self._build_completion_params(
                                                messages=follow_up_messages,
                                                temperature=temperature,
                                                stream=stream
                                            )
                                        ):
                                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                                response_text += chunk.choices[0].delta.content
                                    
                                    # Set flag to indicate Ollama was handled
                                    ollama_handled = True
                                    final_response_text = response_text.strip()
                                    logging.debug(f"[OLLAMA_DEBUG] Ollama follow-up response: {final_response_text[:200]}...")
                                    
                                    # Display the response if we got one
                                    if final_response_text and verbose:
                                        display_interaction(
                                            original_prompt,
                                            final_response_text,
                                            markdown=markdown,
                                            generation_time=time.time() - start_time,
                                            console=console
                                        )
                                    
                                    # Return the final response after processing Ollama's follow-up
                                    if final_response_text:
                                        return final_response_text
                                    else:
                                        logging.warning("[OLLAMA_DEBUG] Ollama follow-up returned empty response")
                            except (json.JSONDecodeError, KeyError):
                                # Not a JSON response or not a tool call format, continue normally
                                pass
                        
                        # If Ollama wasn't handled or we're not using Ollama, check if we need final processing
                        if not ollama_handled and tool_results:
                            # We have tool results, make one more call to get final response
                            logging.debug("Making final call to process tool results")
                            
                            # Get final response after tool execution
                            final_resp = litellm.completion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=False,  # No streaming for final response
                                    **kwargs
                                )
                            )
                            
                            final_response_text = final_resp["choices"][0]["message"]["content"]
                            
                            if verbose and final_response_text:
                                display_interaction(
                                    original_prompt,
                                    final_response_text,
                                    markdown=markdown,
                                    generation_time=time.time() - start_time,
                                    console=console
                                )
                            
                            return final_response_text.strip()
                    else:
                        # No tool calls - this is the final response
                        final_response_text = response_text
                        
                        # Display the response if we haven't already
                        if verbose and not self.reasoning_steps:  # reasoning_steps already displayed
                            display_interaction(
                                original_prompt,
                                final_response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )
                        
                        # Break out of the loop
                        break

                except Exception as error:
                    # Handle context length errors
                    if hasattr(error, 'message') and "context" in str(error.message).lower():
                        raise LLMContextLengthExceededException(str(error))
                    
                    display_error(f"Error in LLM iteration {iteration_count}: {str(error)}")
                    logging.error(f"ERROR Error in LLM iteration {iteration_count}: {str(error)}")
                    raise

            # Self-reflection logic
            if self.self_reflect and iteration_count >= self.min_reflect and iteration_count < self.max_reflect:
                logging.debug(f"Starting self-reflection (iteration {iteration_count + 1})")
                
                reflection_prompt = """Please review your response and consider:
1. Is the answer complete and accurate?
2. Does it fully address the user's question?
3. Are there any errors or improvements needed?

If improvements are needed, provide a better response. Otherwise, confirm the response is good.
Format your reflection as JSON: {"needs_improvement": true/false, "reflection": "your thoughts", "improved_response": "better response if needed"}"""
                
                reflection_messages = messages + [
                    {"role": "assistant", "content": response_text},
                    {"role": "user", "content": reflection_prompt}
                ]

                # If reasoning_steps is True, do a single non-streaming call to capture reasoning
                if self.reasoning_steps:
                    reflection_resp = litellm.completion(
                        **self._build_completion_params(
                            messages=reflection_messages,
                            temperature=temperature,
                            stream=False,  # Force non-streaming
                            response_format={"type": "json_object"},
                            **kwargs
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
                            console=console
                        )
                else:
                    # Get reflection with streaming
                    if verbose:
                        with Live(display_generating("", start_time), console=console, refresh_per_second=4) as live:
                            reflection_text = ""
                            for chunk in litellm.completion(
                                **self._build_completion_params(
                                    messages=reflection_messages,
                                    temperature=temperature,
                                    stream=stream,
                                    response_format={"type": "json_object"}
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
                                response_format={"type": "json_object"}
                            )
                        ):
                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                reflection_text += chunk.choices[0].delta.content

                # Parse reflection
                try:
                    reflection_data = json.loads(reflection_text.strip())
                    reflection_output = ReflectionOutput(**reflection_data)
                    
                    if verbose:
                        display_self_reflection(
                            thought=reflection_output.reflection,
                            needs_improvement=reflection_output.needs_improvement,
                            markdown=markdown,
                            console=console
                        )
                    
                    # If improvement needed, use the improved response
                    if reflection_output.needs_improvement and reflection_output.improved_response:
                        final_response_text = reflection_output.improved_response
                        if verbose:
                            display_interaction(
                                "Improved response:",
                                final_response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )
                        
                except json.JSONDecodeError:
                    logging.warning("Failed to parse reflection as JSON")

            return final_response_text.strip()

        except Exception as error:
            display_error(f"Error in get_response: {str(error)}")
            raise

    async def get_response_async(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True,
        temperature: float = 0.2,
        verbose: bool = True,
        markdown: bool = True,
        console: Optional[Console] = None,
        **kwargs
    ) -> Union[str, Dict[str, Any]]:
        """
        Async version of get_response with tool calling capabilities.
        
        Args:
            messages: List of message dictionaries
            tools: Optional list of tools the LLM can use
            stream: Whether to stream the response
            temperature: Temperature for generation
            verbose: Whether to display output
            markdown: Whether to use markdown formatting
            console: Rich console instance
            **kwargs: Additional parameters passed to the LLM
            
        Returns:
            Either a string response or a dict containing tool calls
        """
        try:
            import litellm
            import logging
            logger = logging.getLogger(__name__)
            
            # Extract agent info from kwargs if provided
            agent_name = kwargs.pop('agent_name', None)
            agent_role = kwargs.pop('agent_role', None)
            agent_tools = kwargs.pop('agent_tools', None)
            
            # Use provided values or instance defaults
            verbose = kwargs.get('verbose', verbose if verbose is not None else self.verbose)
            markdown = kwargs.get('markdown', markdown if markdown is not None else self.markdown)
            console = console or self.console
            
            litellm.set_verbose = False
            start_time = time.time()
            
            # Extract original prompt for display
            original_prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                original_prompt = item.get("text", "")
                                break
                    else:
                        original_prompt = content
                    if original_prompt:
                        break

            # Format tools if provided
            formatted_tools = None
            if tools:
                formatted_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {})
                        }
                    }
                    for tool in tools
                ]

            # Display instruction if agent info is provided
            if verbose and agent_name:
                # Truncate prompt for display
                display_text = original_prompt
                if len(display_text) > 100:
                    display_text = display_text[:97] + "..."
                    
                if hasattr(console, 'print'):
                    console.print()  # Add a line break before instruction
                else:
                    print()  # Fallback if console doesn't have print method
                    
                display_instruction(
                    f"Agent {agent_name} is processing prompt: {display_text}",
                    console=console,
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_tools=agent_tools
                )

            # Sequential tool calling loop
            max_iterations = 10
            iteration_count = 0
            final_response_text = ""

            while iteration_count < max_iterations:
                try:
                    # Get response from LiteLLM
                    current_time = time.time()

                    # If reasoning_steps is True, do a single non-streaming call
                    if self.reasoning_steps:
                        resp = await litellm.acompletion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=False,  # force non-streaming
                                tools=formatted_tools,
                                **kwargs
                            )
                        )
                        reasoning_content = resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                        response_text = resp["choices"][0]["message"]["content"]
                        final_response = resp
                        
                        # Optionally display reasoning if present
                        if verbose and reasoning_content:
                            display_interaction(
                                original_prompt,
                                f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}",
                                markdown=markdown,
                                generation_time=time.time() - current_time,
                                console=console
                            )
                        else:
                            display_interaction(
                                original_prompt,
                                response_text,
                                markdown=markdown,
                                generation_time=time.time() - current_time,
                                console=console
                            )
                    
                    # Otherwise do the existing streaming approach
                    else:
                        if verbose:
                            with Live(display_generating("", current_time), console=console, refresh_per_second=4) as live:
                                response_text = ""
                                async for chunk in await litellm.acompletion(
                                    **self._build_completion_params(
                                        messages=messages,
                                        tools=formatted_tools,
                                        temperature=temperature,
                                        stream=stream,
                                        **kwargs
                                    )
                                ):
                                    if chunk and chunk.choices and chunk.choices[0].delta.content:
                                        content = chunk.choices[0].delta.content
                                        response_text += content
                                        live.update(display_generating(response_text, current_time))
                        else:
                            # Non-verbose mode, just collect the response
                            response_text = ""
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=messages,
                                    tools=formatted_tools,
                                    temperature=temperature,
                                    stream=stream,
                                    **kwargs
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    response_text += chunk.choices[0].delta.content

                        response_text = response_text.strip()

                        # Get final completion to check for tool calls
                        final_response = await litellm.acompletion(
                            **self._build_completion_params(
                                messages=messages,
                                tools=formatted_tools,
                                temperature=temperature,
                                stream=False,  # No streaming for tool call check
                                **kwargs
                            )
                        )
                    
                    tool_calls = final_response["choices"][0]["message"].get("tool_calls")
                    
                    # Handle tool calls
                    if tool_calls:
                        # Process tool calls
                        tool_results = []
                        is_ollama = self._is_ollama_provider()
                        
                        for tool_call in tool_calls:
                            function_name, arguments, tool_call_id = self._parse_tool_call_arguments(tool_call, is_ollama)
                            
                            # Find the matching tool
                            matching_tool = None
                            for tool in tools:
                                if tool["name"] == function_name:
                                    matching_tool = tool
                                    break
                            
                            if matching_tool and "function" in matching_tool:
                                try:
                                    # Call the tool function
                                    tool_function = matching_tool["function"]
                                    
                                    # Display tool call if verbose
                                    if verbose:
                                        display_tool_call(
                                            function_name=function_name,
                                            arguments=arguments,
                                            console=console
                                        )
                                    
                                    # Execute the function (handle both sync and async)
                                    start_time_tool = time.time()
                                    import asyncio
                                    if asyncio.iscoroutinefunction(tool_function):
                                        result = await tool_function(**arguments)
                                    else:
                                        result = tool_function(**arguments)
                                    execution_time = time.time() - start_time_tool
                                    
                                    # Create tool result message
                                    tool_result = {
                                        "name": function_name,
                                        "output": str(result),
                                        "tool_call_id": tool_call_id,
                                        "execution_time": execution_time
                                    }
                                    tool_results.append(tool_result)
                                    
                                    # Add tool call and result to messages
                                    messages.append({
                                        "role": "assistant",
                                        "content": response_text if response_text else None,
                                        "tool_calls": [tool_call]
                                    })
                                    
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "name": function_name,
                                        "content": str(result)
                                    })
                                    
                                except Exception as e:
                                    error_msg = f"Error executing {function_name}: {str(e)}"
                                    if verbose:
                                        display_error(error_msg, console=console)
                                    
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "name": function_name,
                                        "content": error_msg
                                    })
                            else:
                                error_msg = f"Tool '{function_name}' not found in available tools"
                                if verbose:
                                    display_error(error_msg, console=console)
                                
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "name": function_name,
                                    "content": error_msg
                                })
                        
                        # Continue to next iteration if we have tool results
                        if tool_results:
                            iteration_count += 1
                            continue
                        
                        # Handle Ollama special case
                        if self.model and self.model.startswith("ollama/") and tool_results:
                            try:
                                json_response = json.loads(response_text.strip())
                                if ('name' in json_response or 'function' in json_response):
                                    # Create follow-up for Ollama
                                    original_query = original_prompt
                                    results_text = json.dumps(tool_results[0] if len(tool_results) == 1 else tool_results, indent=2)
                                    follow_up_prompt = f"Results:\n{results_text}\nProvide Answer to this Original Question based on the above results: '{original_query}'"
                                    
                                    follow_up_messages = [{"role": "user", "content": follow_up_prompt}]
                                    
                                    if verbose:
                                        with Live(display_generating("", start_time), console=console, refresh_per_second=4) as live:
                                            response_text = ""
                                            async for chunk in await litellm.acompletion(
                                                **self._build_completion_params(
                                                    messages=follow_up_messages,
                                                    temperature=temperature,
                                                    stream=stream
                                                )
                                            ):
                                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                                    content = chunk.choices[0].delta.content
                                                    response_text += content
                                                    live.update(display_generating(response_text, start_time))
                                    else:
                                        response_text = ""
                                        async for chunk in await litellm.acompletion(
                                            **self._build_completion_params(
                                                messages=follow_up_messages,
                                                temperature=temperature,
                                                stream=stream
                                            )
                                        ):
                                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                                response_text += chunk.choices[0].delta.content
                                    
                                    final_response_text = response_text.strip()
                                    
                                    if final_response_text and verbose:
                                        display_interaction(
                                            original_prompt,
                                            final_response_text,
                                            markdown=markdown,
                                            generation_time=time.time() - start_time,
                                            console=console
                                        )
                                    
                                    return final_response_text
                            except (json.JSONDecodeError, KeyError):
                                pass
                        
                        # Get final response after tool execution
                        if tool_results:
                            final_resp = await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=False,
                                    **kwargs
                                )
                            )
                            
                            final_response_text = final_resp["choices"][0]["message"]["content"]
                            
                            if verbose and final_response_text:
                                display_interaction(
                                    original_prompt,
                                    final_response_text,
                                    markdown=markdown,
                                    generation_time=time.time() - start_time,
                                    console=console
                                )
                            
                            return final_response_text.strip()
                    else:
                        # No tool calls - this is the final response
                        final_response_text = response_text
                        
                        if verbose and not self.reasoning_steps:
                            display_interaction(
                                original_prompt,
                                final_response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )
                        
                        break

                except Exception as error:
                    if hasattr(error, 'message') and "context" in str(error.message).lower():
                        raise LLMContextLengthExceededException(str(error))
                    
                    display_error(f"Error in async LLM iteration {iteration_count}: {str(error)}")
                    raise

            # Self-reflection logic (async)
            if self.self_reflect and iteration_count >= self.min_reflect and iteration_count < self.max_reflect:
                reflection_prompt = """Please review your response and consider:
1. Is the answer complete and accurate?
2. Does it fully address the user's question?
3. Are there any errors or improvements needed?

If improvements are needed, provide a better response. Otherwise, confirm the response is good.
Format your reflection as JSON: {"needs_improvement": true/false, "reflection": "your thoughts", "improved_response": "better response if needed"}"""
                
                reflection_messages = messages + [
                    {"role": "assistant", "content": response_text},
                    {"role": "user", "content": reflection_prompt}
                ]

                # If reasoning_steps is True, do a single non-streaming call
                if self.reasoning_steps:
                    reflection_resp = await litellm.acompletion(
                        **self._build_completion_params(
                            messages=reflection_messages,
                            temperature=temperature,
                            stream=False,
                            response_format={"type": "json_object"},
                            **kwargs
                        )
                    )
                    reasoning_content = reflection_resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                    reflection_text = reflection_resp["choices"][0]["message"]["content"]

                    if verbose and reasoning_content:
                        display_interaction(
                            "Reflection reasoning:",
                            f"{reasoning_content}\n\nReflection result:\n{reflection_text}",
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=console
                        )
                else:
                    # Get reflection with streaming
                    if verbose:
                        with Live(display_generating("", start_time), console=console, refresh_per_second=4) as live:
                            reflection_text = ""
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=reflection_messages,
                                    temperature=temperature,
                                    stream=stream,
                                    response_format={"type": "json_object"}
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
                                response_format={"type": "json_object"}
                            )
                        ):
                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                reflection_text += chunk.choices[0].delta.content

                # Parse reflection
                try:
                    reflection_data = json.loads(reflection_text.strip())
                    reflection_output = ReflectionOutput(**reflection_data)
                    
                    if verbose:
                        display_self_reflection(
                            thought=reflection_output.reflection,
                            needs_improvement=reflection_output.needs_improvement,
                            markdown=markdown,
                            console=console
                        )
                    
                    if reflection_output.needs_improvement and reflection_output.improved_response:
                        final_response_text = reflection_output.improved_response
                        if verbose:
                            display_interaction(
                                "Improved response:",
                                final_response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )
                        
                except json.JSONDecodeError:
                    logging.warning("Failed to parse async reflection as JSON")

            return final_response_text.strip()

        except Exception as error:
            display_error(f"Error in async get_response: {str(error)}")
            raise

    def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        stream: bool = True,
        verbose: bool = True,
        markdown: bool = True,
        console: Optional[Console] = None,
        **kwargs
    ) -> str:
        """
        Chat with the LLM, maintaining conversation history.
        
        Args:
            message: The user message
            system_prompt: Optional system prompt
            temperature: Temperature for generation
            stream: Whether to stream the response
            verbose: Whether to display output
            markdown: Whether to use markdown formatting
            console: Rich console instance
            **kwargs: Additional parameters passed to the LLM
            
        Returns:
            str: The LLM response
        """
        # Add user message to history
        self.chat_history.append({"role": "user", "content": message})
        
        # Build messages including history
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(self.chat_history)
        
        # Get response
        response = self.response(
            prompt=message,
            system_prompt=system_prompt,
            temperature=temperature,
            stream=stream,
            verbose=verbose,
            markdown=markdown,
            console=console,
            **kwargs
        )
        
        # Add assistant response to history
        self.chat_history.append({"role": "assistant", "content": response})
        
        return response

    def get_context_size(self, model: Optional[str] = None) -> int:
        """
        Get the context window size for a model.
        
        Args:
            model: Model name (uses instance model if not provided)
            
        Returns:
            int: Context window size in tokens
        """
        model = model or self.model
        
        # Check exact match first
        if model in self.MODEL_WINDOWS:
            return self.MODEL_WINDOWS[model]
        
        # Check prefix matches
        for model_prefix, window_size in self.MODEL_WINDOWS.items():
            if model.startswith(model_prefix):
                return window_size
        
        # Try to get from litellm
        try:
            import litellm
            context_size = litellm.get_max_tokens(model)
            if context_size:
                # Return 75% of actual for safety
                return int(context_size * 0.75)
        except:
            pass
        
        # Default fallback
        return 4000

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
                logger.debug(f"Async response method configuration: {json.dumps(debug_info, indent=2, default=str)}")
            
            # Build messages list
            messages = []
            if system_prompt:
                # Skip system messages for legacy o1 models as they don't support them
                if not self._needs_system_message_skip():
                    messages.append({"role": "system", "content": system_prompt})
            
            # Add prompt to messages
            if isinstance(prompt, list):
                messages.append({"role": "user", "content": prompt})
            else:
                messages.append({"role": "user", "content": prompt})

            # Get response from LiteLLM
            if stream:
                response_text = ""
                if verbose:
                    with Live(display_generating("", start_time), console=console or self.console, refresh_per_second=4) as live:
                        async for chunk in await litellm.acompletion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=True,
                                **kwargs
                            )
                        ):
                            if chunk and chunk.choices and chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                response_text += content
                                live.update(display_generating(response_text, start_time))
                else:
                    async for chunk in await litellm.acompletion(
                        **self._build_completion_params(
                            messages=messages,
                            temperature=temperature,
                            stream=True,
                            **kwargs
                        )
                    ):
                        if chunk and chunk.choices and chunk.choices[0].delta.content:
                            response_text += chunk.choices[0].delta.content
            else:
                response = await litellm.acompletion(
                    **self._build_completion_params(
                        messages=messages,
                        temperature=temperature,
                        stream=False,
                        **kwargs
                    )
                )
                response_text = response.choices[0].message.content.strip()

            if verbose:
                display_interaction(
                    prompt if isinstance(prompt, str) else prompt[0].get("text", ""),
                    response_text,
                    markdown=markdown,
                    generation_time=time.time() - start_time,
                    console=console or self.console
                )
            
            return response_text.strip()

        except Exception as error:
            display_error(f"Error in async response: {str(error)}")
            raise

    def can_use_tools(self) -> bool:
        """Check if this model can use tool/function calling"""
        try:
            import litellm
            # Get supported params for this model
            supported_params = litellm.get_supported_openai_params(model=self.model)
            return "tools" in supported_params or "functions" in supported_params
        except:
            # If we can't determine, assume it doesn't support tools
            return False

    def can_use_stop_words(self) -> bool:
        """Check if this model supports stop words/sequences"""
        try:
            import litellm
            # Get supported params for this model
            supported_params = litellm.get_supported_openai_params(model=self.model)
            return "stop" in supported_params
        except:
            # If we can't determine, assume it doesn't support stop words
            return False