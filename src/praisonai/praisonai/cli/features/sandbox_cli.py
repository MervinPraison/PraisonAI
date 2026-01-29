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
        
        if file:
            if not os.path.exists(file):
                print(f"Error: File not found: {file}")
                return
            with open(file, "r") as f:
                code = f.read()
        
        try:
            from praisonaiagents.sandbox import ResourceLimits
            
            if sandbox_type == "docker":
                from praisonai.sandbox import DockerSandbox
                sandbox = DockerSandbox(image=image)
            else:
                from praisonai.sandbox import SubprocessSandbox
                sandbox = SubprocessSandbox()
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
        try:
            from praisonaiagents.sandbox import ResourceLimits
            
            if sandbox_type == "docker":
                from praisonai.sandbox import DockerSandbox
                sandbox = DockerSandbox(image=image)
            else:
                from praisonai.sandbox import SubprocessSandbox
                sandbox = SubprocessSandbox()
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
        """Check sandbox availability."""
        print("Sandbox Status:")
        print()
        
        print("Subprocess sandbox: Available")
        
        try:
            from praisonai.sandbox import DockerSandbox
            sandbox = DockerSandbox()
            if sandbox.is_available:
                print("Docker sandbox: Available")
            else:
                print("Docker sandbox: Not available (Docker not running)")
        except ImportError:
            print("Docker sandbox: Not available (dependencies not installed)")


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
