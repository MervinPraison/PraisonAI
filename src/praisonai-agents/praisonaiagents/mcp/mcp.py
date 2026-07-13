import asyncio
import threading
import queue
import time
import inspect
import shlex
import logging
from praisonaiagents._logging import get_logger
import os
import re
import platform
from typing import Any, List, Optional, Callable, Iterable, Union
from functools import wraps, partial

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None

class MCPToolRunner(threading.Thread):
    """A dedicated thread for running MCP operations."""
    
    def __init__(self, server_params, timeout=60):
        super().__init__(daemon=True)
        self.server_params = server_params
        self.queue = queue.Queue()
        self.initialized = threading.Event()
        self._init_error = None
        self.tools = []
        self.resources = []
        self.resource_templates = []
        self.prompts = []
        self.timeout = timeout
        self._tool_timings = {}
        self._timings_lock = threading.Lock()
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

                    # Best-effort capability negotiation for resources and prompts.
                    # Servers that do not advertise these capabilities simply
                    # leave the corresponding lists empty (tools-only servers are
                    # unaffected).
                    await self._discover_resources_and_prompts(session)

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
                                
                                response_queue, kind, name, arguments = item
                                try:
                                    if kind == "resource":
                                        result = await session.read_resource(name)
                                    elif kind == "prompt":
                                        result = await session.get_prompt(name, arguments or None)
                                    else:
                                        result = await session.call_tool(name, arguments)
                                    response_queue.put((True, result))
                                except Exception as e:
                                    response_queue.put((False, str(e)))
                            except queue.Empty:
                                pass
                            
                            # Give other tasks a chance to run
                            await asyncio.sleep(0.01)
                        except asyncio.CancelledError:
                            break
        except Exception as e:
            self._init_error = f"MCP initialization error: {str(e)}"
            self.initialized.set()  # Ensure we don't hang

    async def _discover_resources_and_prompts(self, session):
        """Enumerate server resources, resource templates and prompts.

        Each call is guarded independently so a server that supports only a
        subset of primitives (or none) still initializes cleanly. Failures are
        logged at debug level and leave the corresponding list empty.
        """
        try:
            resources_result = await session.list_resources()
            self.resources = list(getattr(resources_result, "resources", []) or [])
        except Exception as e:
            logging.debug(f"MCP list_resources unavailable: {e}")

        try:
            templates_result = await session.list_resource_templates()
            self.resource_templates = list(
                getattr(templates_result, "resourceTemplates", []) or []
            )
        except Exception as e:
            logging.debug(f"MCP list_resource_templates unavailable: {e}")

        try:
            prompts_result = await session.list_prompts()
            self.prompts = list(getattr(prompts_result, "prompts", []) or [])
        except Exception as e:
            logging.debug(f"MCP list_prompts unavailable: {e}")

    def _dispatch(self, kind, name, arguments):
        """Send a request to the runner thread and wait for its result.

        Args:
            kind: One of ``"tool"``, ``"resource"`` or ``"prompt"``.
            name: Tool name, resource URI, or prompt name.
            arguments: Argument mapping (tools/prompts) or ``None``.

        Returns:
            The raw MCP result object on success, or ``(False, message)`` on
            failure so callers can format errors consistently.
        """
        if not self.initialized.is_set():
            self.initialized.wait(timeout=self.timeout)
            if not self.initialized.is_set():
                return (False, f"MCP initialization timed out after {self.timeout} seconds")

        if self._init_error:
            return (False, self._init_error)

        response_queue = queue.Queue(maxsize=1)
        self.queue.put((response_queue, kind, name, arguments))
        try:
            success, result = response_queue.get(timeout=self.timeout)
        except queue.Empty:
            return (False, f"MCP {kind} call timed out after {self.timeout} seconds")
        if not success:
            return (False, result)
        return result

    def read_resource(self, uri):
        """Read an MCP resource by URI and return its normalised contents."""
        from .resources import normalize_resource_result
        result = self._dispatch("resource", uri, None)
        if isinstance(result, tuple) and result and result[0] is False:
            return f"Error: {result[1]}"
        return normalize_resource_result(result)

    def get_prompt(self, name, arguments=None):
        """Fetch an MCP prompt template rendered with ``arguments``."""
        from .resources import normalize_prompt_result
        result = self._dispatch("prompt", name, arguments or {})
        if isinstance(result, tuple) and result and result[0] is False:
            return f"Error: {result[1]}"
        return normalize_prompt_result(result)

    def call_tool(self, tool_name, arguments):
        """Call an MCP tool and wait for the result."""
        # Import telemetry here to avoid circular imports
        try:
            from ..telemetry.telemetry import get_telemetry
            telemetry = get_telemetry()
        except (ImportError, AttributeError):
            telemetry = None
        
        # Check initialization first (without timing)
        if not self.initialized.is_set():
            self.initialized.wait(timeout=self.timeout)
            if not self.initialized.is_set():
                # Track initialization timeout failure
                if telemetry:
                    telemetry.track_tool_usage(tool_name, success=False, execution_time=0)
                return f"Error: MCP initialization timed out after {self.timeout} seconds"

        if self._init_error:
            if telemetry:
                telemetry.track_tool_usage(tool_name, success=False, execution_time=0)
            return f"Error: {self._init_error}"
        
        # Start timing after initialization check
        start_time = time.time()
        is_success = False
        response_queue = queue.Queue(maxsize=1)
        try:
            # Put request in queue with caller-specific response channel
            self.queue.put((response_queue, "tool", tool_name, arguments))
            
            # Wait for result with timeout
            try:
                success, result = response_queue.get(timeout=self.timeout)
            except queue.Empty:
                return f"Error: MCP tool call timed out after {self.timeout} seconds"
            if not success:
                return f"Error: {result}"
            
            # Process result
            if hasattr(result, 'content') and result.content:
                if hasattr(result.content[0], 'text'):
                    processed_result = result.content[0].text
                else:
                    processed_result = str(result.content[0])
            else:
                processed_result = str(result)
            
            is_success = True
            return processed_result
            
        except Exception as e:
            return f"Error: {str(e)}"
        finally:
            # Track timing regardless of success/failure
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Log timing information for debugging
            logging.debug(f"Tool '{tool_name}' execution time: {execution_time:.3f} seconds")
            
            # Store timing in thread-safe manner
            with self._timings_lock:
                self._tool_timings[tool_name] = execution_time
            
            # Track tool usage with timing information
            if telemetry:
                telemetry.track_tool_usage(tool_name, success=is_success, execution_time=execution_time)
    
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
    
    def __init__(self, command_or_string=None, args=None, *, command=None, timeout=60, debug=False, 
                 allowed_tools: Optional[List[str]] = None, disabled_tools: Optional[List[str]] = None, **kwargs):
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
            allowed_tools: Include whitelist - only these tools will be available (default: None = all tools)
            disabled_tools: Exclude blacklist - these tools will be filtered out (default: None = no exclusions)
            **kwargs: Additional parameters for StdioServerParameters
            
        Note:
            If both allowed_tools and disabled_tools are specified, allowed_tools takes precedence
            (include wins over exclude).
        """
        # Check if MCP is available
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP (Model Context Protocol) package is not installed. "
                "Install it with: pip install praisonaiagents[mcp]"
            )

        # Handle backward compatibility with named parameter 'command'
        if command_or_string is None and command is not None:
            command_or_string = command

        # Set up logging - default to WARNING level to hide INFO messages
        if debug:
            get_logger("mcp-wrapper").setLevel(logging.DEBUG)
            get_logger("mcp-sse").setLevel(logging.DEBUG)
            get_logger("mcp.client").setLevel(logging.DEBUG)
            get_logger("sse").setLevel(logging.DEBUG)
            get_logger("mcp-server").setLevel(logging.DEBUG)
            get_logger("mcp-client").setLevel(logging.DEBUG)
            get_logger("_client").setLevel(logging.DEBUG)
            get_logger("httpx").setLevel(logging.DEBUG)
            get_logger("llm").setLevel(logging.DEBUG)
        else:
            # Set all MCP-related loggers to WARNING level by default
            get_logger("mcp-wrapper").setLevel(logging.WARNING)
            get_logger("mcp-sse").setLevel(logging.WARNING)
            get_logger("mcp.client").setLevel(logging.WARNING)
            get_logger("sse").setLevel(logging.WARNING)
            get_logger("mcp-server").setLevel(logging.WARNING)
            get_logger("mcp-client").setLevel(logging.WARNING)
            get_logger("_client").setLevel(logging.WARNING)
            get_logger("httpx").setLevel(logging.WARNING)
            get_logger("llm").setLevel(logging.WARNING)
        
        # Store additional parameters
        self.timeout = timeout
        self.debug = debug
        self.allowed_tools = allowed_tools
        self.disabled_tools = disabled_tools

        # Optional prefix applied to tool names to avoid cross-server collisions
        # when multiple MCP servers are loaded together (see load_mcp_tools).
        self._tool_prefix: Optional[str] = None
        
        # Check if this is a WebSocket URL (ws:// or wss://)
        if isinstance(command_or_string, str) and re.match(r'^wss?://', command_or_string):
            from .mcp_websocket import WebSocketMCPClient
            # Extract auth token if provided
            auth_token = kwargs.pop('auth_token', None)
            
            self.websocket_client = WebSocketMCPClient(
                command_or_string,
                debug=debug,
                timeout=timeout,
                auth_token=auth_token,
                options=kwargs
            )
            self._tools = self._apply_tool_filters(list(self.websocket_client.tools))
            self.is_sse = False
            self.is_http_stream = False
            self.is_websocket = True
            self.is_npx = False
            return
        
        # Check if this is an HTTP URL
        if isinstance(command_or_string, str) and re.match(r'^https?://', command_or_string):
            # Determine transport type based on URL or kwargs
            if command_or_string.endswith('/sse') and 'transport_type' not in kwargs:
                # Legacy SSE URL - use SSE transport for backward compatibility
                from .mcp_sse import SSEMCPClient
                self.sse_client = SSEMCPClient(command_or_string, debug=debug, timeout=timeout)
                self._tools = self._apply_tool_filters(list(self.sse_client.tools))
                self.is_sse = True
                self.is_http_stream = False
                self.is_npx = False
                return
            else:
                # Use HTTP Stream transport for all other HTTP URLs
                from .mcp_http_stream import HTTPStreamMCPClient
                # Extract transport options from kwargs
                transport_options = {}
                if 'responseMode' in kwargs:
                    transport_options['responseMode'] = kwargs.pop('responseMode')
                if 'headers' in kwargs:
                    transport_options['headers'] = kwargs.pop('headers')
                if 'cors' in kwargs:
                    transport_options['cors'] = kwargs.pop('cors')
                if 'session' in kwargs:
                    transport_options['session'] = kwargs.pop('session')
                if 'resumability' in kwargs:
                    transport_options['resumability'] = kwargs.pop('resumability')
                
                self.http_stream_client = HTTPStreamMCPClient(
                    command_or_string, 
                    debug=debug, 
                    timeout=timeout,
                    options=transport_options
                )
                self._tools = self._apply_tool_filters(list(self.http_stream_client.tools))
                self.is_sse = False
                self.is_http_stream = True
                self.is_npx = False
                return
            
        # Handle the single string format for stdio client
        if isinstance(command_or_string, str) and args is None:
            # Split the string into command and args using shell-like parsing
            if platform.system() == 'Windows':
                # Use shlex with posix=False for Windows to handle quotes and paths with spaces
                parts = shlex.split(command_or_string, posix=False)
                # Remove quotes from parts if present (Windows shlex keeps them)
                parts = [part.strip('"') for part in parts]
            else:
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
        self.is_http_stream = False
        
        # Build safe environment for stdio MCP servers
        # Use safe baseline + explicit env from config (B5 security policy)
        custom_env = kwargs.get('env', {})
        env = self._build_safe_env(custom_env)
        
        kwargs['env'] = env
        
        self.server_params = StdioServerParameters(
            command=cmd,
            args=arguments,
            **kwargs
        )
        self.runner = MCPToolRunner(self.server_params, timeout)
        
        # Wait for initialization
        if not self.runner.initialized.wait(timeout=self.timeout):
            print(f"Warning: MCP initialization timed out after {self.timeout} seconds")
        
        # Automatically detect if this is an NPX command
        base_cmd = os.path.basename(cmd) if isinstance(cmd, str) else cmd
        # Check for npx with or without Windows extensions
        npx_variants = ['npx', 'npx.cmd', 'npx.exe']
        if platform.system() == 'Windows' and isinstance(base_cmd, str):
            # Case-insensitive comparison on Windows
            self.is_npx = base_cmd.lower() in [v.lower() for v in npx_variants]
        else:
            self.is_npx = base_cmd in npx_variants
        
        # For NPX-based MCP servers, use a different approach
        if self.is_npx:
            self._function_declarations = []
            self._initialize_npx_mcp_tools(cmd, arguments)
        else:
            # Generate tool functions immediately and store them
            self._tools = self._apply_tool_filters(self._generate_tool_functions())
    
    def _generate_tool_functions(self) -> List[Callable]:
        """
        Generate functions for each MCP tool.
        
        Returns:
            List[Callable]: Functions that can be used as tools
        """
        if self.is_sse:
            return list(self.sse_client.tools)
        
        if self.is_http_stream:
            return list(self.http_stream_client.tools)
            
        tool_functions = []
        
        for tool in self.runner.tools:
            wrapper = self._create_tool_wrapper(tool)
            tool_functions.append(wrapper)

        # Register synthetic, agent-callable tools for MCP resources and
        # prompts, but only when the connected server actually advertises them
        # (tools-only servers are unaffected — no extra tools appear).
        tool_functions.extend(self._generate_resource_tools())

        return tool_functions

    def _generate_resource_tools(self) -> List[Callable]:
        """Build synthetic tools for resources/prompts advertised by the server.

        Returns an empty list when the server exposes neither, so existing
        tools-only configurations behave exactly as before.
        """
        runner = getattr(self, "runner", None)
        if runner is None:
            return []

        from . import resources as _res

        synthetic: List[Callable] = []
        has_resources = bool(runner.resources or runner.resource_templates)
        has_prompts = bool(runner.prompts)

        if has_resources:
            def list_mcp_resources() -> str:
                """List the resources available from the connected MCP server."""
                return _res.to_json(_res.resources_to_dicts(runner.resources))

            def list_mcp_resource_templates() -> str:
                """List the resource templates available from the MCP server."""
                return _res.to_json(
                    _res.resource_templates_to_dicts(runner.resource_templates)
                )

            def read_mcp_resource(uri: str) -> str:
                """Read a resource from the MCP server by its URI."""
                return runner.read_resource(uri)

            synthetic.extend(
                [list_mcp_resources, list_mcp_resource_templates, read_mcp_resource]
            )

        if has_prompts:
            def list_mcp_prompts() -> str:
                """List the prompt templates available from the MCP server."""
                return _res.to_json(_res.prompts_to_dicts(runner.prompts))

            def get_mcp_prompt(name: str, arguments: dict = None) -> str:
                """Fetch an MCP prompt template rendered with the given arguments."""
                return runner.get_prompt(name, arguments or {})

            synthetic.extend([list_mcp_prompts, get_mcp_prompt])

        return synthetic

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
        # Separate required and optional parameters to ensure proper ordering
        # (required parameters must come before optional parameters)
        required_param_objects = []
        optional_param_objects = []
        
        for name in param_names:
            is_required = name in required_params
            param = inspect.Parameter(
                name=name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty if is_required else None,
                annotation=param_annotations.get(name, Any)
            )
            
            if is_required:
                required_param_objects.append(param)
            else:
                optional_param_objects.append(param)
        
        # Combine parameters with required first, then optional
        params = required_param_objects + optional_param_objects
        
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
            self._tools = self._apply_tool_filters(self._generate_tool_functions())
            
            if self.debug:
                logging.debug(f"Generated {len(self._tools)} NPX MCP tools")
                
        except Exception as e:
            if self.debug:
                logging.error(f"Failed to initialize NPX MCP tools: {e}")
            raise RuntimeError(f"Failed to initialize NPX MCP tools: {e}")
    
    def _apply_tool_filters(self, raw_tools: List[Any]) -> List[Any]:
        """
        Apply tool filtering based on allowed_tools and disabled_tools.
        
        Args:
            raw_tools: Unfiltered tool list
            
        Returns:
            Filtered tool list
        """
        if not self.allowed_tools and not self.disabled_tools:
            return raw_tools
            
        # Import filter functions
        from .mcp_utils import filter_tools_by_allowlist, filter_disabled_tools
        
        # Convert tools to the format expected by filter functions (list of dicts with 'name')
        # Raw tools might be function objects, so we need to extract names
        tool_defs = []
        for tool in raw_tools:
            if hasattr(tool, '__name__'):
                tool_defs.append({"name": tool.__name__, "_tool_obj": tool})
            elif isinstance(tool, dict) and 'name' in tool:
                tool_defs.append(tool)
            else:
                # Skip tools that don't have a clear name
                continue
        
        # Include wins over exclude - apply allowlist exclusively if provided
        if self.allowed_tools:
            tool_defs = filter_tools_by_allowlist(tool_defs, self.allowed_tools)
        elif self.disabled_tools:
            tool_defs = filter_disabled_tools(tool_defs, self.disabled_tools)
        
        # Convert back to original format
        filtered_tools = []
        for tool_def in tool_defs:
            if "_tool_obj" in tool_def:
                filtered_tools.append(tool_def["_tool_obj"])
            else:
                filtered_tools.append(tool_def)
        
        return filtered_tools

    def apply_tool_filters(
        self,
        allowed_tools: Optional[List[str]] = None,
        disabled_tools: Optional[List[str]] = None,
    ) -> "MCP":
        """Public API to (re)apply allow/deny tool filters to this instance.

        Lets callers (e.g. the loader) express include/exclude intent without
        reaching into private state. ``allowed_tools`` wins over
        ``disabled_tools`` when both are supplied.

        Args:
            allowed_tools: Only these tool names are kept (allowlist).
            disabled_tools: These tool names are removed (denylist).

        Returns:
            self, to allow fluent chaining.
        """
        if allowed_tools is not None:
            self.allowed_tools = allowed_tools
        if disabled_tools is not None:
            self.disabled_tools = disabled_tools
        if self.allowed_tools or self.disabled_tools:
            self._tools = self._apply_tool_filters(self._tools)
        return self

    def _build_safe_env(self, custom_env: Optional[dict] = None) -> dict:
        """
        Build a safe environment for stdio MCP servers.
        
        Merges only safe baseline environment variables with explicit custom ones,
        following the security policy outlined in AGENTS.md.
        
        Args:
            custom_env: Optional custom environment variables from config
            
        Returns:
            Safe environment dictionary
        """
        # Safe baseline environment variables
        safe_baseline = {
            'PATH': os.environ.get('PATH', ''),
            'HOME': os.environ.get('HOME', os.path.expanduser('~')),
            'USER': os.environ.get('USER', ''),
            'LANG': os.environ.get('LANG', 'C.UTF-8'),
            'LC_ALL': os.environ.get('LC_ALL', 'C.UTF-8'),
            'PYTHONIOENCODING': 'utf-8',
        }
        
        # Platform-specific safe variables
        if platform.system() == 'Windows':
            safe_baseline.update({
                'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),
                'COMSPEC': os.environ.get('COMSPEC', ''),
                'USERNAME': os.environ.get('USERNAME', ''),
                'USERPROFILE': os.environ.get('USERPROFILE', ''),
                'APPDATA': os.environ.get('APPDATA', ''),
                'LOCALAPPDATA': os.environ.get('LOCALAPPDATA', ''),
                'TEMP': os.environ.get('TEMP', ''),
                'TMP': os.environ.get('TMP', ''),
            })
        else:
            safe_baseline.update({
                'TMPDIR': os.environ.get('TMPDIR', '/tmp'),
                'SHELL': os.environ.get('SHELL', '/bin/sh'),
            })
        
        # Start with safe baseline
        env = {k: v for k, v in safe_baseline.items() if v}  # Only include non-empty values
        
        # Add explicit custom environment variables from config
        if custom_env:
            env.update(custom_env)
        
        return env

    def __iter__(self) -> Iterable[Callable]:
        """
        Allow the MCP instance to be used directly as an iterable of tools.
        
        This makes it possible to pass the MCP instance directly to the Agent's tools parameter.
        """
        return iter(self._tools)
    
    @staticmethod
    def _sanitize_prefix(prefix: str) -> str:
        """Sanitize a server name into a safe tool-name prefix."""
        sanitized = re.sub(r"[^0-9A-Za-z_]", "_", prefix or "")
        return sanitized.strip("_")

    def _prefixed_name(self, original_name: str) -> str:
        """Return the namespaced tool name for an original server-side name."""
        if not self._tool_prefix:
            return original_name
        return f"{self._tool_prefix}_{original_name}"

    def with_tool_prefix(self, prefix: str) -> "MCP":
        """
        Namespace this server's tool names with ``<prefix>_`` to avoid
        collisions when multiple MCP servers are loaded together.

        Both the callable tool names (``__name__``) and the OpenAI schema
        names produced by :meth:`to_openai_tool` are prefixed, while calls
        are still dispatched to the original server-side tool names.

        Args:
            prefix: The server name to derive the prefix from. It is
                sanitized to contain only ``[0-9A-Za-z_]`` characters.

        Raises:
            ValueError: If ``prefix`` sanitizes to an empty string, since an
                empty prefix would silently reintroduce the cross-server name
                collisions this method exists to prevent.

        Returns:
            self, to allow fluent chaining.
        """
        sanitized = self._sanitize_prefix(prefix)
        if not sanitized:
            raise ValueError(
                f"Cannot derive a valid tool prefix from server name {prefix!r}; "
                "provide a name containing at least one alphanumeric or "
                "underscore character."
            )

        self._tool_prefix = sanitized

        # Rename already-generated callable tools. Dispatch inside each
        # wrapper closes over the original tool name, so only the public
        # __name__/__qualname__ needs updating for schema construction.
        for tool in getattr(self, "_tools", []) or []:
            if callable(tool) and hasattr(tool, "__name__"):
                original = getattr(tool, "__original_name__", tool.__name__)
                tool.__original_name__ = original
                new_name = f"{sanitized}_{original}"
                tool.__name__ = new_name
                try:
                    tool.__qualname__ = new_name
                except (AttributeError, TypeError):
                    pass

        return self

    def get_tools(self) -> List[Callable]:
        """
        Get the list of tool functions from this MCP instance.
        
        This method provides explicit access to the tools list, which is useful
        when you need to inspect or manipulate the tools programmatically.
        
        Returns:
            List[Callable]: List of tool functions that can be called
            
        Example:
            ```python
            mcp = MCP("npx -y @modelcontextprotocol/server-time")
            tools = mcp.get_tools()
            for tool in tools:
                print(f"Tool: {tool.__name__}")
            ```
        """
        return self._tools

    def get_resources(self) -> List[dict]:
        """List resources/resource-templates advertised by the MCP server.

        Returns an empty list for transports that do not surface resources or
        for tools-only servers.

        Returns:
            List[dict]: Serialised resource and resource-template descriptors.
        """
        from . import resources as _res
        runner = getattr(self, "runner", None)
        if runner is None:
            return []
        return (
            _res.resources_to_dicts(runner.resources)
            + _res.resource_templates_to_dicts(runner.resource_templates)
        )

    def get_prompts(self) -> List[dict]:
        """List prompt templates advertised by the MCP server.

        Returns an empty list for transports that do not surface prompts or for
        servers that expose none.

        Returns:
            List[dict]: Serialised prompt descriptors with argument hints.
        """
        from . import resources as _res
        runner = getattr(self, "runner", None)
        if runner is None:
            return []
        return _res.prompts_to_dicts(runner.prompts)
    
    def _fix_array_schemas(self, schema):
        """
        Fix array schemas by adding missing 'items' attribute required by OpenAI.

        Thin wrapper around the shared ``fix_array_schemas`` helper, kept for
        backward compatibility with any external subclassing.

        Args:
            schema: The schema dictionary to fix

        Returns:
            dict: The fixed schema
        """
        from ..llm.schema_utils import fix_array_schemas
        return fix_array_schemas(schema)
    
    def to_openai_tool(self):
        """Convert the MCP tool to an OpenAI-compatible tool definition.
        
        This method is specifically invoked by the Agent class when using
        provider/model format (e.g., "openai/gpt-4o-mini").
        
        Returns:
            dict or list: OpenAI-compatible tool definition(s)
        """
        if self.is_sse and hasattr(self, 'sse_client') and self.sse_client.tools:
            # Return all tools from SSE client
            return self._apply_prefix_to_openai_tools(self.sse_client.to_openai_tools())
        
        if self.is_http_stream and hasattr(self, 'http_stream_client') and self.http_stream_client.tools:
            # Return all tools from HTTP Stream client
            return self._apply_prefix_to_openai_tools(self.http_stream_client.to_openai_tools())
            
        # Synthetic resource/prompt tools (if the server advertises them) are
        # captured up front so resource-only servers still expose something.
        synthetic_tools = self._synthetic_resource_openai_tools()

        # For simplicity, we'll convert the first tool only if multiple exist
        # More complex implementations could handle multiple tools
        if not hasattr(self, 'runner') or not self.runner.tools:
            if synthetic_tools:
                return synthetic_tools
            logging.warning("No MCP tools available to convert to OpenAI format")
            return None
            
        # Convert all tools to OpenAI format
        openai_tools = []
        for tool in self.runner.tools:
            # Create OpenAI tool definition
            parameters = {}
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                # Fix array schemas to include 'items' attribute
                parameters = self._fix_array_schemas(tool.inputSchema)
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
                    "name": self._prefixed_name(tool.name),
                    "description": tool.description if hasattr(tool, 'description') else f"Call the {tool.name} tool",
                    "parameters": parameters
                },
                "__praisonai_deferrable__": True  # Mark MCP tools as deferrable for tool search
            })

        openai_tools.extend(synthetic_tools)

        return openai_tools

    # Names of the synthetic resource/prompt tools generated by
    # _generate_resource_tools. Used to distinguish them from server tools
    # (which live in self.runner.tools) when building OpenAI schemas.
    _SYNTHETIC_TOOL_NAMES = {
        "list_mcp_resources",
        "list_mcp_resource_templates",
        "read_mcp_resource",
        "list_mcp_prompts",
        "get_mcp_prompt",
    }

    def _synthetic_resource_openai_tools(self):
        """Build OpenAI schemas for the synthetic MCP resource/prompt tools.

        Derives schemas from the callables' own signatures so their names stay
        in sync with the configured tool prefix and any applied filtering.
        """
        server_tool_names = {
            getattr(t, "name", None) for t in getattr(getattr(self, "runner", None), "tools", []) or []
        }

        schemas = []
        for fn in getattr(self, "_tools", []) or []:
            original = getattr(fn, "__original_name__", getattr(fn, "__name__", ""))
            if original not in self._SYNTHETIC_TOOL_NAMES or original in server_tool_names:
                continue

            properties = {}
            required = []
            try:
                sig = inspect.signature(fn)
                for pname, param in sig.parameters.items():
                    ptype = "object" if pname == "arguments" else "string"
                    properties[pname] = {"type": ptype}
                    if param.default is inspect.Parameter.empty:
                        required.append(pname)
            except (ValueError, TypeError):
                pass

            schemas.append({
                "type": "function",
                "function": {
                    "name": getattr(fn, "__name__", original),
                    "description": (fn.__doc__ or f"Call the {original} tool").strip(),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
                "__praisonai_deferrable__": True,
            })

        return schemas

    def _apply_prefix_to_openai_tools(self, openai_tools):
        """Apply the configured tool prefix to OpenAI schema tool names.

        Used for transports (SSE/HTTP/WebSocket) whose clients build their
        own OpenAI schemas so their names stay in sync with the prefixed
        callable ``__name__`` values consumed during dispatch.

        Returns a new list with copied dicts so the call is idempotent and
        never mutates the clients' internal tool representations (avoids
        double-prefixing if a client caches its schema dicts).
        """
        if not self._tool_prefix or not openai_tools:
            return openai_tools

        is_list = isinstance(openai_tools, list)
        items = openai_tools if is_list else [openai_tools]
        result = []
        for item in items:
            if isinstance(item, dict):
                item = dict(item)
                fn = item.get("function")
                if isinstance(fn, dict) and fn.get("name"):
                    item["function"] = dict(fn)
                    item["function"]["name"] = self._prefixed_name(fn["name"])
            result.append(item)

        return result if is_list else result[0]
    
    def __enter__(self):
        """Context manager entry - return self for use in 'with' statements."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up resources."""
        self.shutdown()
        return False  # Don't suppress exceptions
    
    def shutdown(self):
        """Explicitly shut down MCP resources.
        
        Call this method when done using the MCP instance to ensure
        all background threads and connections are properly cleaned up.
        """
        # Shutdown stdio runner if present
        if hasattr(self, 'runner') and self.runner is not None:
            try:
                self.runner.shutdown()
            except Exception:
                pass  # Best effort cleanup
        
        # Shutdown SSE client if present
        if hasattr(self, 'sse_client') and self.sse_client is not None:
            try:
                if hasattr(self.sse_client, 'shutdown'):
                    self.sse_client.shutdown()
            except Exception:
                pass
        
        # Shutdown HTTP stream client if present
        if hasattr(self, 'http_stream_client') and self.http_stream_client is not None:
            try:
                if hasattr(self.http_stream_client, 'shutdown'):
                    self.http_stream_client.shutdown()
            except Exception:
                pass
        
        # Shutdown WebSocket client if present
        if hasattr(self, 'websocket_client') and self.websocket_client is not None:
            try:
                if hasattr(self.websocket_client, 'shutdown'):
                    self.websocket_client.shutdown()
            except Exception:
                pass
    
    def __del__(self):
        """Clean up resources when the object is garbage collected.
        
        Note: __del__ is called during garbage collection and may not
        always run. For reliable cleanup, use the context manager
        pattern or call shutdown() explicitly.
        """
        try:
            self.shutdown()
        except Exception:
            pass  # Best effort cleanup in __del__