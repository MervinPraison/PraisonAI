"""
Serve CLI Feature Handler

Provides CLI commands for launching PraisonAI servers:
- praisonai serve agents - Launch agents as HTTP API
- praisonai serve recipe - Launch recipe runner
- praisonai serve mcp - Launch MCP server
- praisonai serve tools - Launch tools as MCP server
- praisonai serve a2a - Launch A2A server
- praisonai serve a2u - Launch A2U event stream server
- praisonai serve unified - Launch unified server with all providers

All servers include the unified discovery endpoint at /__praisonai__/discovery.
"""

import os
import sys
import logging
from typing import Any, Dict, List, Optional


_LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _install_api_key_middleware(
    app: Any,
    api_key: Optional[str],
    public_paths: Optional[set] = None,
) -> None:
    """Enforce --api-key on serve endpoints when a key is configured."""
    if not api_key:
        return

    from praisonai._api_auth import build_api_key_middleware

    public = public_paths or {"/health", "/", "/.well-known/agent.json"}

    app.add_middleware(build_api_key_middleware(api_key, public))


class ServeHandler:
    """
    CLI handler for serve operations.
    
    Commands:
    - agents: Launch agents as HTTP API
    - recipe: Launch recipe runner
    - mcp: Launch MCP server
    - tools: Launch tools as MCP server
    - a2a: Launch A2A server
    - a2u: Launch A2U event stream server
    - unified: Launch unified server
    """
    
    EXIT_SUCCESS = 0
    EXIT_GENERAL_ERROR = 1
    EXIT_VALIDATION_ERROR = 2
    
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8765
    
    def __init__(self):
        """Initialize the handler."""
        pass
    
    def handle(self, args: List[str]) -> int:
        """
        Handle serve subcommand.
        
        Args:
            args: Command arguments
            
        Returns:
            Exit code
        """
        if not args:
            self._print_help()
            return self.EXIT_SUCCESS
        
        command = args[0]
        remaining = args[1:]
        
        commands = {
            "agents": self.cmd_agents,
            "recipe": self.cmd_recipe,
            "mcp": self.cmd_mcp,
            "tools": self.cmd_tools,
            "a2a": self.cmd_a2a,
            "a2u": self.cmd_a2u,
            "unified": self.cmd_unified,
            "help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "--help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "-h": lambda _: self._print_help() or self.EXIT_SUCCESS,
        }
        
        if command in commands:
            return commands[command](remaining)
        else:
            self._print_error(f"Unknown command: {command}")
            self._print_help()
            return self.EXIT_GENERAL_ERROR
    
    def _print_help(self):
        """Print help message."""
        help_text = """
[bold cyan]PraisonAI Serve[/bold cyan]

Launch PraisonAI servers with unified discovery support.

[bold]Usage:[/bold]
  praisonai serve <command> [options]

[bold]Commands:[/bold]
  agents            Launch agents as HTTP API
  recipe            Launch recipe runner server
  mcp               Launch MCP server (HTTP mode)
  tools             Launch tools as MCP server
  a2a               Launch A2A protocol server
  a2u               Launch A2U event stream server
  unified           Launch unified server with all providers

[bold]Common Options:[/bold]
  --host <host>     Server host (default: 127.0.0.1)
  --port <port>     Server port (default: 8765)
  --reload          Enable hot reload
  --api-key <key>   API key for authentication

[bold]Agents Options:[/bold]
  --file <path>     Agents YAML file (default: agents.yaml)
  --path <path>     API endpoint path (default: /agents)

[bold]Recipe Options:[/bold]
  --config <path>   Config file path (serve.yaml)
  --preload         Preload all recipes

[bold]MCP Options:[/bold]
  --transport       Transport type: http, sse (default: http)

[bold]Examples:[/bold]
  praisonai serve agents --file agents.yaml --port 8000
  praisonai serve recipe --port 8765
  praisonai serve mcp --transport http --port 8080
  praisonai serve tools --port 8081
  praisonai serve a2a --port 8082
  praisonai serve unified --port 8765

[bold]Discovery:[/bold]
  All servers expose /__praisonai__/discovery for unified endpoint discovery.

[bold]A2UI / AG-UI rendering:[/bold]
  For live A2UI surfaces in a web UI, use PraisonAIUI (POST /agui SSE + /api/surfaces):
    pip install praisonaiui praisonaiagents[a2ui]
  See docs: Integrate A2UI with Your Frontend.
  Use `praisonai endpoints` to interact with any server.
"""
        self._print_rich(help_text)
    
    def _print_rich(self, text: str):
        """Print with rich formatting if available."""
        try:
            from rich import print as rprint
            rprint(text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', text)
            print(plain)
    
    def _print_error(self, message: str):
        """Print error message."""
        try:
            from rich import print as rprint
            rprint(f"[red]Error: {message}[/red]")
        except ImportError:
            print(f"Error: {message}", file=sys.stderr)
    
    def _print_success(self, message: str):
        """Print success message."""
        try:
            from rich import print as rprint
            rprint(f"[green]✓ {message}[/green]")
        except ImportError:
            print(f"✓ {message}")
    
    def _parse_args(self, args: List[str], spec: Dict[str, Any]) -> Dict[str, Any]:
        """Parse command arguments based on spec."""
        result = {k: v.get("default") for k, v in spec.items()}
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg.startswith("--"):
                key = arg[2:].replace("-", "_")
                if key in spec:
                    if spec[key].get("flag"):
                        result[key] = True
                    elif i + 1 < len(args):
                        value = args[i + 1]
                        # Type conversion
                        if spec[key].get("type") == "int":
                            value = int(value)
                        result[key] = value
                        i += 1
                i += 1
            else:
                i += 1
        
        return result
    
    def cmd_agents(self, args: List[str]) -> int:
        """Launch agents as HTTP API."""
        spec = {
            "file": {"default": "agents.yaml"},
            "host": {"default": self.DEFAULT_HOST},
            "port": {"default": self.DEFAULT_PORT, "type": "int"},
            "path": {"default": "/agents"},
            "reload": {"flag": True, "default": False},
            "api_key": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        # Check if agents file exists
        if not os.path.exists(parsed["file"]):
            self._print_error(f"Agents file not found: {parsed['file']}")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            self._print_success(f"Starting agents server on {parsed['host']}:{parsed['port']}")
            print(f"  Agents file: {parsed['file']}")
            print(f"  Endpoint: {parsed['path']}")
            print("  Discovery: /__praisonai__/discovery")
            
            # Create and run server
            app = self._create_agents_app(parsed)
            self._run_server(app, parsed["host"], parsed["port"], parsed["reload"])
            
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            print("Install with: pip install praisonai[serve]")
            return self.EXIT_GENERAL_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
        
        return self.EXIT_SUCCESS
    
    def _create_agents_app(self, config: Dict[str, Any]) -> Any:
        """Create FastAPI app for agents."""
        from contextlib import asynccontextmanager

        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
        
        from praisonai.endpoints.discovery import (
            create_discovery_document,
            EndpointInfo,
            ProviderInfo,
        )
        from praisonai.endpoints.server import add_discovery_routes
        
        # Validate the agents YAML parses (file existence already checked in
        # cmd_agents); the cached generator re-reads it at startup. Capture the
        # YAML-declared framework so the cached generator honours it (crewai,
        # autogen, ...) instead of being pinned to praisonai; None -> registry
        # default, matching praisonai.run/arun.
        import yaml
        with open(config["file"]) as f:
            _yaml_config = yaml.safe_load(f) or {}
        yaml_framework = _yaml_config.get("framework")

        # Security: POST /agents can drive YAML-defined tools (execute_command,
        # write_file, ...) through the LLM tool-calling loop. Refuse to bind a
        # non-localhost host without an API key, mirroring jobs/server.py.
        host = config.get("host", self.DEFAULT_HOST)
        api_key = config.get("api_key") or os.environ.get("PRAISONAI_SERVE_API_KEY")
        if host not in _LOCALHOST_HOSTS and not api_key:
            raise SystemExit(
                "praisonai serve agents: --api-key (or PRAISONAI_SERVE_API_KEY) is "
                "required when binding to a non-localhost host; POST /agents can "
                "execute YAML-defined tools."
            )

        # Create discovery document
        discovery = create_discovery_document(server_name="praisonai-agents")
        discovery.add_provider(ProviderInfo(
            type="agents-api",
            name="Agents API",
            description="Agent HTTP API endpoints",
            capabilities=["invoke", "health"],
        ))

        # Cache a single AgentsGenerator for the app's lifetime so every request
        # reuses one YAML parse + framework resolution + tool-timeout pool instead
        # of rebuilding them (and a fresh 32-worker pool) per call. A lock
        # serialises the shared per-request cli_config mutation.
        import asyncio

        @asynccontextmanager
        async def _agents_lifespan(app):
            gen = None
            try:
                from praisonai._entrypoint import _resolve_run_inputs
                from praisonai.agents_generator import AgentsGenerator
                adapter, config_list = await asyncio.to_thread(
                    _resolve_run_inputs, yaml_framework
                )
                gen = AgentsGenerator(
                    agent_file=config["file"],
                    framework=adapter.name,
                    config_list=config_list,
                    adapter=adapter,
                )
            except Exception as e:
                logging.getLogger(__name__).warning(
                    f"Could not cache AgentsGenerator, falling back to per-request "
                    f"runs: {e}"
                )
            app.state.generator = gen
            app.state.generator_lock = asyncio.Lock()
            try:
                yield
            finally:
                if gen is not None:
                    gen.close()

        # Create app
        app = FastAPI(
            title="PraisonAI Agents API",
            description="HTTP API for PraisonAI Agents",
            lifespan=_agents_lifespan,
        )
        
        # Add discovery routes
        add_discovery_routes(app, discovery)
        
        # Mount agent_invoke router for n8n integration. We intentionally do NOT
        # seed the registry with hand-rolled PraisonAgent instances built from raw
        # YAML: that path silently dropped tool_timeout/approval/guardrails/retry.
        # Both /agents routes now run the cached AgentsGenerator instead, so a
        # single YAML -> agent lowering applies uniformly.
        try:
            from praisonai.api import agent_invoke
            # Only mount router if FastAPI is available and router exists
            if getattr(agent_invoke, 'FASTAPI_AVAILABLE', False) and hasattr(agent_invoke, 'router'):
                app.include_router(agent_invoke.router)
            else:
                logging.getLogger(__name__).warning("FastAPI not available, agent_invoke router not mounted")
            
        except ImportError as e:
            logging.getLogger(__name__).warning(f"Could not load agent invoke router: {e}")
        
        # Request model. ``agent`` is accepted for backward/n8n compatibility but
        # is not used to select a single role: POST /agents runs the full YAML
        # workflow through the cached generator (see invoke_agents).
        class AgentQuery(BaseModel):
            query: str
            agent: Optional[str] = None  # Accepted for compatibility; ignored
        
        # Create endpoint for agents
        path = config["path"]
        
        async def _run_query(request: Request, query: str) -> str:
            """Run a query through the cached generator so every route shares the
            same YAML -> agent lowering (ToolResolver, tool_timeout, approval,
            guardrails, retry). Falls back to praisonai.arun if caching failed."""
            gen = getattr(request.app.state, "generator", None)
            lock = getattr(request.app.state, "generator_lock", None)
            if gen is not None and lock is not None:
                async with lock:
                    gen.cli_config = {"topic": query} if query else {}
                    return await gen.agenerate_crew_and_kickoff()
            # Fallback: build a one-shot generator via the native async entrypoint.
            # framework=None lets arun honour the YAML-declared framework (or the
            # registry default), matching the cached generator above.
            import praisonai
            return await praisonai.arun(
                agent_file=config["file"],
                framework=yaml_framework,
                cli_config={"topic": query} if query else None,
            )

        @app.post(path)
        async def invoke_agents(request: Request, query_data: AgentQuery = None):
            """Invoke agents with a query."""
            if query_data is None:
                try:
                    body = await request.json()
                    query = body.get("query", "") or body.get("message", "")
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid request")
            else:
                query = query_data.query

            try:
                result = await _run_query(request, query)
                return {"response": result}
            except Exception as e:
                return JSONResponse(
                    {"error": str(e)},
                    status_code=500,
                )

        # Add simple /agents/{agent_name} endpoint for n8n compatibility. The
        # path segment is accepted as a compatibility alias only: it runs the
        # same cached generator (full YAML workflow) as POST /agents, so identical
        # YAML produces identical behaviour instead of silently dropping
        # tool_timeout/approval/guardrails via a hand-rolled per-agent path. It
        # does NOT select a single role; use the workflow's own routing for that.
        @app.post("/agents/{agent_name}")
        async def invoke_single_agent(agent_name: str, request: Request):
            """Invoke the agents workflow (n8n compatibility alias).

            ``agent_name`` is accepted for URL compatibility but the full YAML
            workflow is executed; it does not select an individual role.
            """
            try:
                body = await request.json()
                query = body.get("query", "") or body.get("message", "")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")

            if not query:
                raise HTTPException(status_code=400, detail="No query or message provided")

            try:
                result = await _run_query(request, query)
                return {"response": str(result)}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")
        
        # Add endpoint to discovery
        discovery.add_endpoint(EndpointInfo(
            name=path.lstrip("/"),
            description="Invoke agents workflow",
            provider_type="agents-api",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}, "agent": {"type": "string", "description": "Accepted for compatibility; ignored"}}},
            streaming=["none"],
        ))
        
        discovery.add_endpoint(EndpointInfo(
            name="agents/{agent_name}",
            description=(
                "n8n compatibility alias — runs the full agents workflow; "
                "agent_name does not select an individual role"
            ),
            provider_type="agents-api",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            streaming=["none"],
        ))
        
        # Root endpoint. The YAML-backed workflow is served on ``path`` and its
        # ``/{agent_name}`` alias. The mounted n8n router
        # (/api/v1/agents/{agent_id}/invoke) resolves only agents added via
        # register_agent(); it is not seeded from the served YAML, so it is
        # advertised separately to avoid implying YAML roles are invokable there.
        @app.get("/")
        async def root():
            return {
                "message": "PraisonAI Agents API",
                "endpoints": [path, "/agents/{agent_name}"],
                "registry_api": "/api/v1/agents/{agent_id}/invoke",
                "discovery": "/__praisonai__/discovery",
            }

        # Enforce the resolved key (flag or PRAISONAI_SERVE_API_KEY). No-ops only
        # for a keyless localhost bind; non-localhost keyless binds already raised.
        _install_api_key_middleware(app, api_key)
        
        return app
    
    def cmd_recipe(self, args: List[str]) -> int:
        """Launch recipe runner server via WebSocketGateway."""
        spec = {
            "host": {"default": self.DEFAULT_HOST},
            "port": {"default": self.DEFAULT_PORT, "type": "int"},
            "recipe": {"default": None},
            "reload": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        recipe_name = parsed.get("recipe")
        if not recipe_name:
            self._print_error("A recipe name is required (e.g. --recipe my-recipe)")
            return self.EXIT_VALIDATION_ERROR
            
        try:
            self._print_success(f"Starting recipe gateway on {parsed['host']}:{parsed['port']}")
            from praisonai_bot.cli.features.recipe_gateway import run_recipe_gateway

            return run_recipe_gateway(
                host=parsed["host"],
                port=parsed["port"],
                recipe_name=recipe_name,
            )
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            print("Install with: pip install praisonai[serve]")
            return self.EXIT_GENERAL_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_mcp(self, args: List[str]) -> int:
        """Launch MCP server (DEPRECATED - use 'praisonai mcp serve' instead)."""
        import sys
        
        # Print deprecation warning
        print("\n[yellow]⚠ DEPRECATION WARNING:[/yellow]", file=sys.stderr)
        print("[yellow]'praisonai serve mcp' is deprecated and will be removed in a future version.[/yellow]", file=sys.stderr)
        print("[yellow]Please use 'praisonai mcp serve' instead.[/yellow]\n", file=sys.stderr)
        
        # Redirect to new MCP server CLI
        try:
            from praisonai.mcp_server.cli import handle_mcp_command
            
            # Convert args to new format
            new_args = ["serve"]
            spec = {
                "host": {"default": self.DEFAULT_HOST},
                "port": {"default": 8080, "type": "int"},
                "transport": {"default": "http-stream"},
            }
            parsed = self._parse_args(args, spec)
            
            new_args.extend(["--host", parsed["host"]])
            new_args.extend(["--port", str(parsed["port"])])
            new_args.extend(["--transport", parsed["transport"]])
            
            return handle_mcp_command(new_args)
            
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            return self.EXIT_GENERAL_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_tools(self, args: List[str]) -> int:
        """Launch tools as MCP server (DEPRECATED - use 'praisonai mcp serve' instead)."""
        import sys
        
        # Print deprecation warning
        print("\n[yellow]⚠ DEPRECATION WARNING:[/yellow]", file=sys.stderr)
        print("[yellow]'praisonai serve tools' is deprecated and will be removed in a future version.[/yellow]", file=sys.stderr)
        print("[yellow]Please use 'praisonai mcp serve' instead.[/yellow]\n", file=sys.stderr)
        
        # Redirect to new MCP server CLI
        try:
            from praisonai.mcp_server.cli import handle_mcp_command
            
            # Convert args to new format
            new_args = ["serve"]
            spec = {
                "host": {"default": self.DEFAULT_HOST},
                "port": {"default": 8080, "type": "int"},
            }
            parsed = self._parse_args(args, spec)
            
            new_args.extend(["--host", parsed["host"]])
            new_args.extend(["--port", str(parsed["port"])])
            new_args.extend(["--transport", "http-stream"])
            
            return handle_mcp_command(new_args)
            
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            return self.EXIT_GENERAL_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_a2a(self, args: List[str]) -> int:
        """Launch A2A protocol server."""
        spec = {
            "host": {"default": self.DEFAULT_HOST},
            "port": {"default": 8082, "type": "int"},
            "file": {"default": "agents.yaml"},
        }
        parsed = self._parse_args(args, spec)
        
        try:
            self._print_success(f"Starting A2A server on {parsed['host']}:{parsed['port']}")
            print("  Agent Card: /.well-known/agent.json")
            print("  Discovery: /__praisonai__/discovery")
            
            app = self._create_a2a_app(parsed)
            self._run_server(app, parsed["host"], parsed["port"], False)
            
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            return self.EXIT_GENERAL_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
        
        return self.EXIT_SUCCESS
    
    def _create_a2a_app(self, config: Dict[str, Any]) -> Any:
        """Create FastAPI app for A2A server."""
        from fastapi import FastAPI
        
        from praisonai.endpoints.discovery import (
            create_discovery_document,
            EndpointInfo,
            ProviderInfo,
        )
        from praisonai.endpoints.server import add_discovery_routes
        
        discovery = create_discovery_document(server_name="praisonai-a2a")
        discovery.add_provider(ProviderInfo(
            type="a2a",
            name="A2A Protocol",
            description="Agent-to-Agent communication",
            capabilities=["agent-card", "message-send"],
        ))
        
        app = FastAPI(
            title="PraisonAI A2A Server",
            description="A2A protocol server",
        )
        
        add_discovery_routes(app, discovery)
        
        # Agent card
        @app.get("/.well-known/agent.json")
        async def agent_card():
            """Return agent card for A2A discovery."""
            return {
                "name": "PraisonAI Agent",
                "description": "PraisonAI Agent via A2A protocol",
                "version": "1.0.0",
                "url": f"http://{config.get('host', 'localhost')}:{config.get('port', 8082)}/a2a",
                "capabilities": {
                    "streaming": True,
                    "pushNotifications": False,
                },
                "skills": [],
            }
        
        @app.get("/status")
        async def status():
            """Return server status."""
            return {"status": "ok", "name": "PraisonAI A2A", "version": "1.0.0"}
        
        @app.post("/a2a")
        async def a2a_endpoint(request_data: dict):
            """Handle A2A JSON-RPC requests."""
            method = request_data.get("method")
            params = request_data.get("params", {})
            request_id = request_data.get("id")
            
            if method == "message/send":
                # Handle message
                message = params.get("message", {})
                parts = message.get("parts", [])
                text = ""
                for part in parts:
                    if part.get("type") == "text":
                        text += part.get("text", "")
                
                # TODO: Process with agent
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "message": {
                            "role": "assistant",
                            "parts": [{"type": "text", "text": f"Received: {text}"}],
                        },
                    },
                }
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        
        discovery.add_endpoint(EndpointInfo(
            name="a2a",
            description="A2A protocol endpoint",
            provider_type="a2a",
            streaming=["sse"],
        ))
        
        @app.get("/")
        async def root():
            return {
                "message": "PraisonAI A2A Server",
                "agent_card": "/.well-known/agent.json",
                "discovery": "/__praisonai__/discovery",
            }
        
        return app
    
    def cmd_a2u(self, args: List[str]) -> int:
        """Launch A2U event stream server."""
        import os
        spec = {
            "host": {"default": self.DEFAULT_HOST},
            "port": {"default": 8083, "type": "int"},
        }
        parsed = self._parse_args(args, spec)
        host = parsed["host"]
        if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("A2U_AUTH_TOKEN"):
            self._print_error(
                "A2U_AUTH_TOKEN required for non-localhost binding. "
                "Set A2U_AUTH_TOKEN or bind to 127.0.0.1"
            )
            return 4  # POLICY_DENIED
        
        try:
            self._print_success(f"Starting A2U server on {parsed['host']}:{parsed['port']}")
            print("  Events: /a2u/events/<stream>")
            print("  Discovery: /__praisonai__/discovery")
            
            app = self._create_a2u_app(parsed)
            self._run_server(app, parsed["host"], parsed["port"], False)
            
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            return self.EXIT_GENERAL_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
        
        return self.EXIT_SUCCESS
    
    def _create_a2u_app(self, config: Dict[str, Any]) -> Any:
        """Create FastAPI app for A2U server."""
        from fastapi import FastAPI
        
        from praisonai.endpoints.discovery import (
            create_discovery_document,
            EndpointInfo,
            ProviderInfo,
        )
        from praisonai.endpoints.server import add_discovery_routes
        from praisonai.endpoints.a2u_server import create_a2u_routes
        
        discovery = create_discovery_document(server_name="praisonai-a2u")
        discovery.add_provider(ProviderInfo(
            type="a2u",
            name="A2U Event Stream",
            description="Agent-to-User event streaming",
            capabilities=["subscribe", "stream"],
        ))
        
        app = FastAPI(
            title="PraisonAI A2U Server",
            description="A2U event stream server",
        )
        
        add_discovery_routes(app, discovery)
        create_a2u_routes(app)
        
        discovery.add_endpoint(EndpointInfo(
            name="events",
            description="Agent event stream",
            provider_type="a2u",
            streaming=["sse"],
        ))
        
        @app.get("/")
        async def root():
            return {
                "message": "PraisonAI A2U Server",
                "events": "/a2u/events/<stream>",
                "discovery": "/__praisonai__/discovery",
            }
        
        return app
    
    def cmd_unified(self, args: List[str]) -> int:
        """Launch unified server with all providers."""
        spec = {
            "host": {"default": self.DEFAULT_HOST},
            "port": {"default": self.DEFAULT_PORT, "type": "int"},
            "file": {"default": "agents.yaml"},
            "reload": {"flag": True, "default": False},
            "api_key": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        try:
            self._print_success(f"Starting unified server on {parsed['host']}:{parsed['port']}")
            print("  Providers: agents-api, recipe, mcp, a2a, a2u")
            print("  Discovery: /__praisonai__/discovery")
            
            app = self._create_unified_app(parsed)
            self._run_server(app, parsed["host"], parsed["port"], parsed["reload"])
            
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            print("Install with: pip install praisonai[serve]")
            return self.EXIT_GENERAL_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
        
        return self.EXIT_SUCCESS
    
    def _create_unified_app(self, config: Dict[str, Any]) -> Any:
        """Create unified FastAPI app with all providers."""
        from fastapi import FastAPI
        
        from praisonai.endpoints.discovery import (
            create_discovery_document,
            EndpointInfo,
            ProviderInfo,
        )
        from praisonai.endpoints.server import add_discovery_routes
        from praisonai.endpoints.a2u_server import create_a2u_routes
        
        discovery = create_discovery_document(server_name="praisonai-unified")
        
        # Add all providers
        discovery.add_provider(ProviderInfo(
            type="agents-api",
            name="Agents API",
            capabilities=["invoke", "health"],
        ))
        discovery.add_provider(ProviderInfo(
            type="recipe",
            name="Recipe Runner",
            capabilities=["list", "describe", "invoke", "stream"],
        ))
        discovery.add_provider(ProviderInfo(
            type="mcp",
            name="MCP Server",
            capabilities=["list-tools", "call-tool"],
        ))
        discovery.add_provider(ProviderInfo(
            type="a2a",
            name="A2A Protocol",
            capabilities=["agent-card", "message-send"],
        ))
        discovery.add_provider(ProviderInfo(
            type="a2u",
            name="A2U Event Stream",
            capabilities=["subscribe", "stream"],
        ))
        
        app = FastAPI(
            title="PraisonAI Unified Server",
            description="Unified server with all PraisonAI providers",
        )
        
        add_discovery_routes(app, discovery)
        create_a2u_routes(app)
        
        # Add sample endpoints
        discovery.add_endpoint(EndpointInfo(
            name="agents",
            description="Agents workflow endpoint",
            provider_type="agents-api",
        ))
        discovery.add_endpoint(EndpointInfo(
            name="events",
            description="Agent event stream",
            provider_type="a2u",
            streaming=["sse"],
        ))
        
        @app.get("/")
        async def root():
            return {
                "message": "PraisonAI Unified Server",
                "providers": ["agents-api", "recipe", "mcp", "a2a", "a2u"],
                "discovery": "/__praisonai__/discovery",
            }
        
        @app.get("/.well-known/agent.json")
        async def agent_card():
            return {
                "name": "PraisonAI Unified",
                "description": "PraisonAI Unified Server",
                "version": "1.0.0",
            }

        _install_api_key_middleware(app, config.get("api_key"))
        
        return app
    
    def _run_server(self, app: Any, host: str, port: int, reload: bool) -> None:
        """Run the server with uvicorn."""
        import os
        import uvicorn

        os.environ["PRAISONAI_CALL_BIND_HOST"] = host
        uvicorn.run(app, host=host, port=port, reload=reload)


def handle_serve_command(args: List[str]) -> int:
    """Entry point for serve command."""
    handler = ServeHandler()
    return handler.handle(args)
