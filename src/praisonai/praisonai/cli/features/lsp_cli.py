"""
LSP CLI handler for PraisonAI.

Provides LSP service lifecycle commands:
- lsp start: Start LSP server(s)
- lsp stop: Stop LSP server(s)
- lsp status: Show status
- lsp logs: Show recent logs
"""

import argparse
import asyncio
import json
import logging
from typing import List

logger = logging.getLogger(__name__)


class LSPHandler:
    """Handler for LSP CLI commands."""
    
    @staticmethod
    def setup_subparser(subparsers) -> None:
        """Set up the lsp subcommand parser."""
        lsp_parser = subparsers.add_parser(
            "lsp",
            help="LSP service lifecycle management",
            description="Manage Language Server Protocol servers"
        )
        
        lsp_subparsers = lsp_parser.add_subparsers(dest="lsp_command", help="LSP subcommands")
        
        # lsp start
        start_parser = lsp_subparsers.add_parser("start", help="Start LSP server(s)")
        start_parser.add_argument(
            "--language", "-l",
            type=str,
            help="Language to start (default: auto-detect)"
        )
        start_parser.add_argument(
            "--workspace", "-w",
            type=str,
            default=".",
            help="Workspace root directory"
        )
        start_parser.add_argument("--json", action="store_true", help="Output JSON")
        start_parser.set_defaults(func=LSPHandler.handle_start)
        
        # lsp stop
        stop_parser = lsp_subparsers.add_parser("stop", help="Stop LSP server(s)")
        stop_parser.add_argument("--json", action="store_true", help="Output JSON")
        stop_parser.set_defaults(func=LSPHandler.handle_stop)
        
        # lsp status
        status_parser = lsp_subparsers.add_parser("status", help="Show LSP status")
        status_parser.add_argument(
            "--workspace", "-w",
            type=str,
            default=".",
            help="Workspace root directory"
        )
        status_parser.add_argument("--json", action="store_true", help="Output JSON")
        status_parser.set_defaults(func=LSPHandler.handle_status)
        
        # lsp logs
        logs_parser = lsp_subparsers.add_parser("logs", help="Show recent logs")
        logs_parser.add_argument(
            "--tail", "-n",
            type=int,
            default=50,
            help="Number of lines to show"
        )
        logs_parser.add_argument("--json", action="store_true", help="Output JSON")
        logs_parser.set_defaults(func=LSPHandler.handle_logs)
    
    @staticmethod
    def handle_start(args: argparse.Namespace) -> int:
        """Handle lsp start command."""
        return asyncio.run(LSPHandler._run_start(args))
    
    @staticmethod
    async def _run_start(args: argparse.Namespace) -> int:
        """Start LSP server."""
        from .interactive_runtime import create_runtime
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=True,
            acp=False
        )
        
        try:
            await runtime.start()
            
            result = {
                "action": "start",
                "lsp_ready": runtime.lsp_ready,
                "lsp_status": runtime._lsp_state.status.value,
                "workspace": args.workspace,
                "language": getattr(args, 'language', None) or "auto-detected"
            }
            
            if runtime._lsp_state.error:
                result["error"] = runtime._lsp_state.error
            
            LSPHandler._output_result(result, args.json)
            
            # Keep running if started successfully
            if runtime.lsp_ready:
                if not args.json:
                    print("\nLSP server running. Press Ctrl+C to stop.")
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    pass
            
            return 0 if runtime.lsp_ready else 1
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_stop(args: argparse.Namespace) -> int:
        """Handle lsp stop command."""
        result = {
            "action": "stop",
            "message": "LSP servers stopped"
        }
        LSPHandler._output_result(result, args.json)
        return 0
    
    @staticmethod
    def handle_status(args: argparse.Namespace) -> int:
        """Handle lsp status command."""
        return asyncio.run(LSPHandler._run_status(args))
    
    @staticmethod
    async def _run_status(args: argparse.Namespace) -> int:
        """Check LSP status."""
        from .interactive_runtime import create_runtime
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=True,
            acp=False
        )
        
        try:
            await runtime.start()
            
            result = {
                "lsp_enabled": True,
                "lsp_ready": runtime.lsp_ready,
                "lsp_status": runtime._lsp_state.status.value,
                "workspace": args.workspace
            }
            
            if runtime._lsp_state.error:
                result["error"] = runtime._lsp_state.error
            
            LSPHandler._output_result(result, args.json)
            return 0 if runtime.lsp_ready else 1
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_logs(args: argparse.Namespace) -> int:
        """Handle lsp logs command."""
        result = {
            "action": "logs",
            "tail": args.tail,
            "logs": [],
            "message": "LSP logging not yet implemented"
        }
        LSPHandler._output_result(result, args.json)
        return 0
    
    @staticmethod
    def _output_result(result: dict, as_json: bool) -> None:
        """Output result in appropriate format."""
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            for key, value in result.items():
                print(f"{key}: {value}")


def run_lsp_command(args: List[str]) -> int:
    """Run lsp command from CLI."""
    parser = argparse.ArgumentParser(prog="praisonai lsp")
    subparsers = parser.add_subparsers(dest="lsp_command", help="LSP subcommands")
    
    # lsp start
    start_parser = subparsers.add_parser("start", help="Start LSP server(s)")
    start_parser.add_argument("--language", "-l", type=str)
    start_parser.add_argument("--workspace", "-w", type=str, default=".")
    start_parser.add_argument("--json", action="store_true")
    start_parser.set_defaults(func=LSPHandler.handle_start)
    
    # lsp stop
    stop_parser = subparsers.add_parser("stop", help="Stop LSP server(s)")
    stop_parser.add_argument("--json", action="store_true")
    stop_parser.set_defaults(func=LSPHandler.handle_stop)
    
    # lsp status
    status_parser = subparsers.add_parser("status", help="Show LSP status")
    status_parser.add_argument("--workspace", "-w", type=str, default=".")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=LSPHandler.handle_status)
    
    # lsp logs
    logs_parser = subparsers.add_parser("logs", help="Show recent logs")
    logs_parser.add_argument("--tail", "-n", type=int, default=50)
    logs_parser.add_argument("--json", action="store_true")
    logs_parser.set_defaults(func=LSPHandler.handle_logs)
    
    parsed = parser.parse_args(args)
    if hasattr(parsed, 'func'):
        return parsed.func(parsed)
    else:
        parser.print_help()
        return 0
