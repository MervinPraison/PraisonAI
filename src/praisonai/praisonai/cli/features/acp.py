"""
ACP CLI handler for PraisonAI.

Provides the `praisonai acp` command for IDE/editor integration.
"""

import argparse
import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)


class ACPHandler:
    """Handler for ACP CLI commands."""
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        """Add ACP-specific arguments to parser."""
        parser.add_argument(
            "-w", "--workspace",
            type=str,
            default=".",
            help="Workspace root directory (default: current directory)"
        )
        parser.add_argument(
            "-a", "--agent",
            type=str,
            default="default",
            help="Agent name or configuration file"
        )
        parser.add_argument(
            "--agents",
            type=str,
            help="Multi-agent configuration YAML file"
        )
        parser.add_argument(
            "--router",
            action="store_true",
            help="Enable router agent for task delegation"
        )
        parser.add_argument(
            "-m", "--model",
            type=str,
            help="LLM model to use"
        )
        parser.add_argument(
            "-r", "--resume",
            type=str,
            nargs="?",
            const="__last__",
            help="Resume session by ID (or --resume --last for most recent)"
        )
        parser.add_argument(
            "--last",
            action="store_true",
            help="Resume the last session (use with --resume)"
        )
        parser.add_argument(
            "--approve",
            type=str,
            choices=["manual", "auto", "scoped"],
            default="manual",
            help="Approval mode for actions (default: manual)"
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            default=True,
            help="Read-only mode (default: enabled)"
        )
        parser.add_argument(
            "--allow-write",
            action="store_true",
            help="Allow file write operations"
        )
        parser.add_argument(
            "--allow-shell",
            action="store_true",
            help="Allow shell command execution"
        )
        parser.add_argument(
            "--allow-network",
            action="store_true",
            help="Allow network requests"
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug logging to stderr"
        )
        parser.add_argument(
            "--profile",
            type=str,
            help="Use named profile from config"
        )
    
    @staticmethod
    def handle(args: argparse.Namespace) -> int:
        """
        Handle ACP command execution.
        
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        # Check if ACP SDK is available
        try:
            import importlib.util
            if importlib.util.find_spec("acp") is None:
                print(
                    "Error: agent-client-protocol package not installed.\n"
                    "Install with: pip install praisonai[acp]\n"
                    "Or: pip install agent-client-protocol",
                    file=sys.stderr
                )
                return 1
        except Exception as e:
            print(f"Error checking ACP availability: {e}", file=sys.stderr)
            return 1
        
        # Import ACP module
        try:
            from praisonai.acp import serve
        except ImportError as e:
            print(f"Error importing ACP module: {e}", file=sys.stderr)
            return 1
        
        # Determine resume session
        resume_session: Optional[str] = None
        resume_last = False
        
        if args.resume:
            if args.resume == "__last__" or args.last:
                resume_last = True
            else:
                resume_session = args.resume
        elif args.last:
            resume_last = True
        
        # Determine read-only mode
        read_only = args.read_only and not args.allow_write
        
        try:
            # Start ACP server
            serve(
                workspace=args.workspace,
                agent=args.agent,
                model=args.model,
                resume=resume_session,
                resume_last=resume_last,
                debug=args.debug,
                read_only=read_only,
                allow_write=args.allow_write,
                allow_shell=args.allow_shell,
                approval_mode=args.approve,
            )
            return 0
        except KeyboardInterrupt:
            logger.info("ACP server stopped by user")
            return 0
        except Exception as e:
            logger.exception(f"ACP server error: {e}")
            print(f"Error: {e}", file=sys.stderr)
            return 1


def setup_acp_subparser(subparsers) -> None:
    """Set up the ACP subcommand parser."""
    acp_parser = subparsers.add_parser(
        "acp",
        help="Start ACP server for IDE/editor integration",
        description=(
            "Start the Agent Client Protocol (ACP) server.\n\n"
            "This allows IDEs and editors (Zed, JetBrains, VSCode, Toad) "
            "to connect to PraisonAI agents via JSON-RPC over stdio."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  praisonai acp                    # Start with defaults
  praisonai acp --debug            # Enable debug logging
  praisonai acp --resume --last    # Resume last session
  praisonai acp --allow-write      # Enable file writes
  praisonai acp -m gpt-4o          # Use specific model

Editor Configuration:

  Zed (~/.config/zed/settings.json):
    {
      "agent_servers": {
        "PraisonAI": {
          "command": "praisonai",
          "args": ["acp"],
          "env": {}
        }
      }
    }

  JetBrains (~/.jetbrains/acp.json):
    {
      "agent_servers": {
        "PraisonAI": {
          "command": "praisonai",
          "args": ["acp"],
          "env": {}
        }
      }
    }

  Toad:
    toad acp "praisonai acp"
"""
    )
    ACPHandler.add_arguments(acp_parser)
    acp_parser.set_defaults(func=lambda args: ACPHandler.handle(args))


def run_acp_command(args: Optional[list] = None) -> int:
    """
    Run ACP command directly.
    
    This can be called from the main CLI or as a standalone entry point.
    """
    parser = argparse.ArgumentParser(
        prog="praisonai acp",
        description="Start ACP server for IDE/editor integration"
    )
    ACPHandler.add_arguments(parser)
    
    parsed_args = parser.parse_args(args)
    return ACPHandler.handle(parsed_args)


if __name__ == "__main__":
    sys.exit(run_acp_command())
