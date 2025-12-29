"""
Endpoints CLI Feature Handler

Provides CLI commands for interacting with recipe endpoints:
- list: List available recipe endpoints
- describe: Show endpoint details and schema
- invoke: Call an endpoint
- health: Check endpoint server health

All commands use the canonical `praisonai endpoints` prefix.

Why this feature is valuable:
- DX: Client invocation from any language/script
- Ops: Health checks, monitoring, automation
- Polyglot: Non-Python clients can invoke recipes via HTTP
- Testing: Easy endpoint verification without code

Architecture notes:
- Optional extras only (no server deps in core)
- Lazy imports for all HTTP client code
- No impact on praisonaiagents import time
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional


class EndpointsHandler:
    """
    CLI handler for endpoints operations.
    
    Commands:
    - list: List available recipe endpoints
    - describe: Show endpoint details
    - invoke: Call an endpoint
    - health: Check server health
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

Client CLI for interacting with recipe endpoints.

[bold]Usage:[/bold]
  praisonai endpoints <command> [options]

[bold]Commands:[/bold]
  list              List available recipe endpoints
  describe <recipe> Show endpoint details and schema
  invoke <recipe>   Call an endpoint
  health            Check server health

[bold]List Options:[/bold]
  --format json     Output as JSON
  --tags <a,b>      Filter by tags (comma-separated)
  --url <url>       Server URL (default: http://localhost:8765)

[bold]Describe Options:[/bold]
  --schema          Show input/output schema only
  --url <url>       Server URL

[bold]Invoke Options:[/bold]
  --input <path>    Input file path
  --input-json <j>  Input as JSON string
  --config k=v      Config override (repeatable)
  --json            Output as JSON
  --stream          Stream output events (SSE)
  --url <url>       Server URL
  --api-key <key>   API key for auth (or set PRAISONAI_ENDPOINTS_API_KEY)
  --dry-run         Validate without executing

[bold]Health Options:[/bold]
  --url <url>       Server URL

[bold]Environment Variables:[/bold]
  PRAISONAI_ENDPOINTS_URL      Default server URL
  PRAISONAI_ENDPOINTS_API_KEY  API key for authentication

[bold]Examples:[/bold]
  praisonai endpoints list
  praisonai endpoints list --format json --tags audio,video
  praisonai endpoints describe ai-podcast-cleaner
  praisonai endpoints describe ai-podcast-cleaner --schema
  praisonai endpoints invoke ai-podcast-cleaner --input ./audio.mp3
  praisonai endpoints invoke ai-podcast-cleaner --input-json '{"text": "hello"}'
  praisonai endpoints invoke ai-podcast-cleaner --input ./audio.mp3 --stream
  praisonai endpoints health
  praisonai endpoints health --url http://localhost:8000
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
    
    def cmd_list(self, args: List[str]) -> int:
        """List available recipe endpoints."""
        spec = {
            "format": {"default": "table"},
            "tags": {"default": None},
            "url": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        # Build query params
        path = "/v1/recipes"
        if parsed["tags"]:
            path += f"?tags={parsed['tags']}"
        
        result = self._make_request("GET", path, url=parsed["url"])
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        recipes = result.get("data", {}).get("recipes", [])
        
        if parsed["format"] == "json":
            self._print_json(recipes)
            return self.EXIT_SUCCESS
        
        if not recipes:
            print("No endpoints available.")
            return self.EXIT_SUCCESS
        
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="Available Endpoints")
            table.add_column("Name", style="cyan")
            table.add_column("Version", style="green")
            table.add_column("Description")
            table.add_column("Tags", style="yellow")
            
            for r in recipes:
                tags = r.get("tags", [])
                table.add_row(
                    r.get("name", ""),
                    r.get("version", ""),
                    (r.get("description", "")[:50] + "...") if len(r.get("description", "")) > 50 else r.get("description", ""),
                    ", ".join(tags[:3]) if tags else "",
                )
            
            console.print(table)
        except ImportError:
            for r in recipes:
                print(f"{r.get('name')} ({r.get('version')}): {r.get('description', '')}")
        
        return self.EXIT_SUCCESS
    
    def cmd_describe(self, args: List[str]) -> int:
        """Describe a recipe endpoint."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "schema": {"flag": True, "default": False},
            "url": {"default": None},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        # Get schema if requested
        if parsed["schema"]:
            path = f"/v1/recipes/{parsed['recipe']}/schema"
        else:
            path = f"/v1/recipes/{parsed['recipe']}"
        
        result = self._make_request("GET", path, url=parsed["url"])
        
        if result.get("status") == 404:
            self._print_error(f"Endpoint not found: {parsed['recipe']}")
            return self.EXIT_NOT_FOUND
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        self._print_json(data)
        return self.EXIT_SUCCESS
    
    def cmd_invoke(self, args: List[str]) -> int:
        """Invoke a recipe endpoint."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "input": {"short": "-i", "default": None},
            "input_json": {"default": None},
            "config": {"repeatable": True, "default": []},
            "json": {"flag": True, "default": False},
            "stream": {"flag": True, "default": False},
            "url": {"default": None},
            "api_key": {"default": None},
            "dry_run": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        # Build input data
        input_data = {}
        if parsed["input_json"]:
            try:
                input_data = json.loads(parsed["input_json"])
            except json.JSONDecodeError:
                self._print_error("Invalid JSON in --input-json")
                return self.EXIT_VALIDATION_ERROR
        elif parsed["input"]:
            input_data = {"input": parsed["input"]}
        
        # Build config from --config key=value pairs
        config = {}
        for cfg in parsed["config"]:
            if "=" in cfg:
                k, v = cfg.split("=", 1)
                config[k] = v
        
        # Build request body
        body = {
            "recipe": parsed["recipe"],
            "input": input_data,
            "config": config,
            "options": {"dry_run": parsed["dry_run"]},
        }
        
        if parsed["stream"]:
            return self._invoke_stream(body, parsed)
        
        # Sync invocation
        result = self._make_request(
            "POST",
            "/v1/recipes/run",
            url=parsed["url"],
            api_key=parsed["api_key"],
            json_data=body,
        )
        
        if result.get("status") == 401:
            self._print_error("Authentication required. Use --api-key or set PRAISONAI_ENDPOINTS_API_KEY")
            return self.EXIT_AUTH_ERROR
        
        if result.get("status") == 404:
            self._print_error(f"Endpoint not found: {parsed['recipe']}")
            return self.EXIT_NOT_FOUND
        
        if result.get("error"):
            self._print_error(result["error"].get("message", str(result["error"])))
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        if parsed["json"]:
            self._print_json(data)
        else:
            if data.get("ok"):
                self._print_success(f"Endpoint '{parsed['recipe']}' invoked successfully")
                print(f"  Run ID: {data.get('run_id')}")
                print(f"  Status: {data.get('status')}")
                if data.get("output"):
                    print(f"  Output: {data.get('output')}")
            else:
                self._print_error(f"Invocation failed: {data.get('error')}")
                return self.EXIT_RUNTIME_ERROR
        
        return self.EXIT_SUCCESS if data.get("ok") else self.EXIT_RUNTIME_ERROR
    
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
        }
        parsed = self._parse_args(args, spec)
        
        result = self._make_request("GET", "/health", url=parsed["url"])
        
        if result.get("error"):
            self._print_error(f"Server unhealthy: {result['error'].get('message', str(result['error']))}")
            return self.EXIT_CONNECTION_ERROR
        
        data = result.get("data", {})
        
        if data.get("status") == "healthy":
            self._print_success("Server healthy")
            print(f"  Service: {data.get('service')}")
            print(f"  Version: {data.get('version')}")
            return self.EXIT_SUCCESS
        else:
            self._print_error(f"Server unhealthy: {data}")
            return self.EXIT_RUNTIME_ERROR


def handle_endpoints_command(args: List[str]) -> int:
    """Entry point for endpoints command."""
    handler = EndpointsHandler()
    return handler.handle(args)
