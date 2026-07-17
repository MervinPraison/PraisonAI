"""
Sandbox CLI commands for PraisonAI.

Provides CLI commands for sandbox code execution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def _ensure_backends():
    """Bootstrap praisonai-sandbox before registry imports (fail loud if missing)."""
    try:
        from praisonai._bootstrap import ensure_praisonai_sandbox

        ensure_praisonai_sandbox()
    except ImportError:
        pass


class SandboxHandler:
    """Handler for sandbox CLI commands."""
    
    def run(
        self,
        code: Optional[str] = None,
        file: Optional[str] = None,
        sandbox_type: str = "subprocess",
        image: str = "python:3.11-slim",
        timeout: int = 60,
    ) -> None:
        """Run code in a sandbox.
        
        Args:
            code: Code to execute
            file: Path to file to execute
            sandbox_type: Type of sandbox (subprocess, docker)
            image: Docker image to use
            timeout: Execution timeout in seconds
        """
        if not code and not file:
            print("Error: Provide code via --code or --file")
            return
        
        _ensure_backends()
        
        if file:
            if not os.path.exists(file):
                print(f"Error: File not found: {file}")
                return
            with open(file, "r") as f:
                code = f.read()
        
        try:
            from praisonaiagents.sandbox import ResourceLimits
            
            from praisonai_sandbox._registry import SandboxRegistry
            
            registry = SandboxRegistry.default()
            try:
                sandbox_class = registry.resolve(sandbox_type)
            except ValueError as e:
                # Don't silently downgrade. Fail loud, give a fix-it hint.
                print(
                    f"Error: sandbox '{sandbox_type}' is unavailable: {e}\n"
                    f"Available: {registry.list_names()}\n"
                    f"To install the optional backend:  pip install praisonai-sandbox[{sandbox_type}] "
                    f"or pip install \"praisonai[sandbox]\"\n"
                    f"Or explicitly choose another sandbox:  --sandbox-type subprocess"
                )
                sys.exit(2)
            
            # Pass image parameter only for Docker sandbox
            if sandbox_type == "docker":
                sandbox = sandbox_class(image=image)
            else:
                sandbox = sandbox_class()
        except ImportError as e:
            print(f"Error: {e}")
            return
        
        limits = ResourceLimits(timeout_seconds=timeout)
        
        print(f"Running in {sandbox_type} sandbox...")
        
        async def execute():
            await sandbox.start()
            try:
                result = await sandbox.execute(code, limits=limits)
                
                if result.stdout:
                    print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, file=sys.stderr, end="")
                
                if result.status.value != "completed":
                    print(f"\nStatus: {result.status.value}")
                    if result.error:
                        print(f"Error: {result.error}")
                
                return result.exit_code or 0
            finally:
                await sandbox.stop()
        
        exit_code = asyncio.run(execute())
        sys.exit(exit_code)
    
    def shell(
        self,
        sandbox_type: str = "subprocess",
        image: str = "python:3.11-slim",
    ) -> None:
        """Start an interactive sandbox shell.
        
        Args:
            sandbox_type: Type of sandbox (subprocess, docker)
            image: Docker image to use
        """
        _ensure_backends()
        try:
            from praisonaiagents.sandbox import ResourceLimits
            
            from praisonai_sandbox._registry import SandboxRegistry
            
            registry = SandboxRegistry.default()
            try:
                sandbox_class = registry.resolve(sandbox_type)
            except ValueError as e:
                # Don't silently downgrade. Fail loud, give a fix-it hint.
                print(
                    f"Error: sandbox '{sandbox_type}' is unavailable: {e}\n"
                    f"Available: {registry.list_names()}\n"
                    f"To install the optional backend:  pip install praisonai-sandbox[{sandbox_type}] "
                    f"or pip install \"praisonai[sandbox]\"\n"
                    f"Or explicitly choose another sandbox:  --sandbox-type subprocess"
                )
                sys.exit(2)
            
            # Pass image parameter only for Docker sandbox
            if sandbox_type == "docker":
                sandbox = sandbox_class(image=image)
            else:
                sandbox = sandbox_class()
        except ImportError as e:
            print(f"Error: {e}")
            return
        
        print(f"Starting {sandbox_type} sandbox shell...")
        print("Type 'exit' or Ctrl+D to quit")
        print()
        
        async def run_shell():
            await sandbox.start()
            try:
                while True:
                    try:
                        code = input(">>> ")
                        if code.strip().lower() == "exit":
                            break
                        if not code.strip():
                            continue
                        
                        result = await sandbox.execute(
                            code,
                            limits=ResourceLimits(timeout_seconds=30),
                        )
                        
                        if result.stdout:
                            print(result.stdout, end="")
                        if result.stderr:
                            print(result.stderr, file=sys.stderr, end="")
                        if result.error:
                            print(f"Error: {result.error}")
                    except EOFError:
                        break
                    except KeyboardInterrupt:
                        print()
                        continue
            finally:
                await sandbox.stop()
        
        asyncio.run(run_shell())
    
    def status(self) -> None:
        """Check sandbox backend availability."""
        print("Sandbox backends:")
        print()
        try:
            from praisonaiagents.sandbox import SandboxManager, SandboxConfig

            manager = SandboxManager(SandboxConfig.subprocess())
            for name, info in sorted(manager.get_available_types().items()):
                flag = "Available" if info.get("available") else "Unavailable"
                print(f"  {name}: {flag}")
        except ImportError as exc:
            print(f"  Error: {exc}")


def handle_sandbox_command(args) -> None:
    """Handle sandbox CLI command."""
    handler = SandboxHandler()
    
    subcommand = getattr(args, "sandbox_command", None) or "status"
    
    if subcommand == "run":
        handler.run(
            code=getattr(args, "code", None),
            file=getattr(args, "file", None),
            sandbox_type=getattr(args, "type", "subprocess"),
            image=getattr(args, "image", "python:3.11-slim"),
            timeout=getattr(args, "timeout", 60),
        )
    elif subcommand == "shell":
        handler.shell(
            sandbox_type=getattr(args, "type", "subprocess"),
            image=getattr(args, "image", "python:3.11-slim"),
        )
    elif subcommand == "status":
        handler.status()
    else:
        print(f"Unknown sandbox command: {subcommand}")
        print("Available commands: run, shell, status")


def add_sandbox_parser(subparsers) -> None:
    """Add sandbox subparser to CLI."""
    sandbox_parser = subparsers.add_parser(
        "sandbox",
        help="Run code in a sandbox",
    )
    
    sandbox_subparsers = sandbox_parser.add_subparsers(
        dest="sandbox_command",
        help="Sandbox commands",
    )
    
    run_parser = sandbox_subparsers.add_parser(
        "run",
        help="Run code in sandbox",
    )
    run_parser.add_argument(
        "--code", "-c",
        help="Code to execute",
    )
    run_parser.add_argument(
        "--file", "-f",
        help="File to execute",
    )
    run_parser.add_argument(
        "--type", "-t",
        choices=["subprocess", "docker"],
        default="subprocess",
        help="Sandbox type (default: subprocess)",
    )
    run_parser.add_argument(
        "--image",
        default="python:3.11-slim",
        help="Docker image (default: python:3.11-slim)",
    )
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds (default: 60)",
    )
    
    shell_parser = sandbox_subparsers.add_parser(
        "shell",
        help="Start interactive sandbox shell",
    )
    shell_parser.add_argument(
        "--type", "-t",
        choices=["subprocess", "docker"],
        default="subprocess",
        help="Sandbox type (default: subprocess)",
    )
    shell_parser.add_argument(
        "--image",
        default="python:3.11-slim",
        help="Docker image (default: python:3.11-slim)",
    )
    
    sandbox_subparsers.add_parser(
        "status",
        help="Check sandbox availability",
    )
    
    sandbox_parser.set_defaults(func=handle_sandbox_command)
