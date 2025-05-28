import asyncio
import threading
import queue
import time
import inspect
import shlex
import logging
import os
import re
import sys
from typing import Any, List, Optional, Callable, Iterable, Union
from functools import wraps, partial

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPToolRunner(threading.Thread):
    """A dedicated thread for running MCP operations."""
    
    def __init__(self, server_params, timeout=60):
        super().__init__(daemon=True)
        self.server_params = server_params
        self.queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.initialized = threading.Event()
        self.tools = []
        self.timeout = timeout
        self.start()
        
    def run(self):
        """Main thread function that processes MCP requests."""
        asyncio.run(self._run_async())
        
    async def _run_async(self):
        """Async entry point for MCP operations."""
        try:
            # Set up MCP session
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize connection
                    await session.initialize()
                    
                    # Get tools
                    tools_result = await session.list_tools()
                    self.tools = tools_result.tools
                    
                    # Signal that initialization is complete
                    self.initialized.set()
                    
                    # Process requests
                    while True:
                        try:
                            # Check for new requests
                            try:
                                item = self.queue.get(block=False)
                                if item is None:  # Shutdown signal
                                    break
                                
                                tool_name, arguments = item
                                try:
                                    result = await session.call_tool(tool_name, arguments)
                                    self.result_queue.put((True, result))
                                except Exception as e:
                                    self.result_queue.put((False, str(e)))
                            except queue.Empty:
                                pass
                            
                            # Give other tasks a chance to run
                            await asyncio.sleep(0.01)
                        except asyncio.CancelledError:
                            break
        except Exception as e:
            self.initialized.set()  # Ensure we don't hang
            self.result_queue.put((False, f"MCP initialization error: {str(e)}"))
    
    def call_tool(self, tool_name, arguments):
        """Call an MCP tool and wait for the result."""
        if not self.initialized.is_set():
            self.initialized.wait(timeout=self.timeout)
            if not self.initialized.is_set():
                return f"Error: MCP initialization timed out after {self.timeout} seconds"
        
        # Put request in queue
        self.queue.put((tool_name, arguments))
        
        # Wait for result
        success, result = self.result_queue.get()
        if not success:
            return f"Error: {result}"
        
        # Process result
        if hasattr(result, 'content') and result.content:
            if hasattr(result.content[0], 'text'):
                return result.content[0].text
            return str(result.content[0])
        return str(result)
    
    def shutdown(self):
        """Signal the thread to shut down."""
        self.queue.put(None)


class MCP:
    """
    Model Context Protocol (MCP) integration for PraisonAI Agents.
    
    This class provides a simple way to connect to MCP servers and use their tools
    within PraisonAI agents.
    
    Example:
        ```python
        from praisonaiagents import Agent
        from praisonaiagents.mcp import MCP
        
        # Method 1: Using command and args separately
        agent = Agent(
            instructions="You are a helpful assistant...",
            llm="gpt-4o-mini",
            tools=MCP(
                command="/path/to/python",
                args=["/path/to/app.py"]
            )
        )
        
        # Method 2: Using a single command string
        agent = Agent(
            instructions="You are a helpful assistant...",
            llm="gpt-4o-mini",
            tools=MCP("/path/to/python /path/to/app.py")
        )
        
        # Method 3: Using an SSE endpoint
        agent = Agent(
            instructions="You are a helpful assistant...",
            llm="gpt-4o-mini",
            tools=MCP("http://localhost:8080/sse")
        )
        
        agent.start("What is the stock price of Tesla?")
        ```
    """
    
    def __init__(self, command_or_string=None, args=None, *, command=None, timeout=60, debug=False, **kwargs):
        """
        Initialize the MCP connection and get tools.
        
        Args:
            command_or_string: Either:
                             - The command to run the MCP server (e.g., Python path)
                             - A complete command string (e.g., "/path/to/python /path/to/app.py")
                             - For NPX: 'npx' command with args for smithery tools
                             - An SSE URL (e.g., "http://localhost:8080/sse")
            args: Arguments to pass to the command (when command_or_string is the command)
            command: Alternative parameter name for backward compatibility
            timeout: Timeout in seconds for MCP server initialization and tool calls (default: 60)
            debug: Enable debug logging for MCP operations (default: False)
            **kwargs: Additional parameters for StdioServerParameters
        """
        # Handle backward compatibility with named parameter 'command'
        if command_or_string is None and command is not None:
            command_or_string = command
        
        # Set up logging - default to WARNING level to hide INFO messages
        if debug:
            logging.getLogger("mcp-wrapper").setLevel(logging.DEBUG)
            logging.getLogger("mcp-sse").setLevel(logging.DEBUG)
            logging.getLogger("mcp.client").setLevel(logging.DEBUG)
            logging.getLogger("sse").setLevel(logging.DEBUG)
            logging.getLogger("mcp-server").setLevel(logging.DEBUG)
            logging.getLogger("mcp-client").setLevel(logging.DEBUG)
            logging.getLogger("_client").setLevel(logging.DEBUG)
            logging.getLogger("httpx").setLevel(logging.DEBUG)
            logging.getLogger("llm").setLevel(logging.DEBUG)
        else:
            # Set all MCP-related loggers to WARNING level by default
            logging.getLogger("mcp-wrapper").setLevel(logging.WARNING)
            logging.getLogger("mcp-sse").setLevel(logging.WARNING)
            logging.getLogger("mcp.client").setLevel(logging.WARNING)
            logging.getLogger("sse").setLevel(logging.WARNING)
            logging.getLogger("mcp-server").setLevel(logging.WARNING)
            logging.getLogger("mcp-client").setLevel(logging.WARNING)
            logging.getLogger("_client").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("llm").setLevel(logging.WARNING)
        
        # Store additional parameters
        self.timeout = timeout
        self.debug = debug
        
        # Check if this is an SSE URL
        if isinstance(command_or_string, str) and re.match(r'^https?://', command_or_string):
            # Import the SSE client implementation
            from .mcp_sse import SSEMCPClient
            self.sse_client = SSEMCPClient(command_or_string, debug=debug, timeout=timeout)
            self._tools = list(self.sse_client.tools)
            self.is_sse = True
            self.is_npx = False
            return
            
        # Handle the single string format for stdio client
        if isinstance(command_or_string, str) and args is None:
            # Split the string into command and args using shell-like parsing
            parts = shlex.split(command_or_string)
            if not parts:
                raise ValueError("Empty command string")
            
            cmd = parts[0]
            arguments = parts[1:] if len(parts) > 1 else []
        else:
            # Use the original format with separate command and args
            cmd = command_or_string
            arguments = args or []
        
        # Set up stdio client
        self.is_sse = False
        
        # Ensure UTF-8 encoding in environment for Docker compatibility
        env = kwargs.get('env', {})
        if not env:
            env = os.environ.copy()
        env.update({
            'PYTHONIOENCODING': 'utf-8',
            'LC_ALL': 'C.UTF-8',
            'LANG': 'C.UTF-8'
        })
        kwargs['env'] = env
        
        self.server_params = StdioServerParameters(
            command=cmd,
            args=arguments,
            **kwargs
        )
        self.runner = MCPToolRunner(self.server_params, timeout)
        
        # Wait for initialization
        if not self.runner.initialized.wait(timeout=self.timeout):
            error_msg = f"Warning: MCP initialization timed out after {self.timeout} seconds"
            print(error_msg)
            # In Streamlit, also log as warning since print might not be visible
            if self._is_streamlit_environment():
                logging.warning(error_msg)
        
        # Automatically detect if this is an NPX command
        self.is_npx = cmd == 'npx' or (isinstance(cmd, str) and os.path.basename(cmd) == 'npx')
        
        # For NPX-based MCP servers, use a different approach
        if self.is_npx:
            self._function_declarations = []
            self._initialize_npx_mcp_tools(cmd, arguments)
        else:
            # Generate tool functions immediately and store them
            self._tools = self._generate_tool_functions()
    
    def _generate_tool_functions(self) -> List[Callable]:
        """
        Generate functions for each MCP tool.
        
        Returns:
            List[Callable]: Functions that can be used as tools
        """
        if self.is_sse:
            return list(self.sse_client.tools)
            
        tool_functions = []
        
        for tool in self.runner.tools:
            wrapper = self._create_tool_wrapper(tool)
            tool_functions.append(wrapper)
        
        return tool_functions
    
    def _is_streamlit_environment(self) -> bool:
        """
        Detect if we're running in a Streamlit environment.
        
        Returns:
            bool: True if running in Streamlit, False otherwise
        """
        try:
            import streamlit
            # Check if we're in Streamlit's execution context
            return hasattr(streamlit, '_is_running_with_streamlit') or 'streamlit' in sys.modules
        except ImportError:
            return False
    
    def _create_tool_wrapper(self, tool):
        """Create a wrapper function for an MCP tool."""
        # Determine parameter names from the schema
        param_names = []
        param_annotations = {}
        required_params = []
        
        if hasattr(tool, 'inputSchema') and tool.inputSchema:
            properties = tool.inputSchema.get("properties", {})
            required = tool.inputSchema.get("required", [])
            
            for name, prop in properties.items():
                param_names.append(name)
                
                # Set annotation based on property type
                prop_type = prop.get("type", "string")
                if prop_type == "string":
                    param_annotations[name] = str
                elif prop_type == "integer":
                    param_annotations[name] = int
                elif prop_type == "number":
                    param_annotations[name] = float
                elif prop_type == "boolean":
                    param_annotations[name] = bool
                elif prop_type == "array":
                    param_annotations[name] = list
                elif prop_type == "object":
                    param_annotations[name] = dict
                else:
                    param_annotations[name] = Any
                
                if name in required:
                    required_params.append(name)
        
        # Create the function signature
        params = []
        for name in param_names:
            is_required = name in required_params
            param = inspect.Parameter(
                name=name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty if is_required else None,
                annotation=param_annotations.get(name, Any)
            )
            params.append(param)
        
        # Create function template to be properly decorated
        def template_function(*args, **kwargs):
            return None
        
        # Create a proper function with the correct signature
        template_function.__signature__ = inspect.Signature(params)
        template_function.__annotations__ = param_annotations
        template_function.__name__ = tool.name
        template_function.__qualname__ = tool.name
        template_function.__doc__ = tool.description
        
        # Create the actual function using a decorator
        @wraps(template_function)
        def wrapper(*args, **kwargs):
            # Map positional args to parameter names
            all_args = {}
            for i, arg in enumerate(args):
                if i < len(param_names):
                    all_args[param_names[i]] = arg
            
            # Add keyword args
            all_args.update(kwargs)
            
            # Call the tool
            return self.runner.call_tool(tool.name, all_args)
        
        # Make sure the wrapper has the correct signature for inspection
        wrapper.__signature__ = inspect.Signature(params)
        
        return wrapper
    
    def _initialize_npx_mcp_tools(self, cmd, arguments):
        """Initialize the NPX MCP tools by extracting tool definitions."""
        try:
            # For NPX tools, we'll use the same approach as regular MCP tools
            # but we need to handle the initialization differently
            if self.debug:
                logging.debug(f"Initializing NPX MCP tools with command: {cmd} {' '.join(arguments)}")
            
            # Generate tool functions using the regular MCP approach
            self._tools = self._generate_tool_functions()
            
            if self.debug:
                logging.debug(f"Generated {len(self._tools)} NPX MCP tools")
                
        except Exception as e:
            if self.debug:
                logging.error(f"Failed to initialize NPX MCP tools: {e}")
            raise RuntimeError(f"Failed to initialize NPX MCP tools: {e}")
    
    def __iter__(self) -> Iterable[Callable]:
        """
        Allow the MCP instance to be used directly as an iterable of tools.
        
        This makes it possible to pass the MCP instance directly to the Agent's tools parameter.
        """
        return iter(self._tools)
    
    def to_openai_tool(self):
        """Convert the MCP tool to an OpenAI-compatible tool definition.
        
        This method is specifically invoked by the Agent class when using
        provider/model format (e.g., "openai/gpt-4o-mini").
        
        Returns:
            dict or list: OpenAI-compatible tool definition(s)
        """
        if self.is_sse and hasattr(self, 'sse_client') and self.sse_client.tools:
            # Return all tools from SSE client
            return self.sse_client.to_openai_tools()
            
        # For simplicity, we'll convert the first tool only if multiple exist
        # More complex implementations could handle multiple tools
        if not hasattr(self, 'runner') or not self.runner.tools:
            error_msg = "No MCP tools available to convert to OpenAI format"
            logging.warning(error_msg)
            # In Streamlit, provide more helpful error information
            if self._is_streamlit_environment():
                logging.error(f"MCP Tools Error in Streamlit: {error_msg}. Check MCP server initialization.")
            return None
            
        # Convert all tools to OpenAI format
        openai_tools = []
        for tool in self.runner.tools:
            # Create OpenAI tool definition
            parameters = {}
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                parameters = tool.inputSchema
            else:
                # Create a minimal schema if none exists
                parameters = {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
                
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description if hasattr(tool, 'description') else f"Call the {tool.name} tool",
                    "parameters": parameters
                }
            })
        
        return openai_tools
    
    def __del__(self):
        """Clean up resources when the object is garbage collected."""
        if hasattr(self, 'runner'):
            self.runner.shutdown() 