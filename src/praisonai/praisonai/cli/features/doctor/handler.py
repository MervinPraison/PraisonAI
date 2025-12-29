"""
Doctor CLI handler for PraisonAI.

Provides the main DoctorHandler class that integrates with the CLI.
"""

import argparse
import sys
from typing import List, Optional

from ..base import CommandHandler
from .models import CheckCategory, DoctorConfig, DoctorReport
from .engine import DoctorEngine
from .registry import get_registry
from .formatters import get_formatter


class DoctorHandler(CommandHandler):
    """
    Handler for the 'praisonai doctor' command.
    
    Provides comprehensive health checks and diagnostics.
    """
    
    @property
    def feature_name(self) -> str:
        return "doctor"
    
    def get_actions(self) -> List[str]:
        return [
            "env",
            "config", 
            "tools",
            "db",
            "mcp",
            "obs",
            "skills",
            "memory",
            "permissions",
            "network",
            "performance",
            "ci",
            "selftest",
        ]
    
    def _register_checks(self) -> None:
        """Register all doctor checks."""
        from .checks import register_all_checks
        register_all_checks()
    
    def _parse_args(self, args: List[str]) -> argparse.Namespace:
        """Parse doctor command arguments."""
        parser = argparse.ArgumentParser(
            prog="praisonai doctor",
            description="PraisonAI health checks and diagnostics",
        )
        
        # Subcommand
        parser.add_argument(
            "subcommand",
            nargs="?",
            choices=self.get_actions() + [None],
            help="Subcommand to run (default: run all fast checks)",
        )
        
        # Global flags
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output in JSON format",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format (default: text)",
        )
        parser.add_argument(
            "--output", "-o",
            type=str,
            help="Write report to file",
        )
        parser.add_argument(
            "--deep",
            action="store_true",
            help="Enable deeper probes (DB connects, network checks)",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=10.0,
            help="Per-check timeout in seconds (default: 10)",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Treat warnings as failures",
        )
        parser.add_argument(
            "--quiet", "-q",
            action="store_true",
            help="Minimal output",
        )
        parser.add_argument(
            "--no-color",
            action="store_true",
            help="Disable ANSI colors",
        )
        parser.add_argument(
            "--only",
            type=str,
            help="Only run these check IDs (comma-separated)",
        )
        parser.add_argument(
            "--skip",
            type=str,
            help="Skip these check IDs (comma-separated)",
        )
        parser.add_argument(
            "--list-checks",
            action="store_true",
            help="List available check IDs",
        )
        parser.add_argument(
            "--version",
            action="store_true",
            help="Show doctor module version",
        )
        
        # Subcommand-specific flags
        parser.add_argument(
            "--show-keys",
            action="store_true",
            help="Show masked API key values (env subcommand)",
        )
        parser.add_argument(
            "--require",
            type=str,
            help="Require these env vars (comma-separated)",
        )
        parser.add_argument(
            "--file", "-f",
            type=str,
            help="Config file to validate (config subcommand)",
        )
        parser.add_argument(
            "--schema",
            action="store_true",
            help="Print expected schema (config subcommand)",
        )
        parser.add_argument(
            "--dsn",
            type=str,
            help="Database DSN (db subcommand)",
        )
        parser.add_argument(
            "--provider",
            type=str,
            help="Provider name (db/obs subcommand)",
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            default=True,
            help="Read-only mode for DB checks (default: true)",
        )
        parser.add_argument(
            "--name",
            type=str,
            help="Name filter (mcp/tools subcommand)",
        )
        parser.add_argument(
            "--category",
            type=str,
            help="Category filter (tools subcommand)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="all_checks",
            help="Show all items (tools subcommand)",
        )
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Show only missing items (tools subcommand)",
        )
        parser.add_argument(
            "--list-tools",
            action="store_true",
            help="List MCP tools (mcp subcommand)",
        )
        parser.add_argument(
            "--path",
            type=str,
            help="Path to check (skills subcommand)",
        )
        parser.add_argument(
            "--all-installed",
            action="store_true",
            help="Check all installed skills",
        )
        parser.add_argument(
            "--budget-ms",
            type=int,
            help="Import time budget in ms (performance subcommand)",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=10,
            dest="top_n",
            help="Number of top items to show (default: 10)",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Stop on first failure (ci subcommand)",
        )
        parser.add_argument(
            "--mock",
            action="store_true",
            default=True,
            help="Use mock mode (selftest, default: true)",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Use live API calls (selftest)",
        )
        parser.add_argument(
            "--model",
            type=str,
            help="Model to use for selftest",
        )
        parser.add_argument(
            "--save-report",
            action="store_true",
            help="Save selftest report",
        )
        
        return parser.parse_args(args)
    
    def _build_config(self, args: argparse.Namespace) -> DoctorConfig:
        """Build DoctorConfig from parsed arguments."""
        return DoctorConfig(
            deep=args.deep,
            timeout=args.timeout if args.deep else min(args.timeout, 10.0),
            strict=args.strict,
            quiet=args.quiet,
            no_color=args.no_color,
            format="json" if args.json else args.format,
            output_path=args.output,
            only=args.only.split(",") if args.only else [],
            skip=args.skip.split(",") if args.skip else [],
            show_keys=args.show_keys,
            require_keys=args.require.split(",") if args.require else [],
            config_file=args.file,
            dsn=args.dsn,
            provider=args.provider,
            read_only=args.read_only,
            mock=args.mock and not args.live,
            live=args.live,
            model=args.model,
            budget_ms=args.budget_ms,
            top_n=args.top_n,
            fail_fast=args.fail_fast,
            list_tools=args.list_tools,
            all_checks=args.all_checks,
            missing_only=args.missing_only,
            name=args.name,
            category=args.category,
            path=args.path,
            save_report=args.save_report,
        )
    
    def _get_categories_for_subcommand(self, subcommand: Optional[str]) -> Optional[List[CheckCategory]]:
        """Get check categories for a subcommand."""
        category_map = {
            "env": [CheckCategory.ENVIRONMENT],
            "config": [CheckCategory.CONFIG],
            "tools": [CheckCategory.TOOLS],
            "db": [CheckCategory.DATABASE],
            "mcp": [CheckCategory.MCP],
            "obs": [CheckCategory.OBSERVABILITY],
            "skills": [CheckCategory.SKILLS],
            "memory": [CheckCategory.MEMORY],
            "permissions": [CheckCategory.PERMISSIONS],
            "network": [CheckCategory.NETWORK],
            "performance": [CheckCategory.PERFORMANCE],
            "selftest": [CheckCategory.SELFTEST],
            "ci": None,  # CI runs all checks
        }
        return category_map.get(subcommand)
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> int:
        """
        Execute the doctor command.
        
        Args:
            action: The subcommand or empty string
            action_args: Additional arguments
            
        Returns:
            Exit code (0=pass, 1=fail, 2=error)
        """
        # Combine action and action_args for parsing
        all_args = [action] + action_args if action and action != "help" else action_args
        
        try:
            args = self._parse_args(all_args)
        except SystemExit:
            return 0  # Help was shown
        
        # Handle special flags
        if args.version:
            from . import __version__
            print(f"PraisonAI Doctor v{__version__}")
            return 0
        
        # Register all checks
        self._register_checks()
        
        if args.list_checks:
            registry = get_registry()
            print(registry.list_checks_text())
            return 0
        
        # Build config
        config = self._build_config(args)
        
        # Handle CI mode
        if args.subcommand == "ci":
            config.format = "json"
            config.no_color = True
            config.quiet = True
        
        # Get categories for subcommand
        categories = self._get_categories_for_subcommand(args.subcommand)
        
        # Run doctor
        engine = DoctorEngine(config)
        report = engine.run(categories=categories)
        
        # Format output
        formatter = get_formatter(
            format_type=config.format,
            no_color=config.no_color,
            quiet=config.quiet,
            show_prefix_suffix=config.show_keys,
        )
        
        # Write output
        if config.output_path:
            with open(config.output_path, "w") as f:
                formatter.write(report, f)
            if not config.quiet:
                print(f"Report written to: {config.output_path}")
        else:
            formatter.write(report, sys.stdout)
        
        return report.exit_code
    
    def run(self, args: List[str]) -> int:
        """
        Run the doctor command from CLI.
        
        Args:
            args: Command line arguments after 'doctor'
            
        Returns:
            Exit code
        """
        if not args:
            return self.execute("", [])
        
        action = args[0] if args else ""
        action_args = args[1:] if len(args) > 1 else []
        
        return self.execute(action, action_args)


def run_doctor(args: Optional[List[str]] = None) -> int:
    """
    Convenience function to run doctor from CLI.
    
    Args:
        args: Command line arguments (default: sys.argv[1:])
        
    Returns:
        Exit code
    """
    if args is None:
        args = sys.argv[1:]
    
    handler = DoctorHandler()
    return handler.run(args)
