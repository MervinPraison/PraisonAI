"""
Diagnostics export CLI handler for PraisonAI.

Provides diagnostic export functionality:
- diag export: Bundle logs, traces, config for bug reports
"""

import argparse
import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class DiagHandler:
    """Handler for diag CLI commands."""
    
    @staticmethod
    def setup_subparser(subparsers) -> None:
        """Set up the diag subcommand parser."""
        diag_parser = subparsers.add_parser(
            "diag",
            help="Diagnostics export",
            description="Export diagnostic information for bug reports"
        )
        
        diag_subparsers = diag_parser.add_subparsers(dest="diag_command", help="Diag subcommands")
        
        # diag export
        export_parser = diag_subparsers.add_parser("export", help="Export diagnostic bundle")
        export_parser.add_argument(
            "-o", "--output",
            type=str,
            help="Output path (default: praisonai-diag-{timestamp}.zip)"
        )
        export_parser.add_argument(
            "--include-logs",
            action="store_true",
            default=True,
            help="Include log files (default: true)"
        )
        export_parser.add_argument(
            "--include-config",
            action="store_true",
            default=True,
            help="Include configuration (default: true)"
        )
        export_parser.add_argument(
            "--include-trace",
            action="store_true",
            default=True,
            help="Include recent traces (default: true)"
        )
        export_parser.add_argument(
            "--workspace", "-w",
            type=str,
            default=".",
            help="Workspace root directory"
        )
        export_parser.add_argument("--json", action="store_true", help="Output JSON")
        export_parser.set_defaults(func=DiagHandler.handle_export)
    
    @staticmethod
    def handle_export(args: argparse.Namespace) -> int:
        """Handle diag export command."""
        timestamp = int(time.time())
        output_path = args.output or f"praisonai-diag-{timestamp}.zip"
        
        collected_files = []
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Collect system info
            system_info = DiagHandler._collect_system_info()
            system_file = tmppath / "system_info.json"
            with open(system_file, "w") as f:
                json.dump(system_info, f, indent=2, default=str)
            collected_files.append("system_info.json")
            
            # Collect config
            if args.include_config:
                config_files = DiagHandler._collect_config(args.workspace, tmppath)
                collected_files.extend(config_files)
            
            # Collect logs
            if args.include_logs:
                log_files = DiagHandler._collect_logs(tmppath)
                collected_files.extend(log_files)
            
            # Collect traces
            if args.include_trace:
                trace_files = DiagHandler._collect_traces(args.workspace, tmppath)
                collected_files.extend(trace_files)
            
            # Create zip
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file in tmppath.rglob("*"):
                    if file.is_file():
                        arcname = file.relative_to(tmppath)
                        zf.write(file, arcname)
        
        result = {
            "action": "export",
            "output": output_path,
            "files_collected": collected_files,
            "count": len(collected_files)
        }
        
        DiagHandler._output_result(result, args.json)
        return 0
    
    @staticmethod
    def _collect_system_info() -> dict:
        """Collect system information."""
        import platform
        import sys
        
        info = {
            "timestamp": time.time(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python_version": sys.version
            },
            "praisonai": {}
        }
        
        # Get PraisonAI version
        try:
            from praisonai.version import __version__
            info["praisonai"]["version"] = __version__
        except ImportError:
            info["praisonai"]["version"] = "unknown"
        
        # Get praisonaiagents version
        try:
            import praisonaiagents
            info["praisonai"]["agents_version"] = getattr(praisonaiagents, '__version__', 'unknown')
        except ImportError:
            info["praisonai"]["agents_version"] = "not installed"
        
        # Check for optional dependencies
        info["dependencies"] = {}
        for dep in ["acp", "litellm", "openai", "anthropic", "google.generativeai"]:
            try:
                __import__(dep.split(".")[0])
                info["dependencies"][dep] = "installed"
            except ImportError:
                info["dependencies"][dep] = "not installed"
        
        # Environment (redacted)
        env_keys = [
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
            "PRAISONAI_APPROVAL_MODE", "LOGLEVEL"
        ]
        info["environment"] = {}
        for key in env_keys:
            value = os.environ.get(key)
            if value:
                if "KEY" in key or "SECRET" in key:
                    info["environment"][key] = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
                else:
                    info["environment"][key] = value
            else:
                info["environment"][key] = None
        
        return info
    
    @staticmethod
    def _collect_config(workspace: str, tmppath: Path) -> List[str]:
        """Collect configuration files."""
        collected = []
        workspace_path = Path(workspace)
        config_dir = tmppath / "config"
        config_dir.mkdir(exist_ok=True)
        
        # Look for config files
        config_patterns = [
            "agents.yaml",
            "workflow.yaml",
            ".praisonai.yaml",
            ".env.example",  # Not .env to avoid secrets
            "pyproject.toml",
        ]
        
        for pattern in config_patterns:
            for file in workspace_path.glob(pattern):
                if file.is_file():
                    dest = config_dir / file.name
                    shutil.copy(file, dest)
                    collected.append(f"config/{file.name}")
        
        return collected
    
    @staticmethod
    def _collect_logs(tmppath: Path) -> List[str]:
        """Collect log files."""
        collected = []
        logs_dir = tmppath / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # Look for log files in common locations
        log_locations = [
            Path.home() / ".praison" / "logs",
            Path.home() / ".praisonai" / "logs",
            Path("/var/log/praisonai"),
        ]
        
        for log_dir in log_locations:
            if log_dir.exists():
                for log_file in log_dir.glob("*.log"):
                    if log_file.is_file():
                        dest = logs_dir / log_file.name
                        # Only copy last 1000 lines
                        try:
                            with open(log_file) as f:
                                lines = f.readlines()[-1000:]
                            with open(dest, "w") as f:
                                f.writelines(lines)
                            collected.append(f"logs/{log_file.name}")
                        except Exception:
                            pass
        
        return collected
    
    @staticmethod
    def _collect_traces(workspace: str, tmppath: Path) -> List[str]:
        """Collect trace files."""
        collected = []
        traces_dir = tmppath / "traces"
        traces_dir.mkdir(exist_ok=True)
        
        workspace_path = Path(workspace)
        
        # Look for trace files
        trace_patterns = ["*_trace.json", "praisonai_trace*.json", "*.trace"]
        
        for pattern in trace_patterns:
            for trace_file in workspace_path.glob(pattern):
                if trace_file.is_file():
                    dest = traces_dir / trace_file.name
                    shutil.copy(trace_file, dest)
                    collected.append(f"traces/{trace_file.name}")
        
        return collected
    
    @staticmethod
    def _output_result(result: dict, as_json: bool) -> None:
        """Output result in appropriate format."""
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"Diagnostic bundle created: {result['output']}")
            print(f"Files collected: {result['count']}")
            for f in result['files_collected']:
                print(f"  - {f}")


def run_diag_command(args: List[str]) -> int:
    """Run diag command from CLI."""
    parser = argparse.ArgumentParser(prog="praisonai diag")
    subparsers = parser.add_subparsers(dest="diag_command", help="Diag subcommands")
    
    # diag export
    export_parser = subparsers.add_parser("export", help="Export diagnostic bundle")
    export_parser.add_argument("-o", "--output", type=str)
    export_parser.add_argument("--include-logs", action="store_true", default=True)
    export_parser.add_argument("--include-config", action="store_true", default=True)
    export_parser.add_argument("--include-trace", action="store_true", default=True)
    export_parser.add_argument("--workspace", "-w", type=str, default=".")
    export_parser.add_argument("--json", action="store_true")
    export_parser.set_defaults(func=DiagHandler.handle_export)
    
    parsed = parser.parse_args(args)
    if hasattr(parsed, 'func'):
        return parsed.func(parsed)
    else:
        parser.print_help()
        return 0
