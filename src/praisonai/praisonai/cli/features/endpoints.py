"""
Endpoints CLI Feature Handler

Provides CLI commands for interacting with PraisonAI endpoints:
- list: List available endpoints (all provider types)
- describe: Show endpoint details and schema
- invoke: Call an endpoint
- health: Check endpoint server health
- types: List supported provider types

Supported Provider Types:
- recipe: Recipe runner endpoints
- agents-api: Single/multi-agent HTTP API
- mcp: MCP server (stdio, http, sse)
- tools-mcp: Tools exposed as MCP server
- a2a: Agent-to-agent protocol
- a2u: Agent-to-user event stream

All commands use the canonical `praisonai endpoints` prefix.

Why this feature is valuable:
- DX: Client invocation from any language/script
- Ops: Health checks, monitoring, automation
- Polyglot: Non-Python clients can invoke recipes via HTTP
- Testing: Easy endpoint verification without code
- Unified: Single interface for all server types

Architecture notes:
- Optional extras only (no server deps in core)
- Lazy imports for all HTTP client code
- No impact on praisonaiagents import time
- Backward compatible with existing recipe-only usage
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional


# Supported provider types
PROVIDER_TYPES = [
    "recipe",
    "agents-api",
    "mcp",
    "tools-mcp",
    "a2a",
    "a2u",
]


class EndpointsHandler:
    """
    CLI handler for endpoints operations.
    
    Commands:
    - list: List available endpoints (all provider types)
    - describe: Show endpoint details
    - invoke: Call an endpoint
    - health: Check server health
    - types: List supported provider types
    """
    
    # Exit codes
    EXIT_SUCCESS = 0
    EXIT_GENERAL_ERROR = 1
    EXIT_VALIDATION_ERROR = 2
    EXIT_RUNTIME_ERROR = 3
    EXIT_AUTH_ERROR = 4
    EXIT_NOT_FOUND = 7
    EXIT_CONNECTION_ERROR = 8
    
    DEFAULT_URL = "http://localhost:8765"
    
    def __init__(self):
        """Initialize the handler."""
        self._base_url = None
        self._api_key = None
    
    @property
    def base_url(self) -> str:
        """Get base URL from env or default."""
        if self._base_url:
            return self._base_url
        return os.environ.get("PRAISONAI_ENDPOINTS_URL", self.DEFAULT_URL)
    
    @property
    def api_key(self) -> Optional[str]:
        """Get API key from env."""
        if self._api_key:
            return self._api_key
        return os.environ.get("PRAISONAI_ENDPOINTS_API_KEY")
    
    def handle(self, args: List[str]) -> int:
        """
        Handle endpoints subcommand.
        
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
            "list": self.cmd_list,
            "describe": self.cmd_describe,
            "invoke": self.cmd_invoke,
            "health": self.cmd_health,
            "types": self.cmd_types,
            "discovery": self.cmd_discovery,
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
[bold cyan]PraisonAI Endpoints[/bold cyan]

Unified client CLI for interacting with PraisonAI endpoints.

[bold]Usage:[/bold]
  praisonai endpoints <command> [options]

[bold]Commands:[/bold]
  list              List available endpoints (all types)
  describe <name>   Show endpoint details and schema
  invoke <name>     Call an endpoint
  health            Check server health
  types             List supported provider types
  discovery         Show raw discovery document

[bold]Global Options:[/bold]
  --url <url>       Server URL (default: http://localhost:8765)
  --api-key <key>   API key (or set PRAISONAI_ENDPOINTS_API_KEY)
  --type <type>     Filter by provider type (recipe, agents-api, mcp, etc.)

[bold]List Options:[/bold]
  --format json     Output as JSON
  --tags <a,b>      Filter by tags (comma-separated)

[bold]Describe Options:[/bold]
  --schema          Show input/output schema only

[bold]Invoke Options:[/bold]
  --input <path>    Input file path
  --input-json <j>  Input as JSON string
  --config k=v      Config override (repeatable)
  --json            Output as JSON
  --stream          Stream output events (SSE)
  --dry-run         Validate without executing

[bold]Provider Types:[/bold]
  recipe            Recipe runner endpoints
  agents-api        Single/multi-agent HTTP API
  mcp               MCP server (stdio, http, sse)
  tools-mcp         Tools exposed as MCP server
  a2a               Agent-to-agent protocol
  a2u               Agent-to-user event stream

[bold]Environment Variables:[/bold]
  PRAISONAI_ENDPOINTS_URL      Default server URL
  PRAISONAI_ENDPOINTS_API_KEY  API key for authentication

[bold]Examples:[/bold]
  praisonai endpoints list
  praisonai endpoints list --type agents-api
  praisonai endpoints list --format json --tags audio,video
  praisonai endpoints describe my-agent
  praisonai endpoints describe my-agent --schema
  praisonai endpoints invoke my-agent --input-json '{"query": "hello"}'
  praisonai endpoints invoke my-recipe --input ./data.json --stream
  praisonai endpoints health
  praisonai endpoints health --url http://localhost:8000
  praisonai endpoints types
  praisonai endpoints discovery
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
    
    def _print_json(self, data: Any):
        """Print JSON output."""
        print(json.dumps(data, indent=2, default=str))
    
    def _parse_args(self, args: List[str], spec: Dict[str, Any]) -> Dict[str, Any]:
        """Parse command arguments based on spec."""
        result = {k: v.get("default") for k, v in spec.items()}
        positional_keys = [k for k, v in spec.items() if v.get("positional")]
        positional_idx = 0
        
        # Handle repeatable args
        for k, v in spec.items():
            if v.get("repeatable"):
                result[k] = []
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg.startswith("--"):
                key = arg[2:].replace("-", "_")
                if key in spec:
                    if spec[key].get("flag"):
                        result[key] = True
                    elif spec[key].get("repeatable") and i + 1 < len(args):
                        result[key].append(args[i + 1])
                        i += 1
                    elif i + 1 < len(args):
                        result[key] = args[i + 1]
                        i += 1
                i += 1
            elif arg.startswith("-") and len(arg) == 2:
                for key, val in spec.items():
                    if val.get("short") == arg:
                        if val.get("flag"):
                            result[key] = True
                        elif i + 1 < len(args):
                            result[key] = args[i + 1]
                            i += 1
                        break
                i += 1
            else:
                if positional_idx < len(positional_keys):
                    result[positional_keys[positional_idx]] = arg
                    positional_idx += 1
                i += 1
        
        return result
    
    def _make_request(
        self,
        method: str,
        path: str,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        json_data: Optional[Dict] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Make HTTP request to endpoint server."""
        try:
            import urllib.request
            import urllib.error
        except ImportError:
            return {"error": "urllib not available"}
        
        base = url or self.base_url
        full_url = f"{base.rstrip('/')}{path}"
        
        headers = {"Content-Type": "application/json"}
        key = api_key or self.api_key
        if key:
            headers["X-API-Key"] = key
        
        data = None
        if json_data:
            data = json.dumps(json_data).encode("utf-8")
        
        try:
            req = urllib.request.Request(
                full_url,
                data=data,
                headers=headers,
                method=method,
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                return {"status": response.status, "data": json.loads(body) if body else {}}
                
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            try:
                error_data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                error_data = {"message": body}
            return {"status": e.code, "error": error_data}
        except urllib.error.URLError as e:
            return {"status": 0, "error": {"message": f"Connection error: {e.reason}"}}
        except Exception as e:
            return {"status": 0, "error": {"message": str(e)}}
    
    def _stream_request(
        self,
        path: str,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        json_data: Optional[Dict] = None,
    ):
        """Make streaming HTTP request."""
        try:
            import urllib.request
        except ImportError:
            yield {"error": "urllib not available"}
            return
        
        base = url or self.base_url
        full_url = f"{base.rstrip('/')}{path}"
        
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        key = api_key or self.api_key
        if key:
            headers["X-API-Key"] = key
        
        data = json.dumps(json_data).encode("utf-8") if json_data else None
        
        try:
            req = urllib.request.Request(full_url, data=data, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=300) as response:
                buffer = ""
                for line in response:
                    line = line.decode("utf-8")
                    buffer += line
                    
                    if buffer.endswith("\n\n"):
                        # Parse SSE event
                        event_type = "message"
                        event_data = ""
                        
                        for part in buffer.strip().split("\n"):
                            if part.startswith("event:"):
                                event_type = part[6:].strip()
                            elif part.startswith("data:"):
                                event_data = part[5:].strip()
                        
                        if event_data:
                            try:
                                yield {"event": event_type, "data": json.loads(event_data)}
                            except json.JSONDecodeError:
                                yield {"event": event_type, "data": event_data}
                        
                        buffer = ""
                        
        except Exception as e:
            yield {"error": str(e)}
    
    def _get_provider(self, provider_type: str, url: Optional[str] = None, api_key: Optional[str] = None):
        """Get a provider instance."""
        try:
            from praisonai.endpoints import get_provider
            return get_provider(
                provider_type,
                base_url=url or self.base_url,
                api_key=api_key or self.api_key,
            )
        except ImportError:
            return None
    
    def _try_unified_discovery(self, url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Try to get unified discovery document."""
        result = self._make_request("GET", "/__praisonai__/discovery", url=url)
        if not result.get("error") and result.get("data"):
            return result.get("data")
        return None
    
    def cmd_list(self, args: List[str]) -> int:
        """List available endpoints (all provider types)."""
        spec = {
            "format": {"default": "table"},
            "tags": {"default": None},
            "url": {"default": None},
            "type": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        all_endpoints = []
        
        # Try unified discovery first
        discovery = self._try_unified_discovery(parsed["url"])
        if discovery:
            endpoints = discovery.get("endpoints", [])
            for ep in endpoints:
                # Filter by type if specified
                if parsed["type"] and ep.get("provider_type") != parsed["type"]:
                    continue
                # Filter by tags if specified
                if parsed["tags"]:
                    tag_list = [t.strip() for t in parsed["tags"].split(",")]
                    ep_tags = ep.get("tags", [])
                    if not any(t in ep_tags for t in tag_list):
                        continue
                all_endpoints.append(ep)
        else:
            # Fallback: try recipe endpoint (backward compatibility)
            if not parsed["type"] or parsed["type"] == "recipe":
                path = "/v1/recipes"
                if parsed["tags"]:
                    path += f"?tags={parsed['tags']}"
                
                result = self._make_request("GET", path, url=parsed["url"])
                
                if not result.get("error"):
                    recipes = result.get("data", {}).get("recipes", [])
                    for r in recipes:
                        all_endpoints.append({
                            "name": r.get("name", ""),
                            "description": r.get("description", ""),
                            "provider_type": "recipe",
                            "version": r.get("version", "1.0.0"),
                            "tags": r.get("tags", []),
                            "streaming": ["none", "sse"],
                        })
            
            # Try agents-api endpoint
            if not parsed["type"] or parsed["type"] == "agents-api":
                result = self._make_request("GET", "/", url=parsed["url"])
                if not result.get("error"):
                    data = result.get("data", {})
                    for path in data.get("endpoints", []):
                        all_endpoints.append({
                            "name": path.lstrip("/"),
                            "description": f"Agent endpoint at {path}",
                            "provider_type": "agents-api",
                            "streaming": ["none"],
                        })
        
        if not all_endpoints:
            result = self._make_request("GET", "/health", url=parsed["url"])
            if result.get("error"):
                self._print_error(result["error"].get("message", str(result["error"])))
                return self.EXIT_CONNECTION_ERROR
            print("No endpoints available.")
            return self.EXIT_SUCCESS
        
        if parsed["format"] == "json":
            self._print_json(all_endpoints)
            return self.EXIT_SUCCESS
        
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="Available Endpoints")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="magenta")
            table.add_column("Description")
            table.add_column("Streaming", style="green")
            table.add_column("Tags", style="yellow")
            
            for ep in all_endpoints:
                tags = ep.get("tags", [])
                streaming = ep.get("streaming", ["none"])
                desc = ep.get("description", "")
                table.add_row(
                    ep.get("name", ""),
                    ep.get("provider_type", "unknown"),
                    (desc[:40] + "...") if len(desc) > 40 else desc,
                    ", ".join(streaming[:2]),
                    ", ".join(tags[:3]) if tags else "",
                )
            
            console.print(table)
        except ImportError:
            for ep in all_endpoints:
                print(f"[{ep.get('provider_type', 'unknown')}] {ep.get('name')}: {ep.get('description', '')}")
        
        return self.EXIT_SUCCESS
    
    def cmd_describe(self, args: List[str]) -> int:
        """Describe an endpoint."""
        spec = {
            "name": {"positional": True, "default": ""},
            "schema": {"flag": True, "default": False},
            "url": {"default": None},
            "type": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["name"]:
            self._print_error("Endpoint name required")
            return self.EXIT_VALIDATION_ERROR
        
        endpoint_name = parsed["name"]
        endpoint_info = None
        
        # Try unified discovery first
        discovery = self._try_unified_discovery(parsed["url"])
        if discovery:
            for ep in discovery.get("endpoints", []):
                if ep.get("name") == endpoint_name:
                    if parsed["type"] and ep.get("provider_type") != parsed["type"]:
                        continue
                    endpoint_info = ep
                    break
        
        if endpoint_info:
            if parsed["schema"]:
                schema_info = {
                    "name": endpoint_info.get("name"),
                    "input_schema": endpoint_info.get("input_schema"),
                    "output_schema": endpoint_info.get("output_schema"),
                }
                self._print_json(schema_info)
            else:
                self._print_json(endpoint_info)
            return self.EXIT_SUCCESS
        
        # Fallback: try recipe endpoint (backward compatibility)
        if not parsed["type"] or parsed["type"] == "recipe":
            if parsed["schema"]:
                path = f"/v1/recipes/{endpoint_name}/schema"
            else:
                path = f"/v1/recipes/{endpoint_name}"
            
            result = self._make_request("GET", path, url=parsed["url"])
            
            if not result.get("error") and result.get("status") != 404:
                data = result.get("data", {})
                # Add provider_type for consistency
                data["provider_type"] = "recipe"
                self._print_json(data)
                return self.EXIT_SUCCESS
        
        # Try agents-api
        if not parsed["type"] or parsed["type"] == "agents-api":
            # Return basic info for agent endpoints
            endpoint_info = {
                "name": endpoint_name,
                "provider_type": "agents-api",
                "description": f"Agent endpoint: {endpoint_name}",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                "streaming": ["none"],
                "auth_modes": ["none"],
            }
            self._print_json(endpoint_info)
            return self.EXIT_SUCCESS
        
        self._print_error(f"Endpoint not found: {endpoint_name}")
        return self.EXIT_NOT_FOUND
    
    def cmd_invoke(self, args: List[str]) -> int:
        """Invoke an endpoint."""
        spec = {
            "name": {"positional": True, "default": ""},
            "input": {"short": "-i", "default": None},
            "input_json": {"default": None},
            "config": {"repeatable": True, "default": []},
            "json": {"flag": True, "default": False},
            "stream": {"flag": True, "default": False},
            "url": {"default": None},
            "api_key": {"default": None},
            "dry_run": {"flag": True, "default": False},
            "type": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["name"]:
            self._print_error("Endpoint name required")
            return self.EXIT_VALIDATION_ERROR
        
        endpoint_name = parsed["name"]
        
        # Build input data
        input_data = {}
        if parsed["input_json"]:
            try:
                input_data = json.loads(parsed["input_json"])
            except json.JSONDecodeError:
                self._print_error("Invalid JSON in --input-json")
                return self.EXIT_VALIDATION_ERROR
        elif parsed["input"]:
            # Check if input is a file path
            if os.path.isfile(parsed["input"]):
                try:
                    with open(parsed["input"]) as f:
                        input_data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    input_data = {"input": parsed["input"]}
            else:
                input_data = {"input": parsed["input"]}
        
        # Build config from --config key=value pairs
        config = {}
        for cfg in parsed["config"]:
            if "=" in cfg:
                k, v = cfg.split("=", 1)
                config[k] = v
        
        # Detect provider type from discovery or explicit --type
        provider_type = parsed["type"]
        if not provider_type:
            discovery = self._try_unified_discovery(parsed["url"])
            if discovery:
                for ep in discovery.get("endpoints", []):
                    if ep.get("name") == endpoint_name:
                        provider_type = ep.get("provider_type")
                        break
        
        # Default to recipe for backward compatibility
        if not provider_type:
            provider_type = "recipe"
        
        # Route to appropriate invocation method
        if provider_type == "recipe":
            return self._invoke_recipe(endpoint_name, input_data, config, parsed)
        elif provider_type == "agents-api":
            return self._invoke_agents_api(endpoint_name, input_data, config, parsed)
        elif provider_type in ("mcp", "tools-mcp"):
            return self._invoke_mcp(endpoint_name, input_data, config, parsed)
        elif provider_type == "a2a":
            return self._invoke_a2a(endpoint_name, input_data, config, parsed)
        elif provider_type == "a2u":
            return self._invoke_a2u(endpoint_name, input_data, config, parsed)
        else:
            # Fallback to recipe
            return self._invoke_recipe(endpoint_name, input_data, config, parsed)
    
    def _invoke_recipe(self, name: str, input_data: Dict, config: Dict, parsed: Dict) -> int:
        """Invoke a recipe endpoint."""
        body = {
            "recipe": name,
            "input": input_data,
            "config": config,
            "options": {"dry_run": parsed["dry_run"]},
        }
        
        if parsed["stream"]:
            return self._invoke_stream(body, parsed)
        
        result = self._make_request(
            "POST",
            "/v1/recipes/run",
            url=parsed["url"],
            api_key=parsed["api_key"],
            json_data=body,
        )
        
        return self._handle_invoke_result(result, name, parsed)
    
    def _invoke_agents_api(self, name: str, input_data: Dict, config: Dict, parsed: Dict) -> int:
        """Invoke an agents-api endpoint."""
        path = name if name.startswith("/") else f"/{name}"
        
        # Build body - agents-api expects query field
        body = input_data
        if "query" not in body and config.get("query"):
            body["query"] = config["query"]
        
        result = self._make_request(
            "POST",
            path,
            url=parsed["url"],
            api_key=parsed["api_key"],
            json_data=body,
        )
        
        if result.get("status") == 401:
            self._print_error("Authentication required")
            return self.EXIT_AUTH_ERROR
        
        if result.get("status") == 404:
            self._print_error(f"Endpoint not found: {name}")
            return self.EXIT_NOT_FOUND
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        if parsed["json"]:
            self._print_json(data)
        else:
            response = data.get("response", data)
            self._print_success(f"Endpoint '{name}' invoked successfully")
            print(f"  Response: {response}")
        
        return self.EXIT_SUCCESS
    
    def _invoke_mcp(self, name: str, input_data: Dict, config: Dict, parsed: Dict) -> int:
        """Invoke an MCP tool."""
        body = {
            "tool": name,
            "arguments": input_data,
        }
        
        result = self._make_request(
            "POST",
            "/mcp/tools/call",
            url=parsed["url"],
            api_key=parsed["api_key"],
            json_data=body,
        )
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        if parsed["json"]:
            self._print_json(data)
        else:
            self._print_success(f"Tool '{name}' invoked successfully")
            print(f"  Result: {data.get('result', data)}")
        
        return self.EXIT_SUCCESS
    
    def _invoke_a2a(self, name: str, input_data: Dict, config: Dict, parsed: Dict) -> int:
        """Invoke an A2A agent."""
        import uuid
        
        message = input_data.get("message", input_data.get("query", ""))
        if not message and config.get("message"):
            message = config["message"]
        
        body = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": str(uuid.uuid4()),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                },
            },
        }
        
        result = self._make_request(
            "POST",
            "/a2a",
            url=parsed["url"],
            api_key=parsed["api_key"],
            json_data=body,
        )
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        if parsed["json"]:
            self._print_json(data)
        else:
            if "result" in data:
                self._print_success(f"A2A message sent to '{name}'")
                print(f"  Result: {data['result']}")
            elif "error" in data:
                self._print_error(data["error"].get("message", str(data["error"])))
                return self.EXIT_RUNTIME_ERROR
        
        return self.EXIT_SUCCESS
    
    def _invoke_a2u(self, name: str, input_data: Dict, config: Dict, parsed: Dict) -> int:
        """Subscribe to an A2U event stream."""
        if parsed["stream"]:
            return self._stream_a2u(name, parsed)
        
        body = {
            "stream": name,
            "filters": input_data.get("filters", []),
        }
        
        result = self._make_request(
            "POST",
            "/a2u/subscribe",
            url=parsed["url"],
            api_key=parsed["api_key"],
            json_data=body,
        )
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        if parsed["json"]:
            self._print_json(data)
        else:
            self._print_success(f"Subscribed to A2U stream '{name}'")
            print(f"  Stream URL: {data.get('stream_url')}")
        
        return self.EXIT_SUCCESS
    
    def _stream_a2u(self, name: str, parsed: Dict) -> int:
        """Stream A2U events."""
        print(f"Streaming events from '{name}'...")
        
        for event in self._stream_request(
            f"/a2u/events/{name}",
            url=parsed["url"],
            api_key=parsed["api_key"],
        ):
            if event.get("error"):
                self._print_error(event["error"])
                return self.EXIT_CONNECTION_ERROR
            
            if parsed["json"]:
                print(json.dumps(event))
            else:
                print(f"  [{event.get('event', 'event')}] {event.get('data', '')}")
        
        return self.EXIT_SUCCESS
    
    def _handle_invoke_result(self, result: Dict, name: str, parsed: Dict) -> int:
        """Handle common invoke result processing."""
        if result.get("status") == 401:
            self._print_error("Authentication required. Use --api-key or set PRAISONAI_ENDPOINTS_API_KEY")
            return self.EXIT_AUTH_ERROR
        
        if result.get("status") == 404:
            self._print_error(f"Endpoint not found: {name}")
            return self.EXIT_NOT_FOUND
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        if parsed["json"]:
            self._print_json(data)
        else:
            if data.get("ok", True):
                self._print_success(f"Endpoint '{name}' invoked successfully")
                if data.get("run_id"):
                    print(f"  Run ID: {data.get('run_id')}")
                if data.get("status"):
                    print(f"  Status: {data.get('status')}")
                if data.get("output"):
                    print(f"  Output: {data.get('output')}")
            else:
                self._print_error(f"Invocation failed: {data.get('error')}")
                return self.EXIT_RUNTIME_ERROR
        
        return self.EXIT_SUCCESS if data.get("ok", True) else self.EXIT_RUNTIME_ERROR
    
    def _invoke_stream(self, body: Dict, parsed: Dict) -> int:
        """Handle streaming invocation."""
        print("Streaming output...")
        
        for event in self._stream_request(
            "/v1/recipes/stream",
            url=parsed["url"],
            api_key=parsed["api_key"],
            json_data=body,
        ):
            if event.get("error"):
                self._print_error(event["error"])
                return self.EXIT_CONNECTION_ERROR
            
            event_type = event.get("event", "message")
            data = event.get("data", {})
            
            if parsed["json"]:
                print(json.dumps({"event": event_type, "data": data}))
            else:
                if event_type == "started":
                    print(f"  Started: {data.get('run_id')}")
                elif event_type == "progress":
                    print(f"  [{data.get('step')}] {data.get('message', '')}")
                elif event_type == "completed":
                    self._print_success(f"Completed: {data.get('status')}")
                elif event_type == "error":
                    self._print_error(data.get("message", "Unknown error"))
                    return self.EXIT_RUNTIME_ERROR
        
        return self.EXIT_SUCCESS
    
    def cmd_health(self, args: List[str]) -> int:
        """Check endpoint server health."""
        spec = {
            "url": {"default": None},
            "type": {"default": None},
            "format": {"default": "table"},
        }
        parsed = self._parse_args(args, spec)
        
        # Try unified discovery first for richer info
        discovery = self._try_unified_discovery(parsed["url"])
        
        result = self._make_request("GET", "/health", url=parsed["url"])
        
        if result.get("error"):
            self._print_error(f"Server unhealthy: {result['error'].get('message', str(result['error']))}")
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        # Merge discovery info
        if discovery:
            data["schema_version"] = discovery.get("schema_version")
            data["providers"] = [p.get("type") for p in discovery.get("providers", [])]
            data["endpoint_count"] = len(discovery.get("endpoints", []))
        
        if parsed["format"] == "json":
            self._print_json(data)
            return self.EXIT_SUCCESS
        
        status = data.get("status", "unknown")
        if status in ("healthy", "ok"):
            self._print_success("Server healthy")
            if data.get("service"):
                print(f"  Service: {data.get('service')}")
            if data.get("server_name"):
                print(f"  Server: {data.get('server_name')}")
            if data.get("version"):
                print(f"  Version: {data.get('version')}")
            if data.get("schema_version"):
                print(f"  Schema Version: {data.get('schema_version')}")
            if data.get("providers"):
                print(f"  Providers: {', '.join(data.get('providers'))}")
            if data.get("endpoint_count"):
                print(f"  Endpoints: {data.get('endpoint_count')}")
            if data.get("endpoints"):
                print(f"  Endpoints: {', '.join(data.get('endpoints')[:5])}")
            return self.EXIT_SUCCESS
        else:
            self._print_error(f"Server unhealthy: {data}")
            return self.EXIT_RUNTIME_ERROR
    
    def cmd_types(self, args: List[str]) -> int:
        """List supported provider types."""
        spec = {
            "format": {"default": "table"},
        }
        parsed = self._parse_args(args, spec)
        
        types_info = [
            {"type": "recipe", "description": "Recipe runner endpoints", "capabilities": ["list", "describe", "invoke", "stream"]},
            {"type": "agents-api", "description": "Single/multi-agent HTTP API", "capabilities": ["list", "describe", "invoke"]},
            {"type": "mcp", "description": "MCP server (stdio, http, sse)", "capabilities": ["list-tools", "call-tool"]},
            {"type": "tools-mcp", "description": "Tools exposed as MCP server", "capabilities": ["list-tools", "call-tool"]},
            {"type": "a2a", "description": "Agent-to-agent protocol", "capabilities": ["agent-card", "message-send", "stream"]},
            {"type": "a2u", "description": "Agent-to-user event stream", "capabilities": ["subscribe", "stream"]},
        ]
        
        if parsed["format"] == "json":
            self._print_json(types_info)
            return self.EXIT_SUCCESS
        
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="Supported Provider Types")
            table.add_column("Type", style="cyan")
            table.add_column("Description")
            table.add_column("Capabilities", style="green")
            
            for t in types_info:
                table.add_row(
                    t["type"],
                    t["description"],
                    ", ".join(t["capabilities"]),
                )
            
            console.print(table)
        except ImportError:
            for t in types_info:
                print(f"{t['type']}: {t['description']}")
        
        return self.EXIT_SUCCESS
    
    def cmd_discovery(self, args: List[str]) -> int:
        """Show raw discovery document."""
        spec = {
            "url": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        discovery = self._try_unified_discovery(parsed["url"])
        
        if discovery:
            self._print_json(discovery)
            return self.EXIT_SUCCESS
        
        self._print_error("Discovery endpoint not available at this server")
        return self.EXIT_NOT_FOUND


def handle_endpoints_command(args: List[str]) -> int:
    """Entry point for endpoints command."""
    handler = EndpointsHandler()
    return handler.handle(args)
