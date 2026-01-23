"""
OpenAI Client Module

This module provides a unified interface for OpenAI API interactions,
supporting both synchronous and asynchronous operations.
"""

import os
import logging
import time
import json
import asyncio
from typing import Any, Dict, List, Optional, Union, AsyncIterator, Iterator, Callable, Tuple, TYPE_CHECKING
from pydantic import BaseModel
from dataclasses import dataclass
import inspect

# Lazy imports for optional dependencies
_openai_module = None
_rich_console = None
_rich_live = None

def _get_openai():
    """Lazy import openai module."""
    global _openai_module
    if _openai_module is None:
        try:
            import openai as _openai
            _openai_module = _openai
        except ImportError:
            raise ImportError(
                "openai is required for OpenAI client. "
                "Install with: pip install openai"
            )
    return _openai_module

def _get_openai_classes():
    """Get OpenAI and AsyncOpenAI classes lazily."""
    openai = _get_openai()
    return openai.OpenAI, openai.AsyncOpenAI

def _get_rich_console():
    """Lazy import rich Console."""
    global _rich_console
    if _rich_console is None:
        from rich.console import Console
        _rich_console = Console
    return _rich_console

def _get_rich_live():
    """Lazy import rich Live."""
    global _rich_live
    if _rich_live is None:
        from rich.live import Live
        _rich_live = Live
    return _rich_live


# Import display_tool_call for callback support (lazy import to avoid circular imports)
_display_tool_call = None
def _get_display_tool_call():
    global _display_tool_call
    if _display_tool_call is None:
        from ..main import display_tool_call
        _display_tool_call = display_tool_call
    return _display_tool_call

# Constants
LOCAL_SERVER_API_KEY_PLACEHOLDER = "not-needed"

# Data Classes for OpenAI Response Structure
@dataclass
class ChatCompletionMessage:
    content: str
    role: str = "assistant"
    refusal: Optional[str] = None
    audio: Optional[str] = None
    function_call: Optional[dict] = None
    tool_calls: Optional[List] = None
    reasoning_content: Optional[str] = None

@dataclass
class Choice:
    finish_reason: Optional[str]
    index: int
    message: ChatCompletionMessage
    logprobs: Optional[dict] = None

@dataclass
class CompletionTokensDetails:
    accepted_prediction_tokens: Optional[int] = None
    audio_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    rejected_prediction_tokens: Optional[int] = None

@dataclass
class PromptTokensDetails:
    audio_tokens: Optional[int] = None
    cached_tokens: int = 0

@dataclass
class CompletionUsage:
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    completion_tokens_details: Optional[CompletionTokensDetails] = None
    prompt_tokens_details: Optional[PromptTokensDetails] = None
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0

@dataclass
class ChatCompletion:
    id: str
    choices: List[Choice]
    created: int
    model: str
    object: str = "chat.completion"
    system_fingerprint: Optional[str] = None
    service_tier: Optional[str] = None
    usage: Optional[CompletionUsage] = None

@dataclass
class ToolCall:
    """Tool call representation compatible with OpenAI format"""
    id: str
    type: str
    function: Dict[str, Any]


def process_stream_chunks(chunks):
    """Process streaming chunks into combined response"""
    if not chunks:
        return None
    
    try:
        first_chunk = chunks[0]
        last_chunk = chunks[-1]
        
        # Basic metadata
        id = getattr(first_chunk, "id", None) 
        created = getattr(first_chunk, "created", None)
        model = getattr(first_chunk, "model", None)
        system_fingerprint = getattr(first_chunk, "system_fingerprint", None)
        
        # Track usage
        completion_tokens = 0
        prompt_tokens = 0
        
        content_list = []
        reasoning_list = []
        tool_calls = []
        current_tool_call = None

        # First pass: Get initial tool call data
        for chunk in chunks:
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue
            
            delta = getattr(chunk.choices[0], "delta", None)
            if not delta:
                continue

            # Handle content and reasoning
            if hasattr(delta, "content") and delta.content:
                content_list.append(delta.content)
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                reasoning_list.append(delta.reasoning_content)
            
            # Handle tool calls
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    if tool_call_delta.index is not None and tool_call_delta.id:
                        # Found the initial tool call
                        current_tool_call = {
                            "id": tool_call_delta.id,
                            "type": "function",
                            "function": {
                                "name": tool_call_delta.function.name,
                                "arguments": ""
                            }
                        }
                        while len(tool_calls) <= tool_call_delta.index:
                            tool_calls.append(None)
                        tool_calls[tool_call_delta.index] = current_tool_call
                        current_tool_call = tool_calls[tool_call_delta.index]
                    elif current_tool_call is not None and hasattr(tool_call_delta.function, "arguments"):
                        if tool_call_delta.function.arguments:
                            current_tool_call["function"]["arguments"] += tool_call_delta.function.arguments

        # Remove any None values and empty tool calls
        tool_calls = [tc for tc in tool_calls if tc and tc["id"] and tc["function"]["name"]]

        combined_content = "".join(content_list) if content_list else ""
        combined_reasoning = "".join(reasoning_list) if reasoning_list else None
        finish_reason = getattr(last_chunk.choices[0], "finish_reason", None) if hasattr(last_chunk, "choices") and last_chunk.choices else None

        # Create ToolCall objects
        processed_tool_calls = []
        if tool_calls:
            try:
                for tc in tool_calls:
                    tool_call = ToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function={
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        }
                    )
                    processed_tool_calls.append(tool_call)
            except Exception as e:
                print(f"Error processing tool call: {e}")

        message = ChatCompletionMessage(
            content=combined_content,
            role="assistant",
            reasoning_content=combined_reasoning,
            tool_calls=processed_tool_calls if processed_tool_calls else None
        )
        
        choice = Choice(
            finish_reason=finish_reason or "tool_calls" if processed_tool_calls else None,
            index=0,
            message=message
        )

        usage = CompletionUsage(
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            total_tokens=completion_tokens + prompt_tokens,
            completion_tokens_details=CompletionTokensDetails(),
            prompt_tokens_details=PromptTokensDetails()
        )
        
        return ChatCompletion(
            id=id,
            choices=[choice],
            created=created,
            model=model,
            system_fingerprint=system_fingerprint,
            usage=usage
        )
        
    except Exception as e:
        print(f"Error processing chunks: {e}")
        return None


class OpenAIClient:
    """
    Unified OpenAI client wrapper for sync/async operations.
    
    This class encapsulates all OpenAI-specific logic, providing a clean
    interface for chat completions, streaming, and structured outputs.
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize the OpenAI client with proper API key handling.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Custom base URL for API endpoints (defaults to OPENAI_API_BASE env var)
        """
        # Use provided values or fall back to environment variables
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL")
        
        # For local servers like LM Studio, allow minimal API key
        if self.base_url and not self.api_key:
            self.api_key = LOCAL_SERVER_API_KEY_PLACEHOLDER
        elif not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for the default OpenAI service. "
                "If you are targeting a local server (e.g., LM Studio), ensure OPENAI_API_BASE is set "
                f"(e.g., 'http://localhost:1234/v1') and you can use a placeholder API key by setting OPENAI_API_KEY='{LOCAL_SERVER_API_KEY_PLACEHOLDER}'"
            )
        
        # Initialize clients lazily
        self._sync_client = None
        self._async_client = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        # Initialize console lazily
        self._console = None
        
        # Cache for formatted tools and fixed schemas
        self._formatted_tools_cache = {}
        self._fixed_schema_cache = {}
        self._max_cache_size = 100
    
    @property
    def console(self):
        """Lazily initialize Rich Console only when needed."""
        if self._console is None:
            Console = _get_rich_console()
            self._console = Console()
        return self._console
    
    @property
    def sync_client(self):
        """Get the synchronous OpenAI client (lazy initialization)."""
        if self._sync_client is None:
            OpenAI, _ = _get_openai_classes()
            self._sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._sync_client
    
    @property
    def async_client(self):
        """Get the asynchronous OpenAI client (lazy initialization)."""
        if self._async_client is None:
            _, AsyncOpenAI = _get_openai_classes()
            self._async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._async_client
    
    def build_messages(
        self, 
        prompt: Union[str, List[Dict]], 
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict]] = None,
        output_json: Optional[BaseModel] = None,
        output_pydantic: Optional[BaseModel] = None
    ) -> Tuple[List[Dict], Union[str, List[Dict]]]:
        """
        Build messages list for OpenAI completion.
        
        Args:
            prompt: The user prompt (str or list)
            system_prompt: Optional system prompt
            chat_history: Optional list of previous messages
            output_json: Optional Pydantic model for JSON output
            output_pydantic: Optional Pydantic model for JSON output (alias)
            
        Returns:
            tuple: (messages list, original prompt)
        """
        messages = []
        
        # Handle system prompt
        if system_prompt:
            # Append JSON schema if needed
            if output_json:
                # Handle Pydantic model
                if hasattr(output_json, 'model_json_schema'):
                    system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_json.model_json_schema())}"
                # Handle inline dict schema (Option A from YAML)
                elif isinstance(output_json, dict):
                    system_prompt += f"\nReturn ONLY a JSON object that matches this schema: {json.dumps(output_json)}"
            elif output_pydantic:
                # Handle Pydantic model
                if hasattr(output_pydantic, 'model_json_schema'):
                    system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_pydantic.model_json_schema())}"
                # Handle inline dict schema
                elif isinstance(output_pydantic, dict):
                    system_prompt += f"\nReturn ONLY a JSON object that matches this schema: {json.dumps(output_pydantic)}"
            
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
    
    def _get_tools_cache_key(self, tools: List[Any]) -> str:
        """Generate a cache key for tools."""
        parts = []
        for tool in tools:
            if isinstance(tool, dict):
                # For dict tools, use sorted JSON representation
                parts.append(json.dumps(tool, sort_keys=True))
            elif callable(tool):
                # For functions, use module.name
                parts.append(f"{tool.__module__}.{tool.__name__}")
            elif isinstance(tool, str):
                # For string tools, use as-is
                parts.append(tool)
            elif isinstance(tool, list):
                # For lists, recursively process
                subparts = []
                for subtool in tool:
                    if isinstance(subtool, dict):
                        subparts.append(json.dumps(subtool, sort_keys=True))
                    elif callable(subtool):
                        subparts.append(f"{subtool.__module__}.{subtool.__name__}")
                    else:
                        subparts.append(str(subtool))
                parts.append(f"[{','.join(subparts)}]")
            else:
                # For other types, use string representation
                parts.append(str(tool))
        return "|".join(parts)
    
    def format_tools(self, tools: Optional[List[Any]]) -> Optional[List[Dict]]:
        """
        Format tools for OpenAI API.
        
        Supports:
        - Pre-formatted OpenAI tools (dicts with type='function')
        - Lists of pre-formatted tools
        - Callable functions
        - String function names
        - MCP tools
        - Gemini internal tools ({"googleSearch": {}}, {"urlContext": {}}, {"codeExecution": {}})
        
        Args:
            tools: List of tools in various formats
            
        Returns:
            List of formatted tools or None
        """
        if not tools:
            return None
        
        # Check cache first
        cache_key = self._get_tools_cache_key(tools)
        if cache_key in self._formatted_tools_cache:
            return self._formatted_tools_cache[cache_key]
            
        formatted_tools = []
        for tool in tools:
            # Check if the tool is already in OpenAI format
            if isinstance(tool, dict) and 'type' in tool and tool['type'] == 'function':
                if 'function' in tool and isinstance(tool['function'], dict) and 'name' in tool['function']:
                    logging.debug(f"Using pre-formatted OpenAI tool: {tool['function']['name']}")
                    # Fix array schemas in the tool parameters
                    fixed_tool = tool.copy()
                    if 'parameters' in fixed_tool['function']:
                        fixed_tool['function']['parameters'] = self._fix_array_schemas(fixed_tool['function']['parameters'])
                    formatted_tools.append(fixed_tool)
                else:
                    logging.debug("Skipping malformed OpenAI tool: missing function or name")
            # Handle lists of tools
            elif isinstance(tool, list):
                for subtool in tool:
                    if isinstance(subtool, dict) and 'type' in subtool and subtool['type'] == 'function':
                        if 'function' in subtool and isinstance(subtool['function'], dict) and 'name' in subtool['function']:
                            logging.debug(f"Using pre-formatted OpenAI tool from list: {subtool['function']['name']}")
                            # Fix array schemas in the tool parameters
                            fixed_tool = subtool.copy()
                            if 'parameters' in fixed_tool['function']:
                                fixed_tool['function']['parameters'] = self._fix_array_schemas(fixed_tool['function']['parameters'])
                            formatted_tools.append(fixed_tool)
                        else:
                            logging.debug("Skipping malformed OpenAI tool in list: missing function or name")
            elif callable(tool):
                tool_def = self._generate_tool_definition(tool)
                if tool_def:
                    formatted_tools.append(tool_def)
            elif isinstance(tool, str):
                tool_def = self._generate_tool_definition_from_name(tool)
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
                json.dumps(formatted_tools)  # Validate serialization
            except (TypeError, ValueError) as e:
                logging.error(f"Tools are not JSON serializable: {e}")
                return None
        
        # Cache the result
        result = formatted_tools if formatted_tools else None
        if result is not None and len(self._formatted_tools_cache) < self._max_cache_size:
            self._formatted_tools_cache[cache_key] = result
                
        return result
    
    def _generate_tool_definition(self, func: Callable) -> Optional[Dict]:
        """Generate a tool definition from a callable function."""
        try:
            sig = inspect.signature(func)
            
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
            param_descriptions = {}
            if docstring:
                import re
                param_section = re.split(r'\s*Args:\s*', docstring)
                if len(param_section) > 1:
                    param_lines = param_section[1].split('\n')
                    for line in param_lines:
                        line = line.strip()
                        if line and ':' in line:
                            param_name, param_desc = line.split(':', 1)
                            param_descriptions[param_name.strip()] = param_desc.strip()
            
            for name, param in parameters_list:
                param_type = "string"  # Default type
                param_info = {}
                
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation is int:
                        param_type = "integer"
                    elif param.annotation is float:
                        param_type = "number"
                    elif param.annotation is bool:
                        param_type = "boolean"
                    elif param.annotation is list:
                        param_type = "array"
                        # OpenAI requires 'items' for array types
                        param_info["items"] = {"type": "string"}
                    elif param.annotation is dict:
                        param_type = "object"
                
                param_info["type"] = param_type
                if name in param_descriptions:
                    param_info["description"] = param_descriptions[name]
                
                parameters["properties"][name] = param_info
                if param.default == inspect.Parameter.empty:
                    parameters["required"].append(name)
            
            # Extract description from docstring
            description = docstring.split('\n')[0] if docstring else f"Function {func.__name__}"
            
            return {
                "type": "function",
                "function": {
                    "name": func.__name__,
                    "description": description,
                    "parameters": parameters
                }
            }
        except Exception as e:
            logging.error(f"Error generating tool definition: {e}")
            return None
    
    def _generate_tool_definition_from_name(self, function_name: str) -> Optional[Dict]:
        """Generate a tool definition from a function name."""
        # This is a placeholder - in agent.py this would look up the function
        # For now, return None as the actual implementation would need access to the function
        logging.debug(f"Tool definition generation from name '{function_name}' requires function reference")
        return None
    
    def process_stream_response(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 1.0,
        tools: Optional[List[Dict]] = None,
        start_time: Optional[float] = None,
        console: Optional[Any] = None,
        display_fn: Optional[Callable] = None,
        reasoning_steps: bool = False,
        stream_callback: Optional[Callable] = None,
        emit_events: bool = False,
        **kwargs
    ) -> Optional[ChatCompletion]:
        """
        Process streaming response and return final response.
        
        Args:
            messages: List of messages for the conversation
            model: Model to use
            temperature: Temperature for generation
            tools: Optional formatted tools
            start_time: Start time for timing display
            console: Console for output
            display_fn: Display function for live updates
            reasoning_steps: Whether to show reasoning steps
            stream_callback: Optional callback for StreamEvent emission
            emit_events: Whether to emit StreamEvents (requires stream_callback)
            **kwargs: Additional parameters for the API
            
        Returns:
            ChatCompletion object or None if error
        """
        # Lazy import StreamEvent types only when needed
        _emit = emit_events and stream_callback is not None
        if _emit:
            from ..streaming.events import StreamEvent, StreamEventType
        
        try:
            # Default start time and console if not provided
            if start_time is None:
                start_time = time.time()
            if console is None:
                console = self.console
            
            # Emit REQUEST_START event
            request_start_perf = time.perf_counter()
            if _emit:
                stream_callback(StreamEvent(
                    type=StreamEventType.REQUEST_START,
                    timestamp=request_start_perf,
                    metadata={"model": model, "message_count": len(messages)}
                ))
            
            # Create the response stream
            response_stream = self.sync_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools if tools else None,
                stream=True,
                stream_options={"include_usage": True} if _emit else None,
                **kwargs
            )
            
            # Emit HEADERS_RECEIVED event (stream object created means headers received)
            if _emit:
                stream_callback(StreamEvent(
                    type=StreamEventType.HEADERS_RECEIVED,
                    timestamp=time.perf_counter()
                ))
            
            full_response_text = ""
            reasoning_content = ""
            chunks = []
            first_token_emitted = False
            last_content_time = None
            ttft_logged = False
            
            # If display function provided, use Live display
            if display_fn:
                Live = _get_rich_live()
                with Live(
                    display_fn("", start_time),
                    console=console,
                    refresh_per_second=10,  # Increased for more responsive streaming
                    transient=True,
                    vertical_overflow="ellipsis",
                    auto_refresh=True
                ) as live:
                    for chunk in response_stream:
                        chunks.append(chunk)
                        
                        # Check for content delta
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response_text += content
                            last_content_time = time.perf_counter()
                            
                            # Log TTFT on first token
                            if not ttft_logged:
                                ttft_ms = (last_content_time - request_start_perf) * 1000
                                logging.debug(f"TTFT (Time To First Token): {ttft_ms:.0f}ms")
                                ttft_logged = True
                            
                            # Emit FIRST_TOKEN on first content
                            if _emit and not first_token_emitted:
                                stream_callback(StreamEvent(
                                    type=StreamEventType.FIRST_TOKEN,
                                    timestamp=last_content_time,
                                    content=content
                                ))
                                first_token_emitted = True
                            elif _emit:
                                # Emit DELTA_TEXT for subsequent tokens
                                stream_callback(StreamEvent(
                                    type=StreamEventType.DELTA_TEXT,
                                    timestamp=last_content_time,
                                    content=content
                                ))
                            
                            live.update(display_fn(full_response_text, start_time))
                        
                        # Handle tool calls streaming
                        if _emit and chunk.choices and hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                            for tc in chunk.choices[0].delta.tool_calls:
                                stream_callback(StreamEvent(
                                    type=StreamEventType.DELTA_TOOL_CALL,
                                    timestamp=time.perf_counter(),
                                    tool_call={
                                        "index": tc.index,
                                        "id": getattr(tc, 'id', None),
                                        "name": getattr(tc.function, 'name', None) if tc.function else None,
                                        "arguments": getattr(tc.function, 'arguments', None) if tc.function else None
                                    }
                                ))
                        
                        # Update live display with reasoning content if enabled
                        if reasoning_steps and hasattr(chunk.choices[0].delta, "reasoning_content"):
                            rc = chunk.choices[0].delta.reasoning_content
                            if rc:
                                reasoning_content += rc
                                live.update(display_fn(f"{full_response_text}\n[Reasoning: {reasoning_content}]", start_time))
                
                # Clear the last generating display with a blank line
                console.print()
            else:
                # Just collect chunks without display, but still emit events
                for chunk in response_stream:
                    chunks.append(chunk)
                    
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        last_content_time = time.perf_counter()
                        
                        # Log TTFT on first token
                        if not ttft_logged:
                            ttft_ms = (last_content_time - request_start_perf) * 1000
                            logging.debug(f"TTFT (Time To First Token): {ttft_ms:.0f}ms")
                            ttft_logged = True
                        
                        if _emit and not first_token_emitted:
                            stream_callback(StreamEvent(
                                type=StreamEventType.FIRST_TOKEN,
                                timestamp=last_content_time,
                                content=content
                            ))
                            first_token_emitted = True
                        elif _emit:
                            # Emit DELTA_TEXT for subsequent tokens
                            stream_callback(StreamEvent(
                                type=StreamEventType.DELTA_TEXT,
                                timestamp=last_content_time,
                                content=content
                            ))
                    
                    # Handle tool calls streaming
                    if _emit and chunk.choices and hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                        for tc in chunk.choices[0].delta.tool_calls:
                            stream_callback(StreamEvent(
                                type=StreamEventType.DELTA_TOOL_CALL,
                                timestamp=time.perf_counter(),
                                tool_call={
                                    "index": tc.index,
                                    "id": getattr(tc, 'id', None),
                                    "name": getattr(tc.function, 'name', None) if tc.function else None,
                                    "arguments": getattr(tc.function, 'arguments', None) if tc.function else None
                                }
                            ))
            
            # Emit LAST_TOKEN and STREAM_END events
            if _emit:
                if last_content_time:
                    stream_callback(StreamEvent(
                        type=StreamEventType.LAST_TOKEN,
                        timestamp=last_content_time
                    ))
                stream_callback(StreamEvent(
                    type=StreamEventType.STREAM_END,
                    timestamp=time.perf_counter(),
                    metadata={"chunk_count": len(chunks)}
                ))
            
            final_response = process_stream_chunks(chunks)
            return final_response
            
        except Exception as e:
            self.logger.error(f"Error in stream processing: {e}")
            return None
    
    async def process_stream_response_async(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 1.0,
        tools: Optional[List[Dict]] = None,
        start_time: Optional[float] = None,
        console: Optional[Any] = None,
        display_fn: Optional[Callable] = None,
        reasoning_steps: bool = False,
        stream_callback: Optional[Callable] = None,
        emit_events: bool = False,
        **kwargs
    ) -> Optional[ChatCompletion]:
        """
        Async version of process_stream_response.
        
        Args:
            messages: List of messages for the conversation
            model: Model to use
            temperature: Temperature for generation
            tools: Optional formatted tools
            start_time: Start time for timing display
            console: Console for output
            display_fn: Display function for live updates
            reasoning_steps: Whether to show reasoning steps
            stream_callback: Optional callback for StreamEvent emission (can be sync or async)
            emit_events: Whether to emit StreamEvents (requires stream_callback)
            **kwargs: Additional parameters for the API
            
        Returns:
            ChatCompletion object or None if error
        """
        # Lazy import StreamEvent types only when needed
        _emit = emit_events and stream_callback is not None
        if _emit:
            from ..streaming.events import StreamEvent, StreamEventType
        
        try:
            # Default start time and console if not provided
            if start_time is None:
                start_time = time.time()
            if console is None:
                console = self.console
            
            # Emit REQUEST_START event
            request_start_perf = time.perf_counter()
            if _emit:
                event = StreamEvent(
                    type=StreamEventType.REQUEST_START,
                    timestamp=request_start_perf,
                    metadata={"model": model, "message_count": len(messages)}
                )
                if asyncio.iscoroutinefunction(stream_callback):
                    await stream_callback(event)
                else:
                    stream_callback(event)
            
            # Create the response stream
            response_stream = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools if tools else None,
                stream=True,
                stream_options={"include_usage": True} if _emit else None,
                **kwargs
            )
            
            # Emit HEADERS_RECEIVED event
            if _emit:
                event = StreamEvent(
                    type=StreamEventType.HEADERS_RECEIVED,
                    timestamp=time.perf_counter()
                )
                if asyncio.iscoroutinefunction(stream_callback):
                    await stream_callback(event)
                else:
                    stream_callback(event)
            
            full_response_text = ""
            reasoning_content = ""
            chunks = []
            first_token_emitted = False
            last_content_time = None
            
            async def emit_event(event: 'StreamEvent'):
                if asyncio.iscoroutinefunction(stream_callback):
                    await stream_callback(event)
                else:
                    stream_callback(event)
            
            # If display function provided, use Live display
            if display_fn:
                Live = _get_rich_live()
                with Live(
                    display_fn("", start_time),
                    console=console,
                    refresh_per_second=10,
                    transient=True,
                    vertical_overflow="ellipsis",
                    auto_refresh=True
                ) as live:
                    async for chunk in response_stream:
                        chunks.append(chunk)
                        
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response_text += content
                            last_content_time = time.perf_counter()
                            
                            if _emit and not first_token_emitted:
                                await emit_event(StreamEvent(
                                    type=StreamEventType.FIRST_TOKEN,
                                    timestamp=last_content_time,
                                    content=content
                                ))
                                first_token_emitted = True
                            elif _emit:
                                await emit_event(StreamEvent(
                                    type=StreamEventType.DELTA_TEXT,
                                    timestamp=last_content_time,
                                    content=content
                                ))
                            
                            live.update(display_fn(full_response_text, start_time))
                        
                        # Handle tool calls streaming
                        if _emit and chunk.choices and hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                            for tc in chunk.choices[0].delta.tool_calls:
                                await emit_event(StreamEvent(
                                    type=StreamEventType.DELTA_TOOL_CALL,
                                    timestamp=time.perf_counter(),
                                    tool_call={
                                        "index": tc.index,
                                        "id": getattr(tc, 'id', None),
                                        "name": getattr(tc.function, 'name', None) if tc.function else None,
                                        "arguments": getattr(tc.function, 'arguments', None) if tc.function else None
                                    }
                                ))
                        
                        # Update live display with reasoning content if enabled
                        if reasoning_steps and hasattr(chunk.choices[0].delta, "reasoning_content"):
                            rc = chunk.choices[0].delta.reasoning_content
                            if rc:
                                reasoning_content += rc
                                live.update(display_fn(f"{full_response_text}\n[Reasoning: {reasoning_content}]", start_time))
                
                # Clear the last generating display with a blank line
                console.print()
            else:
                # Just collect chunks without display
                async for chunk in response_stream:
                    chunks.append(chunk)
                    
                    if _emit and chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        last_content_time = time.perf_counter()
                        
                        if not first_token_emitted:
                            await emit_event(StreamEvent(
                                type=StreamEventType.FIRST_TOKEN,
                                timestamp=last_content_time,
                                content=content
                            ))
                            first_token_emitted = True
                        else:
                            await emit_event(StreamEvent(
                                type=StreamEventType.DELTA_TEXT,
                                timestamp=last_content_time,
                                content=content
                            ))
                    
                    if _emit and chunk.choices and hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                        for tc in chunk.choices[0].delta.tool_calls:
                            await emit_event(StreamEvent(
                                type=StreamEventType.DELTA_TOOL_CALL,
                                timestamp=time.perf_counter(),
                                tool_call={
                                    "index": tc.index,
                                    "id": getattr(tc, 'id', None),
                                    "name": getattr(tc.function, 'name', None) if tc.function else None,
                                    "arguments": getattr(tc.function, 'arguments', None) if tc.function else None
                                }
                            ))
            
            # Emit LAST_TOKEN and STREAM_END events
            if _emit:
                if last_content_time:
                    await emit_event(StreamEvent(
                        type=StreamEventType.LAST_TOKEN,
                        timestamp=last_content_time
                    ))
                await emit_event(StreamEvent(
                    type=StreamEventType.STREAM_END,
                    timestamp=time.perf_counter(),
                    metadata={"chunk_count": len(chunks)}
                ))
            
            final_response = process_stream_chunks(chunks)
            return final_response
            
        except Exception as e:
            self.logger.error(f"Error in async stream processing: {e}")
            return None
    
    def create_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[Any, Iterator[Any]]:
        """
        Create a chat completion using the synchronous client.
        
        Args:
            messages: List of message dictionaries
            model: Model to use for completion
            temperature: Sampling temperature
            stream: Whether to stream the response
            tools: List of tools/functions available
            tool_choice: Tool selection preference
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            ChatCompletion object or stream iterator
        """
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        
        try:
            return self.sync_client.chat.completions.create(**params)
        except Exception as e:
            self.logger.error(f"Error creating completion: {e}")
            raise
    
    async def acreate_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[Any, AsyncIterator[Any]]:
        """
        Create a chat completion using the asynchronous client.
        
        Args:
            messages: List of message dictionaries
            model: Model to use for completion
            temperature: Sampling temperature
            stream: Whether to stream the response
            tools: List of tools/functions available
            tool_choice: Tool selection preference
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            ChatCompletion object or async stream iterator
        """
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        
        try:
            return await self.async_client.chat.completions.create(**params)
        except Exception as e:
            self.logger.error(f"Error creating async completion: {e}")
            raise
    
    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        tools: Optional[List[Any]] = None,
        execute_tool_fn: Optional[Callable] = None,
        stream: bool = True,
        console: Optional[Any] = None,
        display_fn: Optional[Callable] = None,
        reasoning_steps: bool = False,
        verbose: bool = True,
        max_iterations: int = 10,
        **kwargs
    ) -> Optional[ChatCompletion]:
        """
        Create a chat completion with tool support and streaming.
        
        This method handles the full tool execution loop, including:
        - Formatting tools for OpenAI API
        - Making the initial API call
        - Executing tool calls if present
        - Getting final response after tool execution
        
        Args:
            messages: List of message dictionaries
            model: Model to use
            temperature: Temperature for generation
            tools: List of tools (can be callables, dicts, or strings)
            execute_tool_fn: Function to execute tools
            stream: Whether to stream responses
            console: Console for output
            display_fn: Display function for streaming
            reasoning_steps: Whether to show reasoning
            verbose: Whether to show verbose output
            max_iterations: Maximum tool calling iterations
            **kwargs: Additional API parameters
            
        Returns:
            Final ChatCompletion response or None if error
        """
        start_time = time.time()
        
        # Format tools for OpenAI API
        formatted_tools = self.format_tools(tools)
        
        # Continue tool execution loop until no more tool calls are needed
        iteration_count = 0
        
        while iteration_count < max_iterations:
            # Trigger LLM callback for status/trace output
            from ..main import execute_sync_callback
            execute_sync_callback('llm_start', model=model, agent_name=None)
            
            if stream:
                # Process as streaming response with formatted tools
                final_response = self.process_stream_response(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    tools=formatted_tools,
                    start_time=start_time,
                    console=console,
                    display_fn=display_fn,
                    reasoning_steps=reasoning_steps,
                    **kwargs
                )
            else:
                # Process as regular non-streaming response
                if display_fn and console:
                    # When verbose (display_fn provided), use streaming for better UX
                    try:
                        request_start_perf = time.perf_counter()
                        ttft_logged = False
                        Live = _get_rich_live()
                        with Live(display_fn("", start_time), console=console, refresh_per_second=10, transient=True) as live:
                            # Use streaming when display_fn is provided for progressive display
                            response_stream = self.create_completion(
                                messages=messages,
                                model=model,
                                temperature=temperature,
                                tools=formatted_tools,
                                stream=True,  # Always stream when verbose/display_fn
                                **kwargs
                            )
                            
                            full_response_text = ""
                            chunks = []
                            
                            # Process streaming response
                            for chunk in response_stream:
                                chunks.append(chunk)
                                if chunk.choices[0].delta.content:
                                    # Log TTFT on first token
                                    if not ttft_logged:
                                        ttft_ms = (time.perf_counter() - request_start_perf) * 1000
                                        logging.debug(f"TTFT (Time To First Token): {ttft_ms:.0f}ms")
                                        ttft_logged = True
                                    full_response_text += chunk.choices[0].delta.content
                                    live.update(display_fn(full_response_text, start_time))
                            
                            # Process final response from chunks
                            final_response = process_stream_chunks(chunks)
                        
                        # Clear the last generating display with a blank line
                        console.print()
                    except Exception as e:
                        self.logger.error(f"Error in Live display for non-streaming: {e}")
                        # Fallback to regular completion without display
                        final_response = self.create_completion(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            tools=formatted_tools,
                            stream=False,
                            **kwargs
                        )
                else:
                    final_response = self.create_completion(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        tools=formatted_tools,
                        stream=False,
                        **kwargs
                    )
            
            if not final_response:
                return None
            
            # Trigger llm_end callback with metrics for debug output
            llm_end_time = time.perf_counter()
            llm_latency_ms = (llm_end_time - start_time) * 1000
            
            # Extract usage info if available
            usage = getattr(final_response, 'usage', None)
            tokens_in = getattr(usage, 'prompt_tokens', 0) if usage else 0
            tokens_out = getattr(usage, 'completion_tokens', 0) if usage else 0
            
            # Calculate cost using centralized module (lazy litellm import)
            cost = None
            try:
                from ._cost import calculate_cost
                cost = calculate_cost(final_response, model=model)
            except Exception:
                pass  # Cost calculation is optional
            
            execute_sync_callback(
                'llm_end',
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=cost,
                latency_ms=llm_latency_ms
            )
            
            # Check for tool calls
            tool_calls = getattr(final_response.choices[0].message, 'tool_calls', None)
            
            if tool_calls and execute_tool_fn:
                # Convert ToolCall dataclass objects to dict for JSON serialization
                serializable_tool_calls = []
                for tc in tool_calls:
                    if isinstance(tc, ToolCall):
                        # Convert dataclass to dict
                        serializable_tool_calls.append({
                            "id": tc.id,
                            "type": tc.type,
                            "function": tc.function
                        })
                    else:
                        # Already an OpenAI object, keep as is
                        serializable_tool_calls.append(tc)
                
                messages.append({
                    "role": "assistant", 
                    "content": final_response.choices[0].message.content,
                    "tool_calls": serializable_tool_calls
                })
                
                for tool_call in tool_calls:
                    # Handle both ToolCall dataclass and OpenAI object
                    if isinstance(tool_call, ToolCall):
                        function_name = tool_call.function["name"]
                        arguments = json.loads(tool_call.function["arguments"])
                    else:
                        function_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                    
                    # Always trigger callback for tool call tracking (even when verbose=False)
                    display_tool_call_fn = _get_display_tool_call()
                    
                    # Execute the tool
                    tool_result = execute_tool_fn(function_name, arguments)
                    results_str = json.dumps(tool_result) if tool_result else "Function returned an empty output"
                    
                    # Trigger callback with structured parameters for status output
                    display_tool_call_fn(
                        f"Calling function: {function_name}",
                        console=console if verbose else None,
                        tool_name=function_name,
                        tool_input=arguments,
                        tool_output=results_str[:200] if results_str else None
                    )
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id if hasattr(tool_call, 'id') else tool_call['id'],
                        "content": results_str
                    })
                
                # Continue the loop to allow more tool calls
                # The model will see tool results and can make additional tool calls
                
                iteration_count += 1
            else:
                # No tool calls, we're done
                break
        
        return final_response
    
    async def achat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        tools: Optional[List[Any]] = None,
        execute_tool_fn: Optional[Callable] = None,
        stream: bool = True,
        console: Optional[Any] = None,
        display_fn: Optional[Callable] = None,
        reasoning_steps: bool = False,
        verbose: bool = True,
        max_iterations: int = 10,
        **kwargs
    ) -> Optional[ChatCompletion]:
        """
        Async version of chat_completion_with_tools.
        
        Args:
            messages: List of message dictionaries
            model: Model to use
            temperature: Temperature for generation
            tools: List of tools (can be callables, dicts, or strings)
            execute_tool_fn: Async function to execute tools
            stream: Whether to stream responses
            console: Console for output
            display_fn: Display function for streaming
            reasoning_steps: Whether to show reasoning
            verbose: Whether to show verbose output
            max_iterations: Maximum tool calling iterations
            **kwargs: Additional API parameters
            
        Returns:
            Final ChatCompletion response or None if error
        """
        start_time = time.time()
        
        # Format tools for OpenAI API
        formatted_tools = self.format_tools(tools)
        
        # Continue tool execution loop until no more tool calls are needed
        iteration_count = 0
        
        while iteration_count < max_iterations:
            if stream:
                # Process as streaming response with formatted tools
                final_response = await self.process_stream_response_async(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    tools=formatted_tools,
                    start_time=start_time,
                    console=console,
                    display_fn=display_fn,
                    reasoning_steps=reasoning_steps,
                    **kwargs
                )
            else:
                # Process as regular non-streaming response
                if display_fn and console:
                    # When verbose (display_fn provided), use streaming for better UX
                    try:
                        Live = _get_rich_live()
                        with Live(display_fn("", start_time), console=console, refresh_per_second=4, transient=True) as live:
                            # Use streaming when display_fn is provided for progressive display
                            response_stream = await self.acreate_completion(
                                messages=messages,
                                model=model,
                                temperature=temperature,
                                tools=formatted_tools,
                                stream=True,  # Always stream when verbose/display_fn
                                **kwargs
                            )
                            
                            full_response_text = ""
                            chunks = []
                            
                            # Process streaming response
                            async for chunk in response_stream:
                                chunks.append(chunk)
                                if chunk.choices[0].delta.content:
                                    full_response_text += chunk.choices[0].delta.content
                                    live.update(display_fn(full_response_text, start_time))
                            
                            # Process final response from chunks
                            final_response = process_stream_chunks(chunks)
                        
                        # Clear the last generating display with a blank line
                        console.print()
                    except Exception as e:
                        self.logger.error(f"Error in Live display for async non-streaming: {e}")
                        # Fallback to regular completion without display
                        final_response = await self.acreate_completion(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            tools=formatted_tools,
                            stream=False,
                            **kwargs
                        )
                else:
                    final_response = await self.acreate_completion(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        tools=formatted_tools,
                        stream=False,
                        **kwargs
                    )
            
            if not final_response:
                return None
            
            # Check for tool calls
            tool_calls = getattr(final_response.choices[0].message, 'tool_calls', None)
            
            if tool_calls and execute_tool_fn:
                # Convert ToolCall dataclass objects to dict for JSON serialization
                serializable_tool_calls = []
                for tc in tool_calls:
                    if isinstance(tc, ToolCall):
                        # Convert dataclass to dict
                        serializable_tool_calls.append({
                            "id": tc.id,
                            "type": tc.type,
                            "function": tc.function
                        })
                    else:
                        # Already an OpenAI object, keep as is
                        serializable_tool_calls.append(tc)
                
                messages.append({
                    "role": "assistant", 
                    "content": final_response.choices[0].message.content,
                    "tool_calls": serializable_tool_calls
                })
                
                for tool_call in tool_calls:
                    # Handle both ToolCall dataclass and OpenAI object
                    if isinstance(tool_call, ToolCall):
                        function_name = tool_call.function["name"]
                        arguments = json.loads(tool_call.function["arguments"])
                    else:
                        function_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                    
                    # Always trigger callback for tool call tracking (even when verbose=False)
                    display_tool_call_fn = _get_display_tool_call()
                    display_tool_call_fn(f"Calling function: {function_name}", console=console if verbose else None)
                    
                    if verbose and console:
                        console.print(f"[dim]Arguments:[/dim] {arguments}")
                    
                    # Execute the tool (async)
                    if asyncio.iscoroutinefunction(execute_tool_fn):
                        tool_result = await execute_tool_fn(function_name, arguments)
                    else:
                        # Run sync function in executor
                        loop = asyncio.get_event_loop()
                        tool_result = await loop.run_in_executor(
                            None, 
                            lambda: execute_tool_fn(function_name, arguments)
                        )
                    
                    results_str = json.dumps(tool_result) if tool_result else "Function returned an empty output"
                    
                    # Trigger callback with result
                    display_tool_call_fn(f"Function {function_name} returned: {results_str[:200]}{'...' if len(results_str) > 200 else ''}", console=console if verbose else None)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id if hasattr(tool_call, 'id') else tool_call['id'],
                        "content": results_str
                    })
                
                # Continue the loop to allow more tool calls
                # The model will see tool results and can make additional tool calls
                
                iteration_count += 1
            else:
                # No tool calls, we're done
                break
        
        return final_response
        
    def chat_completion_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        tools: Optional[List[Any]] = None,
        execute_tool_fn: Optional[Callable] = None,
        reasoning_steps: bool = False,
        verbose: bool = True,
        max_iterations: int = 10,
        **kwargs
    ):
        """
        Create a streaming chat completion with tool support.
        
        This method yields chunks of the response as they are generated,
        enabling real-time streaming to the user.
        
        Args:
            messages: List of message dictionaries
            model: Model to use
            temperature: Temperature for generation
            tools: List of tools (can be callables, dicts, or strings)
            execute_tool_fn: Function to execute tools
            reasoning_steps: Whether to show reasoning
            verbose: Whether to show verbose output
            max_iterations: Maximum tool calling iterations
            **kwargs: Additional API parameters
            
        Yields:
            String chunks of the response as they are generated
        """
        # Format tools for OpenAI API
        formatted_tools = self.format_tools(tools)
        
        # Continue tool execution loop until no more tool calls are needed
        iteration_count = 0
        
        while iteration_count < max_iterations:
            try:
                # Create streaming response
                response_stream = self.sync_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    tools=formatted_tools if formatted_tools else None,
                    stream=True,
                    **kwargs
                )
                
                full_response_text = ""
                reasoning_content = ""
                chunks = []
                
                # Stream the response chunk by chunk
                for chunk in response_stream:
                    chunks.append(chunk)
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response_text += content
                        yield content
                    
                    # Handle reasoning content if enabled
                    if reasoning_steps and chunk.choices and hasattr(chunk.choices[0].delta, "reasoning_content"):
                        rc = chunk.choices[0].delta.reasoning_content
                        if rc:
                            reasoning_content += rc
                            yield f"[Reasoning: {rc}]"
                
                # Process the complete response to check for tool calls
                final_response = process_stream_chunks(chunks)
                
                if not final_response:
                    return
                
                # Check for tool calls
                tool_calls = getattr(final_response.choices[0].message, 'tool_calls', None)
                
                if tool_calls and execute_tool_fn:
                    # Convert ToolCall dataclass objects to dict for JSON serialization
                    serializable_tool_calls = []
                    for tc in tool_calls:
                        if isinstance(tc, ToolCall):
                            # Convert dataclass to dict
                            serializable_tool_calls.append({
                                "id": tc.id,
                                "type": tc.type,
                                "function": tc.function
                            })
                        else:
                            # Already an OpenAI object, keep as is
                            serializable_tool_calls.append(tc)
                    
                    messages.append({
                        "role": "assistant", 
                        "content": final_response.choices[0].message.content,
                        "tool_calls": serializable_tool_calls
                    })
                    
                    for tool_call in tool_calls:
                        # Handle both ToolCall dataclass and OpenAI object
                        try:
                            if isinstance(tool_call, ToolCall):
                                function_name = tool_call.function["name"]
                                arguments = json.loads(tool_call.function["arguments"])
                            else:
                                function_name = tool_call.function.name
                                arguments = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError as e:
                            if verbose:
                                yield f"\n[Error parsing arguments for {function_name if 'function_name' in locals() else 'unknown function'}: {str(e)}]"
                            continue
                        
                        # Always trigger callback for tool call tracking (even when verbose=False)
                        display_tool_call_fn = _get_display_tool_call()
                        display_tool_call_fn(f"Calling function: {function_name}", console=None)
                        
                        if verbose:
                            yield f"\n[Calling function: {function_name}]"
                        
                        # Execute the tool with error handling
                        try:
                            tool_result = execute_tool_fn(function_name, arguments)
                            results_str = json.dumps(tool_result) if tool_result else "Function returned an empty output"
                        except Exception as e:
                            results_str = f"Error executing function: {str(e)}"
                            if verbose:
                                yield f"\n[Function error: {str(e)}]"
                        
                        # Trigger callback with result
                        display_tool_call_fn(f"Function {function_name} returned: {results_str[:200]}{'...' if len(results_str) > 200 else ''}", console=None)
                        
                        if verbose:
                            yield f"\n[Function result: {results_str}]"
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id if hasattr(tool_call, 'id') else tool_call['id'],
                            "content": results_str
                        })
                    
                    # Continue the loop to allow more tool calls
                    iteration_count += 1
                else:
                    # No tool calls, we're done
                    break
                    
            except Exception as e:
                yield f"Error: {str(e)}"
                break
    
    def parse_structured_output(
        self,
        messages: List[Dict[str, Any]],
        response_format: BaseModel,
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        **kwargs
    ) -> Any:
        """
        Parse structured output using the beta.chat.completions.parse API.
        
        Args:
            messages: List of message dictionaries
            response_format: Pydantic model for response validation
            model: Model to use for completion
            temperature: Sampling temperature
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            Parsed response according to the response_format
        """
        try:
            response = self.sync_client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                **kwargs
            )
            return response.choices[0].message.parsed
        except Exception as e:
            self.logger.error(f"Error parsing structured output: {e}")
            raise
    
    async def aparse_structured_output(
        self,
        messages: List[Dict[str, Any]],
        response_format: BaseModel,
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        **kwargs
    ) -> Any:
        """
        Parse structured output using the async beta.chat.completions.parse API.
        
        Args:
            messages: List of message dictionaries
            response_format: Pydantic model for response validation
            model: Model to use for completion
            temperature: Sampling temperature
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            Parsed response according to the response_format
        """
        try:
            response = await self.async_client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                **kwargs
            )
            return response.choices[0].message.parsed
        except Exception as e:
            self.logger.error(f"Error parsing async structured output: {e}")
            raise
    
    def close(self):
        """Close the OpenAI clients."""
        if self._sync_client and hasattr(self._sync_client, 'close'):
            self._sync_client.close()
        if self._async_client and hasattr(self._async_client, 'close'):
            self._async_client.close()
    
    async def aclose(self):
        """Asynchronously close the OpenAI clients."""
        if self._sync_client and hasattr(self._sync_client, 'close'):
            await asyncio.to_thread(self._sync_client.close)
        if self._async_client and hasattr(self._async_client, 'aclose'):
            await self._async_client.aclose()


# Global client instance (similar to main.py pattern)
_global_client = None
_global_client_params = None

def get_openai_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAIClient:
    """
    Get or create a global OpenAI client instance.
    
    Args:
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        base_url: Custom base URL for API endpoints
        
    Returns:
        OpenAIClient instance
    """
    global _global_client, _global_client_params
    
    # Normalize parameters for comparison
    normalized_api_key = api_key or os.getenv("OPENAI_API_KEY")
    normalized_base_url = base_url
    current_params = (normalized_api_key, normalized_base_url)
    
    # Only create new client if parameters changed or first time
    if _global_client is None or _global_client_params != current_params:
        _global_client = OpenAIClient(api_key=api_key, base_url=base_url)
        _global_client_params = current_params
    
    return _global_client