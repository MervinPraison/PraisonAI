"""
Server Adapter Implementation.

Provides a concrete implementation of ServerManagerProtocol that extracts
server management functionality from the Agent class.

This follows the protocol-driven architecture principle by moving heavy
implementation (FastAPI/uvicorn server management) into an adapter while
keeping the protocol lightweight.
"""
import logging
import threading
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent

logger = logging.getLogger(__name__)

# Global state for server management (matches Agent's original implementation)
_server_started = False
_registered_agents: Dict[int, Dict[str, str]] = {}  # port -> {path -> agent_id}
_shared_apps: Dict[int, Any] = {}  # port -> FastAPI app
_server_lock = threading.Lock()


class ServerAdapter:
    """
    Concrete implementation of ServerManagerProtocol.
    
    Extracts server management functionality from Agent class,
    maintaining backward compatibility while following protocol-driven design.
    """
    
    def launch(
        self,
        agent: 'Agent',
        path: str = "/",
        port: int = 8000,
        host: str = "0.0.0.0",
        debug: bool = False,
        protocol: str = "http"
    ) -> None:
        """
        Launch agent as HTTP API endpoint or MCP server.
        
        This is the extracted implementation from Agent.launch() method,
        maintaining full backward compatibility.
        """
        if protocol == "http":
            self._launch_http_server(agent, path, port, host, debug)
        elif protocol == "mcp":
            self._launch_mcp_server(agent, path, port, host, debug)
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")
    
    def _launch_http_server(
        self,
        agent: 'Agent',
        path: str,
        port: int,
        host: str,
        debug: bool
    ) -> None:
        """Launch HTTP FastAPI server."""
        global _server_started, _registered_agents, _shared_apps, _server_lock

        # Try to import FastAPI dependencies - lazy loading
        try:
            import uvicorn
            from fastapi import FastAPI, HTTPException, Request
            from fastapi.responses import JSONResponse
            from pydantic import BaseModel
            import asyncio
            
            # Define the request model here since we need pydantic
            class AgentQuery(BaseModel):
                query: str
                
        except ImportError as e:
            # Check which specific module is missing
            missing_module = str(e).split("No module named '")[-1].rstrip("'")
            # Use agent's display functions if available
            try:
                from ..main import display_error
                display_error(f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
            except ImportError:
                print(f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
            
            logging.error(f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
            print(f"\nTo add API capabilities, install the required dependencies:")
            print(f"pip install {missing_module}")
            print("\nOr install all API dependencies with:")
            print("pip install 'praisonaiagents[api]'")
            return None
            
        with _server_lock:
            # Initialize port-specific collections if needed
            if port not in _registered_agents:
                _registered_agents[port] = {}

            # Initialize shared FastAPI app if not already created for this port
            if _shared_apps.get(port) is None:
                _shared_apps[port] = FastAPI(
                    title=f"PraisonAI Agents API (Port {port})",
                    description="API for interacting with PraisonAI Agents"
                )

                # Add a root endpoint with a welcome message
                @_shared_apps[port].get("/")
                async def root():
                    return {
                        "message": f"Welcome to PraisonAI Agents API on port {port}. See /docs for usage.",
                        "endpoints": list(_registered_agents[port].keys())
                    }

                # Add healthcheck endpoint
                @_shared_apps[port].get("/health")
                async def healthcheck():
                    return {
                        "status": "ok",
                        "endpoints": list(_registered_agents[port].keys())
                    }

            # Normalize path to ensure it starts with /
            if not path.startswith('/'):
                path = f'/{path}'

            # Check if path is already registered for this port
            if path in _registered_agents[port]:
                logging.warning(f"Path '{path}' is already registered on port {port}. Please use a different path.")
                print(f"⚠️ Warning: Path '{path}' is already registered on port {port}.")
                # Use a modified path to avoid conflicts
                original_path = path
                path = f"{path}_{agent.agent_id[:6]}"
                logging.warning(f"Using '{path}' instead of '{original_path}'")
                print(f"🔄 Using '{path}' instead")

            # Register the agent to this path
            _registered_agents[port][path] = agent.agent_id

            # Define the endpoint handler
            @_shared_apps[port].post(path)
            async def handle_agent_query(request: Request, query_data: Optional[AgentQuery] = None):
                # Handle both direct JSON with query field and form data
                if query_data is None:
                    try:
                        request_data = await request.json()
                        if "query" not in request_data:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                        query = request_data["query"]
                    except Exception:
                        # Fallback to form data or query params
                        form_data = await request.form()
                        query = form_data.get("query") or request.query_params.get("query")
                        if not query:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request body, form data, or query parameters")
                else:
                    query = query_data.query

                try:
                    # Use agent's start method for the actual processing
                    response = agent.start(query)
                    return {"response": response, "agent": agent.name or "Agent"}
                except Exception as e:
                    logging.error(f"Error processing query for agent {agent.name}: {e}")
                    raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

            # Start the server if not already started for this port
            if not _server_started or _shared_apps.get(port) is None:
                def run_server():
                    try:
                        print(f"✅ FastAPI server started at http://{host}:{port}")
                        print(f"📖 API docs available at http://{host}:{port}/docs")
                        print(f"🔗 Agent endpoint: http://{host}:{port}{path}")
                        uvicorn.run(_shared_apps[port], host=host, port=port, log_level="debug" if debug else "info")
                    except Exception as e:
                        logging.error(f"Failed to start server: {e}")
                        print(f"❌ Failed to start server: {e}")
                        global _server_started
                        _server_started = False

                # Start server in a separate thread to avoid blocking
                server_thread = threading.Thread(target=run_server, daemon=True)
                server_thread.start()
                
                # Give the server a moment to start
                time.sleep(0.5)
                _server_started = True

    def _launch_mcp_server(
        self,
        agent: 'Agent',
        path: str,
        port: int,
        host: str,
        debug: bool
    ) -> None:
        """Launch MCP server."""
        try:
            import uvicorn
            from ..mcp.mcp_server import MCPServer, MCPTool
            
            # Create MCP server
            server = MCPServer(
                name=f"{agent.name}_mcp_server",
                version="1.0.0"
            )
            
            # Create MCP tool for the agent
            mcp_tool = MCPTool(
                name=f"{agent.name}_chat",
                description=f"Chat with {agent.name}",
                agent=agent
            )
            
            server.add_tool(mcp_tool)
            
            print(f"✅ MCP server started at http://{host}:{port}")
            print(f"🔗 Agent: {agent.name}")
            
            # Launch MCP server
            server.run(host=host, port=port)
            
        except ImportError as e:
            missing_module = str(e).split("No module named '")[-1].rstrip("'")
            print(f"\nTo add MCP capabilities, install the required dependencies:")
            print(f"pip install {missing_module} mcp praison-mcp starlette uvicorn")

    def stop_server(self, port: int = 8000) -> None:
        """Stop server on specified port."""
        global _server_started, _registered_agents, _shared_apps
        
        with _server_lock:
            if port in _shared_apps:
                # Clean up port-specific resources
                del _shared_apps[port]
                if port in _registered_agents:
                    del _registered_agents[port]
                
                # If no more servers, mark as stopped
                if not _shared_apps:
                    _server_started = False
                    
                print(f"🛑 Server stopped on port {port}")
            else:
                print(f"⚠️ No server running on port {port}")


# Create default instance
default_server_adapter = ServerAdapter()