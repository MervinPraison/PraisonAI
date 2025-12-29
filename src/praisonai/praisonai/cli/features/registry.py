"""
Registry CLI Feature Handler

Provides CLI commands for recipe registry management:
- serve: Start local HTTP registry server
- status: Check registry status

All commands use the canonical `praisonai registry` prefix.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List


class RegistryHandler:
    """
    CLI handler for registry operations.
    
    Commands:
    - serve: Start local HTTP registry server
    - status: Check registry server status
    """
    
    # Stable exit codes
    EXIT_SUCCESS = 0
    EXIT_GENERAL_ERROR = 1
    EXIT_VALIDATION_ERROR = 2
    EXIT_NETWORK_ERROR = 10
    EXIT_AUTH_ERROR = 9
    
    def __init__(self):
        """Initialize the handler."""
        pass
    
    def handle(self, args: List[str]) -> int:
        """
        Handle registry subcommand.
        
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
            "serve": self.cmd_serve,
            "status": self.cmd_status,
            "help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "--help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "-h": lambda _: self._print_help() or self.EXIT_SUCCESS,
        }
        
        handler = commands.get(command)
        if handler:
            return handler(remaining)
        
        self._print_error(f"Unknown command: {command}")
        self._print_help()
        return self.EXIT_VALIDATION_ERROR
    
    def _print_help(self):
        """Print help message."""
        print("""
PraisonAI Registry Commands

Usage: praisonai registry <command> [options]

Commands:
  serve     Start local HTTP registry server
  status    Check registry server status

Examples:
  praisonai registry serve
  praisonai registry serve --port 7777 --token mysecret
  praisonai registry serve --read-only
  praisonai registry status --registry http://localhost:7777

Options for 'serve':
  --host HOST       Host to bind to (default: 127.0.0.1)
  --port PORT       Port to bind to (default: 7777)
  --dir PATH        Registry directory (default: ~/.praison/registry)
  --token TOKEN     Require token for write operations
  --read-only       Disable all write operations
  --json            Output in JSON format

Options for 'status':
  --registry URL    Registry URL to check (default: http://localhost:7777)
  --json            Output in JSON format
""")
    
    def _print_error(self, message: str):
        """Print error message."""
        print(f"Error: {message}", file=sys.stderr)
    
    def _print_success(self, message: str):
        """Print success message."""
        print(f"✓ {message}")
    
    def _print_json(self, data: Any):
        """Print JSON output."""
        import json
        print(json.dumps(data, indent=2))
    
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
                        result[key] = args[i + 1]
                        i += 1
            elif arg.startswith("-") and len(arg) == 2:
                # Short flag
                for key, val in spec.items():
                    if val.get("short") == arg:
                        if val.get("flag"):
                            result[key] = True
                        elif i + 1 < len(args):
                            result[key] = args[i + 1]
                            i += 1
                        break
            i += 1
        
        return result
    
    def cmd_serve(self, args: List[str]) -> int:
        """Start local HTTP registry server."""
        spec = {
            "host": {"default": "127.0.0.1"},
            "port": {"default": "7777"},
            "dir": {"default": None},
            "token": {"default": None},
            "read_only": {"flag": True, "default": False},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        try:
            from praisonai.recipe.server import run_server
            from praisonai.recipe.registry import DEFAULT_REGISTRY_PATH
            
            host = parsed["host"]
            port = int(parsed["port"])
            registry_path = Path(parsed["dir"]) if parsed["dir"] else DEFAULT_REGISTRY_PATH
            token = parsed["token"] or os.environ.get("PRAISONAI_REGISTRY_TOKEN")
            read_only = parsed["read_only"]
            
            if parsed["json"]:
                self._print_json({
                    "ok": True,
                    "message": "Starting registry server",
                    "host": host,
                    "port": port,
                    "registry_path": str(registry_path),
                    "read_only": read_only,
                    "auth_required": bool(token),
                })
            
            run_server(
                host=host,
                port=port,
                registry_path=registry_path,
                token=token,
                read_only=read_only,
            )
            
            return self.EXIT_SUCCESS
            
        except KeyboardInterrupt:
            print("\nServer stopped.")
            return self.EXIT_SUCCESS
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_status(self, args: List[str]) -> int:
        """Check registry server status."""
        spec = {
            "registry": {"default": "http://localhost:7777"},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        try:
            from praisonai.recipe.registry import HttpRegistry
            
            registry = HttpRegistry(parsed["registry"])
            health = registry.health()
            
            if parsed["json"]:
                self._print_json(health)
            else:
                status = "healthy" if health.get("ok") else "unhealthy"
                print(f"Registry: {parsed['registry']}")
                print(f"Status: {status}")
                if health.get("read_only"):
                    print("Mode: read-only")
                if health.get("auth_required"):
                    print("Auth: required for writes")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            if parsed["json"]:
                self._print_json({
                    "ok": False,
                    "error": str(e),
                    "registry": parsed["registry"],
                })
            else:
                self._print_error(f"Cannot connect to registry: {e}")
            return self.EXIT_NETWORK_ERROR
