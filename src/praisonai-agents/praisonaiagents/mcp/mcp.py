import asyncio
import threading
import queue
import time
import inspect
import shlex
from typing import Dict, Any, List, Optional, Callable, Iterable, Union
from functools import wraps, partial

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPToolRunner(threading.Thread):
    """A dedicated thread for running MCP operations."""
    
    def __init__(self, server_params):
        """
        Initializes the MCPToolRunner and starts its asynchronous processing thread.
        
        Sets up queues for handling tool requests and results, configures an event to signal
        when initialization is complete, and stores the server parameters for establishing
        an MCP connection. The daemon thread is started immediately to manage asynchronous
        tool operations.
        
        Args:
            server_params: Configuration parameters for connecting to the MCP server.
        """
        super().__init__(daemon=True)
        self.server_params = server_params
        self.queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.initialized = threading.Event()
        self.tools = []
        self.start()
        
    def run(self):
        """
        Starts the asynchronous loop to process MCP requests.
        
        This method serves as the entry point for the dedicated thread,
        initializing an asyncio event loop to execute the internal
        asynchronous request processing routine.
        """
        asyncio.run(self._run_async())
        
    async def _run_async(self):
        """
        Initializes the MCP session and processes tool requests asynchronously.
        
        Establishes a connection with the MCP server using the provided parameters, initializes
        the session, and retrieves available tools before signaling readiness. Then, it enters
        a loop to poll an internal request queue for tool invocation requests, calling the
        appropriate tool for each request and enqueuing the result or error message. The loop
        exits gracefully when a shutdown signal or cancellation is encountered.
        """
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
        """
        Calls an MCP tool synchronously and returns its result.
        
        This method waits for MCP initialization (up to 30 seconds) before proceeding. If initialization
        times out, it returns an error message. Otherwise, it enqueues the tool request with the specified
        arguments and waits for the result. If the tool execution fails, an error message is returned; if
        successful, the method extracts and returns the text content of the result when available, or a string
        representation of the result.
          
        Parameters:
            tool_name: The name of the MCP tool to execute.
            arguments: The arguments to pass to the MCP tool.
          
        Returns:
            A string containing the tool's output or an error message.
        """
        if not self.initialized.is_set():
            self.initialized.wait(timeout=30)
            if not self.initialized.is_set():
                return "Error: MCP initialization timed out"
        
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
        """
        Signals the worker thread to terminate.
        
        Inserts a sentinel value (None) into the request queue, indicating that the thread should
        cease processing further requests.
        """
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
        
        agent.start("What is the stock price of Tesla?")
        ```
    """
    
    def __init__(self, command_or_string=None, args=None, *, command=None, **kwargs):
        """
        Initialize the MCP instance with command parsing and dynamic tool generation.
        
        This method configures the MCP connection by interpreting command inputs. It accepts
        either a complete command string—which is split into a command and its arguments—or
        separate command and argument values. An alternative parameter name 'command' is also
        supported for backward compatibility. The method sets up the server parameters, starts
        the MCP tool runner, and waits up to 30 seconds for initialization, printing a warning
        if the process times out.
        
        Args:
            command_or_string: A command executable or a complete command line to launch the
                MCP server. When provided as a string without separate arguments, it is split
                into the executable and its arguments.
            args: A list of arguments to pass to the command when it is provided separately.
            command: An alternative name for 'command_or_string' for backward compatibility.
            **kwargs: Additional keyword arguments passed to StdioServerParameters.
        
        Raises:
            ValueError: If the provided command string is empty after parsing.
        """
        # Handle backward compatibility with named parameter 'command'
        if command_or_string is None and command is not None:
            command_or_string = command
        
        # Handle the single string format
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
            
        self.server_params = StdioServerParameters(
            command=cmd,
            args=arguments,
            **kwargs
        )
        self.runner = MCPToolRunner(self.server_params)
        
        # Wait for initialization
        if not self.runner.initialized.wait(timeout=30):
            print("Warning: MCP initialization timed out")
        
        # Generate tool functions immediately and store them
        self._tools = self._generate_tool_functions()
    
    def _generate_tool_functions(self) -> List[Callable]:
        """
        Generates callable wrappers for each available MCP tool.
        
        This method iterates over the tools provided by the MCP runner and creates a wrapper
        function for each using the _create_tool_wrapper method. The returned functions can be
        invoked directly to execute the corresponding MCP tool with the appropriate input schema.
        
        Returns:
            List[Callable]: A list of callable wrappers for MCP tools.
        """
        tool_functions = []
        
        for tool in self.runner.tools:
            wrapper = self._create_tool_wrapper(tool)
            tool_functions.append(wrapper)
        
        return tool_functions
    
    def _create_tool_wrapper(self, tool):
        """
        Creates a dynamic wrapper for an MCP tool.
        
        This function builds a callable that conforms to the tool's interface as defined
        by its input schema. It extracts parameter names, types, and required status from
        the tool's schema and constructs a wrapper with a matching signature and
        documentation. When invoked, the wrapper maps positional and keyword arguments
        to the expected parameters and calls the tool via the runner.
        
        Parameters:
            tool: An MCP tool object with attributes 'name', 'description', and 
                  'inputSchema'. The inputSchema should include a "properties" dictionary 
                  that defines parameter types and an optional "required" list for mandatory
                  parameters.
        
        Returns:
            A callable that wraps the tool, allowing it to be invoked with a signature
            that reflects its defined input parameters.
        """
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
            """
            Template function that accepts arbitrary arguments.
            
            This placeholder function is intended for future extension and currently does not perform any operation; it always returns None.
            """
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
            """
            Invokes a tool using combined positional and keyword arguments.
            
            This wrapper maps positional arguments to their corresponding expected
            parameter names, merges them with any keyword arguments, and delegates
            the call to the tool via the runner using the tool's name.
            
            Args:
                *args: Positional values for the tool's parameters.
                **kwargs: Keyword arguments for the tool.
            
            Returns:
                The result of executing the tool.
            """
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
    
    def __iter__(self) -> Iterable[Callable]:
        """
        Allow the MCP instance to be used directly as an iterable of tools.
        
        This makes it possible to pass the MCP instance directly to the Agent's tools parameter.
        """
        return iter(self._tools)
    
    def __del__(self):
        """
        Clean up resources when the MCP instance is garbage collected.
        
        If the instance has an associated runner, its shutdown method is called to halt
        ongoing operations and release allocated resources.
        """
        if hasattr(self, 'runner'):
            self.runner.shutdown() 