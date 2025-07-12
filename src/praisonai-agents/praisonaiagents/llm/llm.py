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
                if tools and hasattr(tools, '__iter__') and not isinstance(tools, str):
                    safe_config['tools'] = [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools]
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
        
        # Handle system prompt
        if system_prompt:
            # Append JSON schema if needed
            if output_json:
                system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_json.model_json_schema())}"
            elif output_pydantic:
                system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_pydantic.model_json_schema())}"
            
            # Skip system messages for legacy o1 models as they don't support them
            if not self._needs_system_message_skip():
                messages.append({"role": "system", "content": system_prompt})
        
        # Add chat history if provided
        if chat_history:
            messages.extend(chat_history)
        
        # Handle prompt modifications for JSON output
        original_prompt = prompt
        if output_json or output_pydantic:
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

    def _format_tools_for_litellm(self, tools: Optional[List[Any]]) -> Optional[List[Dict]]:
        """Format tools for LiteLLM - handles all tool formats.
        
        Supports:
        - Pre-formatted OpenAI tools (dicts with type='function')
        - Lists of pre-formatted tools
        - Callable functions
        - String function names
        
        Args:
            tools: List of tools in various formats
            
        Returns:
            List of formatted tools or None
        """
        if not tools:
            return None
            
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
                
        return formatted_tools if formatted_tools else None

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

            # Display initial instruction once
            if verbose:
                display_text = prompt
                if isinstance(prompt, list):
                    display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                
                if display_text and str(display_text).strip():
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
            stored_reasoning_content = None  # Store reasoning content from tool execution

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
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
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
                        # Determine if we should use streaming based on tool support
                        use_streaming = stream
                        if formatted_tools and not self._supports_streaming_tools():
                            # Provider doesn't support streaming with tools, use non-streaming
                            use_streaming = False
                        
                        if use_streaming:
                            # Streaming approach (with or without tools)
                            tool_calls = []
                            response_text = ""
                            
                            if verbose:
                                with Live(display_generating("", current_time), console=console, refresh_per_second=4) as live:
                                    for chunk in litellm.completion(
                                        **self._build_completion_params(
                                            messages=messages,
                                            tools=formatted_tools,
                                            temperature=temperature,
                                            stream=True,
                                            **kwargs
                                        )
                                    ):
                                        if chunk and chunk.choices and chunk.choices[0].delta:
                                            delta = chunk.choices[0].delta
                                            response_text, tool_calls = self._process_stream_delta(
                                                delta, response_text, tool_calls, formatted_tools
                                            )
                                            if delta.content:
                                                live.update(display_generating(response_text, current_time))

                            else:
                                # Non-verbose streaming
                                for chunk in litellm.completion(
                                    **self._build_completion_params(
                                        messages=messages,
                                        tools=formatted_tools,
                                        temperature=temperature,
                                        stream=True,
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
                            
                            response_text = response_text.strip()
                            
                            # Create a mock final_response with the captured data
                            final_response = {
                                "choices": [{
                                    "message": {
                                        "content": response_text,
                                        "tool_calls": tool_calls if tool_calls else None
                                    }
                                }]
                            }
                        else:
                            # Non-streaming approach (when tools require it or streaming is disabled)
                            final_response = litellm.completion(
                                **self._build_completion_params(
                                    messages=messages,
                                    tools=formatted_tools,
                                    temperature=temperature,
                                    stream=False,
                                    **kwargs
                                )
                            )
                            response_text = final_response["choices"][0]["message"]["content"]
                            
                            if verbose:
                                # Display the complete response at once
                                display_interaction(
                                    original_prompt,
                                    response_text,
                                    markdown=markdown,
                                    generation_time=time.time() - current_time,
                                    console=console
                                )
                    
                    tool_calls = final_response["choices"][0]["message"].get("tool_calls")
                    
                    # Handle tool calls - Sequential tool calling logic
                    if tool_calls and execute_tool_fn:
                        # Convert tool_calls to a serializable format for all providers
                        serializable_tool_calls = self._serialize_tool_calls(tool_calls)
                        messages.append({
                            "role": "assistant",
                            "content": response_text,
                            "tool_calls": serializable_tool_calls
                        })
                        
                        should_continue = False
                        tool_results = []  # Store all tool results
                        for tool_call in tool_calls:
                            # Handle both object and dict access patterns
                            is_ollama = self._is_ollama_provider()
                            function_name, arguments, tool_call_id = self._extract_tool_call_info(tool_call, is_ollama)

                            logging.debug(f"[TOOL_EXEC_DEBUG] About to execute tool {function_name} with args: {arguments}")
                            tool_result = execute_tool_fn(function_name, arguments)
                            logging.debug(f"[TOOL_EXEC_DEBUG] Tool execution result: {tool_result}")
                            tool_results.append(tool_result)  # Store the result

                            if verbose:
                                display_message = f"Agent {agent_name} called function '{function_name}' with arguments: {arguments}\n"
                                if tool_result:
                                    display_message += f"Function returned: {tool_result}"
                                    logging.debug(f"[TOOL_EXEC_DEBUG] Display message with result: {display_message}")
                                else:
                                    display_message += "Function returned no output"
                                    logging.debug("[TOOL_EXEC_DEBUG] Tool returned no output")
                                
                                logging.debug(f"[TOOL_EXEC_DEBUG] About to display tool call with message: {display_message}")
                                display_tool_call(display_message, console=console)
                                
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

                        # Special handling for Ollama models that don't automatically process tool results
                        ollama_handled = False
                        ollama_params = self._handle_ollama_model(response_text, tool_results, messages, original_prompt)
                        
                        if ollama_params:
                            # Get response based on streaming mode
                            if stream:
                                # Streaming approach
                                if verbose:
                                    with Live(display_generating("", start_time), console=console, refresh_per_second=4) as live:
                                        response_text = ""
                                        for chunk in litellm.completion(
                                            **self._build_completion_params(
                                                messages=ollama_params["follow_up_messages"],
                                                temperature=temperature,
                                                stream=True
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
                                            messages=ollama_params["follow_up_messages"],
                                            temperature=temperature,
                                            stream=True
                                        )
                                    ):
                                        if chunk and chunk.choices and chunk.choices[0].delta.content:
                                            response_text += chunk.choices[0].delta.content
                            else:
                                # Non-streaming approach
                                resp = litellm.completion(
                                    **self._build_completion_params(
                                        messages=ollama_params["follow_up_messages"],
                                        temperature=temperature,
                                        stream=False
                                    )
                                )
                                response_text = resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                            
                            # Set flag to indicate Ollama was handled
                            ollama_handled = True
                            final_response_text = response_text.strip()
                            logging.debug(f"[OLLAMA_DEBUG] Ollama follow-up response: {final_response_text[:200]}...")
                            
                            # Display the response if we got one
                            if final_response_text and verbose:
                                display_interaction(
                                    ollama_params["original_prompt"],
                                    final_response_text,
                                    markdown=markdown,
                                    generation_time=time.time() - start_time,
                                    console=console
                                )
                            
                            # Update messages and continue the loop instead of returning
                            if final_response_text:
                                # Update messages with the response to maintain conversation context
                                messages.append({
                                    "role": "assistant",
                                    "content": final_response_text
                                })
                                # Continue the loop to check if more tools are needed
                                iteration_count += 1
                                continue
                            else:
                                logging.warning("[OLLAMA_DEBUG] Ollama follow-up returned empty response")
                        
                        # Handle reasoning_steps after tool execution if not already handled by Ollama
                        if reasoning_steps and not ollama_handled:
                            # Make a non-streaming call to capture reasoning content
                            reasoning_resp = litellm.completion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=False,  # force non-streaming
                                    **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                                )
                            )
                            reasoning_content = reasoning_resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                            response_text = reasoning_resp["choices"][0]["message"]["content"]
                            
                            # Store reasoning content for later use
                            if reasoning_content:
                                stored_reasoning_content = reasoning_content
                            
                            # Update messages with the response
                            messages.append({
                                "role": "assistant",
                                "content": response_text
                            })
                        
                        # After tool execution, continue the loop to check if more tools are needed
                        # instead of immediately trying to get a final response
                        iteration_count += 1
                        continue
                    else:
                        # No tool calls, we're done with this iteration
                        # If we've executed tools in previous iterations, this response contains the final answer
                        if iteration_count > 0:
                            final_response_text = response_text.strip()
                        break
                        
                except Exception as e:
                    logging.error(f"Error in LLM iteration {iteration_count}: {e}")
                    break
                    
            # End of while loop - return final response
            if final_response_text:
                return final_response_text
            
            # No tool calls were made in this iteration, return the response
            if verbose:
                # If we have stored reasoning content from tool execution, display it
                if stored_reasoning_content:
                    display_interaction(
                        original_prompt,
                        f"Reasoning:\n{stored_reasoning_content}\n\nAnswer:\n{response_text}",
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        console=console
                    )
                else:
                    display_interaction(
                        original_prompt,
                        response_text,
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        console=console
                    )
            
            response_text = response_text.strip()
            
            # Return reasoning content if reasoning_steps is True and we have it
            if reasoning_steps and stored_reasoning_content:
                return stored_reasoning_content
            
            # Handle output formatting
            if output_json or output_pydantic:
                self.chat_history.append({"role": "user", "content": original_prompt})
                self.chat_history.append({"role": "assistant", "content": response_text})
                if verbose:
                    display_interaction(original_prompt, response_text, markdown=markdown,
                                     generation_time=time.time() - start_time, console=console)
                return response_text

            if not self_reflect:
                if verbose:
                    display_interaction(original_prompt, response_text, markdown=markdown,
                                     generation_time=time.time() - start_time, console=console)
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
                            console=console
                        )
                    elif verbose:
                        display_interaction(
                            "Self-reflection (non-streaming):",
                            reflection_text,
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=console
                        )
                else:
                    # Existing streaming approach
                    if verbose:
                        with Live(display_generating("", start_time), console=console, refresh_per_second=4) as live:
                            reflection_text = ""
                            for chunk in litellm.completion(
                                **self._build_completion_params(
                                    messages=reflection_messages,
                                    temperature=temperature,
                                    stream=stream,
                                    response_format={"type": "json_object"},
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
                            console=console
                        )

                    if satisfactory and reflection_count >= min_reflect - 1:
                        if verbose:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=console)
                        return response_text

                    if reflection_count >= max_reflect - 1:
                        if verbose:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=console)
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
                        with Live(display_generating("", time.time()), console=console, refresh_per_second=4) as live:
                            response_text = ""
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
                                    live.update(display_generating(response_text, time.time()))
                    else:
                        response_text = ""
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
                    
                    response_text = response_text.strip()
                    continue

                except json.JSONDecodeError:
                    reflection_count += 1
                    if reflection_count >= max_reflect:
                        if verbose:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=console)
                        return response_text
                    continue
                except Exception as e:
                    display_error(f"Error in LLM response: {str(e)}")
                    return None
            
            # If we've exhausted reflection attempts
            if verbose:
                display_interaction(prompt, response_text, markdown=markdown,
                                 generation_time=time.time() - start_time, console=console)
            return response_text

        except Exception as error:
            display_error(f"Error in get_response: {str(error)}")
            raise
        
        # Log completion time if in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            total_time = time.time() - start_time
            logging.debug(f"get_response completed in {total_time:.2f} seconds")

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

            # Format tools for LiteLLM using the shared helper
            formatted_tools = self._format_tools_for_litellm(tools)

            # Initialize variables for iteration loop
            max_iterations = 10  # Prevent infinite loops
            iteration_count = 0
            final_response_text = ""
            stored_reasoning_content = None  # Store reasoning content from tool execution

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
                        **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                    )
                    )
                    reasoning_content = resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                    response_text = resp["choices"][0]["message"]["content"]
                    
                    if verbose and reasoning_content:
                        display_interaction(
                            "Initial reasoning:",
                            f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}",
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=console
                        )
                    elif verbose:
                        display_interaction(
                            "Initial response:",
                            response_text,
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=console
                        )
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
                        
                        response_text = response_text.strip()
                        
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
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                            )
                        )
                        response_text = tool_response.choices[0].message.get("content", "")
                        tool_calls = tool_response.choices[0].message.get("tool_calls", [])
                        
                        if verbose:
                            # Display the complete response at once
                            display_interaction(
                                original_prompt,
                                response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )

                # Now handle tools if we have them (either from streaming or non-streaming)
                if tools and execute_tool_fn and tool_calls:
                    # Convert tool_calls to a serializable format for all providers
                    serializable_tool_calls = self._serialize_tool_calls(tool_calls)
                    messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "tool_calls": serializable_tool_calls
                    })
                    
                    tool_results = []  # Store all tool results
                    for tool_call in tool_calls:
                        # Handle both object and dict access patterns
                        is_ollama = self._is_ollama_provider()
                        function_name, arguments, tool_call_id = self._extract_tool_call_info(tool_call, is_ollama)

                        tool_result = await execute_tool_fn(function_name, arguments)
                        tool_results.append(tool_result)  # Store the result

                        if verbose:
                            display_message = f"Agent {agent_name} called function '{function_name}' with arguments: {arguments}\n"
                            if tool_result:
                                display_message += f"Function returned: {tool_result}"
                            else:
                                display_message += "Function returned no output"
                            display_tool_call(display_message, console=console)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(tool_result) if tool_result is not None else "Function returned an empty output"
                        })

                    # Get response after tool calls
                    response_text = ""
                    
                    # Special handling for Ollama models that don't automatically process tool results
                    ollama_handled = False
                    ollama_params = self._handle_ollama_model(response_text, tool_results, messages, original_prompt)
                    
                    if ollama_params:
                        # Get response with streaming
                        if verbose:
                            response_text = ""
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=ollama_params["follow_up_messages"],
                                    temperature=temperature,
                                    stream=stream
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    content = chunk.choices[0].delta.content
                                    response_text += content
                                    print("\033[K", end="\r")
                                    print(f"Processing results... {time.time() - start_time:.1f}s", end="\r")
                        else:
                            response_text = ""
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=ollama_params["follow_up_messages"],
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
                                ollama_params["original_prompt"],
                                final_response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )
                        
                        # Store the response for potential final return
                        if final_response_text:
                            # Update messages with the response to maintain conversation context
                            messages.append({
                                "role": "assistant",
                                "content": final_response_text
                            })
                            # Continue the loop to check if more tools are needed
                            iteration_count += 1
                            continue
                        else:
                            logging.warning("[OLLAMA_DEBUG] Ollama follow-up returned empty response")
                    
                    # If no special handling was needed or if it's not an Ollama model
                    if reasoning_steps and not ollama_handled:
                        # Non-streaming call to capture reasoning
                        resp = await litellm.acompletion(
                            **self._build_completion_params(
                                messages=messages,
                                temperature=temperature,
                                stream=False,  # force non-streaming
                                tools=formatted_tools,  # Include tools
                                **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                            )
                        )
                        reasoning_content = resp["choices"][0]["message"].get("provider_specific_fields", {}).get("reasoning_content")
                        response_text = resp["choices"][0]["message"]["content"]
                        
                        if verbose and reasoning_content:
                            display_interaction(
                                "Tool response reasoning:",
                                f"Reasoning:\n{reasoning_content}\n\nAnswer:\n{response_text}",
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )
                        elif verbose:
                            display_interaction(
                                "Tool response:",
                                response_text,
                                markdown=markdown,
                                generation_time=time.time() - start_time,
                                console=console
                            )
                    elif not ollama_handled:
                        # Get response after tool calls with streaming if not already handled
                        if verbose:
                            async for chunk in await litellm.acompletion(
                                **self._build_completion_params(
                                    messages=messages,
                                    temperature=temperature,
                                    stream=stream,
                                    tools=formatted_tools,
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
                                    **{k:v for k,v in kwargs.items() if k != 'reasoning_steps'}
                                )
                            ):
                                if chunk and chunk.choices and chunk.choices[0].delta.content:
                                    response_text += chunk.choices[0].delta.content

                    response_text = response_text.strip()
                    
                    # After tool execution, update messages and continue the loop
                    if response_text:
                        messages.append({
                            "role": "assistant",
                            "content": response_text
                        })
                    
                    # Store reasoning content if captured
                    if reasoning_steps and reasoning_content:
                        stored_reasoning_content = reasoning_content
                    
                    # Continue the loop to check if more tools are needed
                    iteration_count += 1
                    continue
                else:
                    # No tool calls, we're done with this iteration
                    # If we've executed tools in previous iterations, this response contains the final answer
                    if iteration_count > 0:
                        final_response_text = response_text.strip()
                    break

            # Handle output formatting
            if output_json or output_pydantic:
                self.chat_history.append({"role": "user", "content": original_prompt})
                self.chat_history.append({"role": "assistant", "content": response_text})
                if verbose:
                    display_interaction(original_prompt, response_text, markdown=markdown,
                                     generation_time=time.time() - start_time, console=console)
                return response_text

            if not self_reflect:
                # Use final_response_text if we went through tool iterations
                display_text = final_response_text if final_response_text else response_text
                
                # Display with stored reasoning content if available
                if verbose:
                    if stored_reasoning_content:
                        display_interaction(
                            original_prompt,
                            f"Reasoning:\n{stored_reasoning_content}\n\nAnswer:\n{display_text}",
                            markdown=markdown,
                            generation_time=time.time() - start_time,
                            console=console
                        )
                    else:
                        display_interaction(original_prompt, display_text, markdown=markdown,
                                         generation_time=time.time() - start_time, console=console)
                
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
                        console=console
                    )
                elif verbose:
                    display_interaction(
                        "Self-reflection (non-streaming):",
                        reflection_text,
                        markdown=markdown,
                        generation_time=time.time() - start_time,
                        console=console
                    )
            else:
                # Existing streaming approach
                if verbose:
                    with Live(display_generating("", start_time), console=console, refresh_per_second=4) as live:
                        reflection_text = ""
                        async for chunk in await litellm.acompletion(
                            **self._build_completion_params(
                                messages=reflection_messages,
                                temperature=temperature,
                                stream=stream,
                                response_format={"type": "json_object"},
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
                            console=console
                        )

                    if satisfactory and reflection_count >= min_reflect - 1:
                        if verbose:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=console)
                        return response_text

                    if reflection_count >= max_reflect - 1:
                        if verbose:
                            display_interaction(prompt, response_text, markdown=markdown,
                                             generation_time=time.time() - start_time, console=console)
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

    def _handle_ollama_model(self, response_text: str, tool_results: List[Any], messages: List[Dict], original_prompt: Union[str, List[Dict]]) -> Optional[Dict[str, Any]]:
        """
        Handle special Ollama model requirements when processing tool results.
        
        Args:
            response_text: The initial response text from the model
            tool_results: List of tool execution results
            messages: The conversation messages list
            original_prompt: The original user prompt
            
        Returns:
            Dict with follow-up parameters if Ollama needs special handling, None otherwise
        """
        if not self._is_ollama_provider() or not tool_results:
            return None
            
        # Check if the response is just a JSON tool call
        try:
            json_response = json.loads(response_text.strip())
            if not (('name' in json_response or 'function' in json_response) and 
                    not any(word in response_text.lower() for word in ['summary', 'option', 'result', 'found'])):
                return None
                
            logging.debug("Detected Ollama returning only tool call JSON, preparing follow-up call to process results")
            
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
            
            # Return parameters for follow-up call
            return {
                "follow_up_messages": [{"role": "user", "content": follow_up_prompt}],
                "original_prompt": original_prompt
            }
            
        except (json.JSONDecodeError, KeyError):
            # Not a JSON response or not a tool call format
            return None

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
        
        # Add tool_choice="auto" when tools are provided (unless already specified)
        if 'tools' in params and params['tools'] and 'tool_choice' not in params:
            # For Gemini models, use tool_choice to encourage tool usage
            # More comprehensive Gemini model detection
            if any(prefix in self.model.lower() for prefix in ['gemini', 'gemini/', 'google/gemini']):
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
                if verbose:
                    with Live(display_generating("", start_time), console=console or self.console, refresh_per_second=4) as live:
                        for chunk in litellm.completion(**completion_params):
                            content = self._process_streaming_chunk(chunk)
                            if content:
                                response_text += content
                                live.update(display_generating(response_text, start_time))
                else:
                    for chunk in litellm.completion(**completion_params):
                        content = self._process_streaming_chunk(chunk)
                        if content:
                            response_text += content
            else:
                response = litellm.completion(**completion_params)
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
                if verbose:
                    with Live(display_generating("", start_time), console=console or self.console, refresh_per_second=4) as live:
                        async for chunk in await litellm.acompletion(**completion_params):
                            content = self._process_streaming_chunk(chunk)
                            if content:
                                response_text += content
                                live.update(display_generating(response_text, start_time))
                else:
                    async for chunk in await litellm.acompletion(**completion_params):
                        content = self._process_streaming_chunk(chunk)
                        if content:
                            response_text += content
            else:
                response = await litellm.acompletion(**completion_params)
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