import subprocess
import logging
import json
from typing import List, Any, Dict, Callable
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='[%H:%M:%S]')
logger = logging.getLogger("npx-mcp-wrapper")

class MCP:
    """
    Wrapper class that integrates NPX-based MCP servers with the PraisonAI agent system.
    This provides a compatible interface for the Agent class to use MCP tools.
    
    This class handles the extraction of tool definitions from MCP servers and creates:
    1. Tool definitions in the global namespace for Agent._generate_tool_definition to find
    2. Callable wrappers for each tool that can be invoked by the Agent
    
    The tool definitions include parameter information formatted to match the expectations
    of the Agent class, ensuring proper argument passing when tools are invoked.
    """
    
    def __init__(self, command: str = "npx", args: List[str] = None, timeout: int = 180, debug: bool = False):
        """
        Initialize the NPX MCP wrapper.
        
        Args:
            command: The NPX command to run (default: "npx")
            args: List of arguments for the NPX command
            timeout: Timeout in seconds (default: 180)
            debug: Enable debug logging (default: False)
        """
        self.command = command
        self.args = args or []
        self.timeout = timeout
        self.debug = debug
        if debug:
            logging.getLogger("npx-mcp-wrapper").setLevel(logging.DEBUG)
            os.environ["DEBUG"] = "mcp:*"
        
        self._tools = []
        self._function_declarations = []
        
        # Initialize the MCP tools
        self._initialize_mcp_tools()
    
    def _initialize_mcp_tools(self):
        """
        Initialize the MCP tools by running a script that extracts the tool definitions.
        This approach avoids the complexity of managing async context managers.
        """
        try:
            # Create a temporary script to extract MCP tool definitions
            temp_script = """
import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def extract_tools(command, args):
    # Create server parameters
    server_params = StdioServerParameters(
        command=command,
        args=args
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize connection
                await session.initialize()
                
                # Get available tools
                mcp_tools = await session.list_tools()
                
                # Convert MCP tools to function declarations with detailed schema
                function_declarations = []
                for tool in mcp_tools.tools:
                    # Make sure parameters are properly formatted
                    parameters = tool.inputSchema
                    if not parameters.get("properties"):
                        parameters = {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    
                    # Add the tool declaration
                    function_declarations.append({
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": parameters
                    })
                
                # Print the function declarations as JSON
                print(json.dumps(function_declarations))
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    command = sys.argv[1]
    args = sys.argv[2:]
    asyncio.run(extract_tools(command, args))
"""
            
            # Write the temporary script to a file
            temp_script_path = os.path.join(os.path.dirname(__file__), "_temp_extract_mcp_tools.py")
            with open(temp_script_path, "w") as f:
                f.write(temp_script)
            
            # Run the temporary script to extract the tool definitions
            cmd = ["python", temp_script_path, self.command] + self.args
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            
            # Remove the temporary script
            os.remove(temp_script_path)
            
            if result.returncode != 0:
                logger.error(f"Error extracting MCP tools: {result.stderr}")
                raise RuntimeError(f"Failed to extract MCP tools: {result.stderr}")
            
            # Parse the function declarations from the script output
            self._function_declarations = json.loads(result.stdout.strip())
            
            # Create tool wrappers for each function declaration
            for func_decl in self._function_declarations:
                tool_name = func_decl["name"]
                self._tools.append(self._create_tool_wrapper(tool_name, func_decl))
                
                # Create a tool definition function in the global namespace
                self._create_tool_definition_function(tool_name, func_decl)
            
            logger.info(f"Initialized MCP tools: {[t.__name__ for t in self._tools]}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP tools: {e}")
            raise
    
    def _create_tool_wrapper(self, tool_name: str, func_decl: Dict[str, Any]) -> Callable:
        """
        Create a wrapper function for an MCP tool.
        
        Args:
            tool_name: The name of the tool
            func_decl: The function declaration for the tool
            
        Returns:
            A callable function that wraps the MCP tool
        """
        def wrapper(**kwargs) -> Any:
            # Create a temporary script to call the MCP tool
            temp_script = """
import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def call_tool(command, args, tool_name, kwargs):
    # Create server parameters
    server_params = StdioServerParameters(
        command=command,
        args=args
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize connection
                await session.initialize()
                
                # Call the tool
                result = await session.call_tool(tool_name, kwargs)
                
                # Extract the result content
                if result.isError:
                    error_msg = result.content[0].text if result.content else "Unknown error"
                    print(json.dumps({"error": error_msg}))
                else:
                    print(json.dumps({"result": result.content[0].text if result.content else ""}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    command = sys.argv[1]
    args = sys.argv[2:-2]
    tool_name = sys.argv[-2]
    kwargs_json = sys.argv[-1]
    kwargs = json.loads(kwargs_json)
    asyncio.run(call_tool(command, args, tool_name, kwargs))
"""
            
            try:
                # Write the temporary script to a file
                temp_script_path = os.path.join(os.path.dirname(__file__), f"_temp_call_mcp_tool_{tool_name}.py")
                with open(temp_script_path, "w") as f:
                    f.write(temp_script)
                
                # Run the temporary script to call the MCP tool
                cmd = ["python", temp_script_path, self.command] + self.args + [tool_name, json.dumps(kwargs)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
                
                # Remove the temporary script
                os.remove(temp_script_path)
                
                if result.returncode != 0:
                    logger.error(f"Error calling MCP tool {tool_name}: {result.stderr}")
                    return {"error": f"Failed to call MCP tool: {result.stderr}"}
                
                # Parse the result from the script output
                return json.loads(result.stdout.strip())
                
            except Exception as e:
                logger.error(f"Error calling MCP tool {tool_name}: {e}")
                return {"error": str(e)}
        
        # Set the name and docstring for the wrapper function
        wrapper.__name__ = tool_name
        wrapper.__doc__ = func_decl.get("description", f"Call the {tool_name} tool on the MCP server")
        
        return wrapper
    
    def __iter__(self):
        """Make the wrapper iterable to work with the agent system."""
        return iter(self._tools)
    
    def _create_tool_definition_function(self, tool_name, func_decl):
        """
        Create a tool definition function in the global namespace.
        This allows the Agent._generate_tool_definition method to find the tool definition.
        
        Args:
            tool_name: The name of the tool
            func_decl: The function declaration for the tool
        """
        # Create the tool definition
        tool_def = {
            "type": "function",
            "function": func_decl
        }
        
        # Store the tool definition in the global namespace directly
        # This way Agent._generate_tool_definition can find it
        tool_def_name = f"{tool_name}_definition"
        setattr(sys.modules["__main__"], tool_def_name, tool_def)
        globals()[tool_def_name] = tool_def
        
        logger.debug(f"Created tool definition: {tool_def_name}")
    
    def to_openai_tool(self):
        """Return the function declarations as OpenAI tools."""
        return [
            {
                "type": "function",
                "function": func_decl
            }
            for func_decl in self._function_declarations
        ]
