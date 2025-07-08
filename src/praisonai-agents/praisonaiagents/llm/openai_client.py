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
from typing import Any, Dict, List, Optional, Union, AsyncIterator, Iterator, Callable, Tuple
from openai import OpenAI, AsyncOpenAI
from openai.types.chat import ChatCompletionChunk
from pydantic import BaseModel
from dataclasses import dataclass
from rich.console import Console
from rich.live import Live
import inspect

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
        
        # Initialize synchronous client (lazy loading for async)
        self._sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self._async_client = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        # Initialize console for display
        self.console = Console()
    
    @property
    def sync_client(self) -> OpenAI:
        """Get the synchronous OpenAI client."""
        return self._sync_client
    
    @property
    def async_client(self) -> AsyncOpenAI:
        """Get the asynchronous OpenAI client (lazy initialization)."""
        if self._async_client is None:
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
                system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_json.model_json_schema())}"
            elif output_pydantic:
                system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_pydantic.model_json_schema())}"
            
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
    
    def format_tools(self, tools: Optional[List[Any]]) -> Optional[List[Dict]]:
        """
        Format tools for OpenAI API.
        
        Supports:
        - Pre-formatted OpenAI tools (dicts with type='function')
        - Lists of pre-formatted tools
        - Callable functions
        - String function names
        - MCP tools
        
        Args:
            tools: List of tools in various formats
            
        Returns:
            List of formatted tools or None
        """
        if not tools:
            return None
            
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
            else:
                logging.debug(f"Skipping tool of unsupported type: {type(tool)}")
                
        # Validate JSON serialization before returning
        if formatted_tools:
            try:
                json.dumps(formatted_tools)  # Validate serialization
            except (TypeError, ValueError) as e:
                logging.error(f"Tools are not JSON serializable: {e}")
                return None
                
        return formatted_tools if formatted_tools else None
    
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
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        start_time: Optional[float] = None,
        console: Optional[Console] = None,
        display_fn: Optional[Callable] = None,
        reasoning_steps: bool = False,
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
            **kwargs: Additional parameters for the API
            
        Returns:
            ChatCompletion object or None if error
        """
        try:
            # Default start time and console if not provided
            if start_time is None:
                start_time = time.time()
            if console is None:
                console = self.console
            
            # Create the response stream
            response_stream = self._sync_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools if tools else None,
                stream=True,
                **kwargs
            )
            
            full_response_text = ""
            reasoning_content = ""
            chunks = []
            
            # If display function provided, use Live display
            if display_fn:
                with Live(
                    display_fn("", start_time),
                    console=console,
                    refresh_per_second=4,
                    transient=True,
                    vertical_overflow="ellipsis",
                    auto_refresh=True
                ) as live:
                    for chunk in response_stream:
                        chunks.append(chunk)
                        if chunk.choices[0].delta.content:
                            full_response_text += chunk.choices[0].delta.content
                            live.update(display_fn(full_response_text, start_time))
                        
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
                for chunk in response_stream:
                    chunks.append(chunk)
            
            final_response = process_stream_chunks(chunks)
            return final_response
            
        except Exception as e:
            self.logger.error(f"Error in stream processing: {e}")
            return None
    
    async def process_stream_response_async(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        start_time: Optional[float] = None,
        console: Optional[Console] = None,
        display_fn: Optional[Callable] = None,
        reasoning_steps: bool = False,
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
            **kwargs: Additional parameters for the API
            
        Returns:
            ChatCompletion object or None if error
        """
        try:
            # Default start time and console if not provided
            if start_time is None:
                start_time = time.time()
            if console is None:
                console = self.console
            
            # Create the response stream
            response_stream = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools if tools else None,
                stream=True,
                **kwargs
            )
            
            full_response_text = ""
            reasoning_content = ""
            chunks = []
            
            # If display function provided, use Live display
            if display_fn:
                with Live(
                    display_fn("", start_time),
                    console=console,
                    refresh_per_second=4,
                    transient=True,
                    vertical_overflow="ellipsis",
                    auto_refresh=True
                ) as live:
                    async for chunk in response_stream:
                        chunks.append(chunk)
                        if chunk.choices[0].delta.content:
                            full_response_text += chunk.choices[0].delta.content
                            live.update(display_fn(full_response_text, start_time))
                        
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
            
            final_response = process_stream_chunks(chunks)
            return final_response
            
        except Exception as e:
            self.logger.error(f"Error in async stream processing: {e}")
            return None
    
    def create_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[Any, Iterator[ChatCompletionChunk]]:
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
            return self._sync_client.chat.completions.create(**params)
        except Exception as e:
            self.logger.error(f"Error creating completion: {e}")
            raise
    
    async def acreate_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[Any, AsyncIterator[ChatCompletionChunk]]:
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
        model: str = "gpt-4o",
        temperature: float = 0.7,
        tools: Optional[List[Any]] = None,
        execute_tool_fn: Optional[Callable] = None,
        stream: bool = True,
        console: Optional[Console] = None,
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
                    
                    if verbose and console:
                        console.print(f"[bold]Calling function:[/bold] {function_name}")
                        console.print(f"[dim]Arguments:[/dim] {arguments}")
                    
                    # Execute the tool
                    tool_result = execute_tool_fn(function_name, arguments)
                    results_str = json.dumps(tool_result) if tool_result else "Function returned an empty output"
                    
                    if verbose and console:
                        console.print(f"[dim]Result:[/dim] {results_str}")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id if hasattr(tool_call, 'id') else tool_call['id'],
                        "content": results_str
                    })
                
                # Check if we should continue (for tools like sequential thinking)
                should_continue = False
                for tool_call in tool_calls:
                    # Handle both ToolCall dataclass and OpenAI object
                    if isinstance(tool_call, ToolCall):
                        function_name = tool_call.function["name"]
                        arguments = json.loads(tool_call.function["arguments"])
                    else:
                        function_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                    
                    # For sequential thinking tool, check if nextThoughtNeeded is True
                    if function_name == "sequentialthinking" and arguments.get("nextThoughtNeeded", False):
                        should_continue = True
                        break
                
                if not should_continue:
                    # Get final response after tool calls
                    if stream:
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
                        final_response = self.create_completion(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            stream=False,
                            **kwargs
                        )
                    break
                
                iteration_count += 1
            else:
                # No tool calls, we're done
                break
        
        return final_response
    
    async def achat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        tools: Optional[List[Any]] = None,
        execute_tool_fn: Optional[Callable] = None,
        stream: bool = True,
        console: Optional[Console] = None,
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
                    
                    if verbose and console:
                        console.print(f"[bold]Calling function:[/bold] {function_name}")
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
                    
                    if verbose and console:
                        console.print(f"[dim]Result:[/dim] {results_str}")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id if hasattr(tool_call, 'id') else tool_call['id'],
                        "content": results_str
                    })
                
                # Check if we should continue (for tools like sequential thinking)
                should_continue = False
                for tool_call in tool_calls:
                    # Handle both ToolCall dataclass and OpenAI object
                    if isinstance(tool_call, ToolCall):
                        function_name = tool_call.function["name"]
                        arguments = json.loads(tool_call.function["arguments"])
                    else:
                        function_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                    
                    # For sequential thinking tool, check if nextThoughtNeeded is True
                    if function_name == "sequentialthinking" and arguments.get("nextThoughtNeeded", False):
                        should_continue = True
                        break
                
                if not should_continue:
                    # Get final response after tool calls
                    if stream:
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
                        final_response = await self.acreate_completion(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            stream=False,
                            **kwargs
                        )
                    break
                
                iteration_count += 1
            else:
                # No tool calls, we're done
                break
        
        return final_response
    
    def parse_structured_output(
        self,
        messages: List[Dict[str, Any]],
        response_format: BaseModel,
        model: str = "gpt-4o",
        temperature: float = 0.7,
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
            response = self._sync_client.beta.chat.completions.parse(
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
        model: str = "gpt-4o",
        temperature: float = 0.7,
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
        if hasattr(self._sync_client, 'close'):
            self._sync_client.close()
        if self._async_client and hasattr(self._async_client, 'close'):
            self._async_client.close()
    
    async def aclose(self):
        """Asynchronously close the OpenAI clients."""
        if hasattr(self._sync_client, 'close'):
            await asyncio.to_thread(self._sync_client.close)
        if self._async_client and hasattr(self._async_client, 'aclose'):
            await self._async_client.aclose()


# Global client instance (similar to main.py pattern)
_global_client = None

def get_openai_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAIClient:
    """
    Get or create a global OpenAI client instance.
    
    Args:
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        base_url: Custom base URL for API endpoints
        
    Returns:
        OpenAIClient instance
    """
    global _global_client
    
    if _global_client is None:
        _global_client = OpenAIClient(api_key=api_key, base_url=base_url)
    
    return _global_client