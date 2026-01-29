"""
Security Audit CLI for PraisonAI.

Provides security scanning and audit capabilities.
"""

from __future__ import annotations

import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class SecurityAudit:
    """Security audit scanner for PraisonAI projects."""
    
    def __init__(self):
        self.findings: List[Dict[str, Any]] = []
    
    def scan(self, path: str = ".") -> Dict[str, Any]:
        """Scan a project for security issues.
        
        Args:
            path: Path to scan
            
        Returns:
            Audit results
        """
        self.findings = []
        
        self._check_env_files(path)
        self._check_api_keys_in_code(path)
        self._check_yaml_configs(path)
        self._check_dependencies(path)
        self._check_permissions(path)
        
        critical = sum(1 for f in self.findings if f["severity"] == "critical")
        high = sum(1 for f in self.findings if f["severity"] == "high")
        medium = sum(1 for f in self.findings if f["severity"] == "medium")
        low = sum(1 for f in self.findings if f["severity"] == "low")
        
        return {
            "path": path,
            "findings": self.findings,
            "summary": {
                "total": len(self.findings),
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low,
            },
            "passed": critical == 0 and high == 0,
        }
    
    def _check_env_files(self, path: str) -> None:
        """Check for exposed .env files."""
        env_files = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".git")]
            for f in files:
                if f == ".env" or f.endswith(".env"):
                    env_files.append(os.path.join(root, f))
        
        for env_file in env_files:
            gitignore_path = os.path.join(os.path.dirname(env_file), ".gitignore")
            if os.path.exists(gitignore_path):
                with open(gitignore_path, "r") as f:
                    gitignore = f.read()
                if ".env" not in gitignore:
                    self.findings.append({
                        "type": "exposed_env",
                        "severity": "critical",
                        "file": env_file,
                        "message": ".env file not in .gitignore - secrets may be exposed",
                        "fix": "Add '.env' to .gitignore",
                    })
            else:
                self.findings.append({
                    "type": "missing_gitignore",
                    "severity": "high",
                    "file": env_file,
                    "message": "No .gitignore found - .env file may be committed",
                    "fix": "Create .gitignore with '.env' entry",
                })
    
    def _check_api_keys_in_code(self, path: str) -> None:
        """Check for hardcoded API keys in code."""
        import re
        
        patterns = [
            (r'sk-[a-zA-Z0-9]{48}', "OpenAI API key"),
            (r'sk-ant-[a-zA-Z0-9-]{95}', "Anthropic API key"),
            (r'AIza[a-zA-Z0-9_-]{35}', "Google API key"),
            (r'xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+', "Slack bot token"),
            (r'xapp-[0-9]+-[a-zA-Z0-9]+', "Slack app token"),
        ]
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in files:
                if f.endswith((".py", ".yaml", ".yml", ".json", ".js", ".ts")):
                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                            content = fp.read()
                        
                        for pattern, key_type in patterns:
                            if re.search(pattern, content):
                                self.findings.append({
                                    "type": "hardcoded_key",
                                    "severity": "critical",
                                    "file": file_path,
                                    "message": f"Possible {key_type} found in code",
                                    "fix": "Move API key to environment variable",
                                })
                    except Exception:
                        pass
    
    def _check_yaml_configs(self, path: str) -> None:
        """Check YAML configurations for security issues."""
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.endswith((".yaml", ".yml")):
                    file_path = os.path.join(root, f)
                    try:
                        import yaml
                        with open(file_path, "r") as fp:
                            config = yaml.safe_load(fp)
                        
                        if config and isinstance(config, dict):
                            if "api_key" in str(config).lower():
                                self.findings.append({
                                    "type": "key_in_config",
                                    "severity": "high",
                                    "file": file_path,
                                    "message": "API key reference found in YAML config",
                                    "fix": "Use environment variables instead",
                                })
                    except Exception:
                        pass
    
    def _check_dependencies(self, path: str) -> None:
        """Check for known vulnerable dependencies."""
        requirements_files = ["requirements.txt", "pyproject.toml"]
        
        for req_file in requirements_files:
            req_path = os.path.join(path, req_file)
            if os.path.exists(req_path):
                self.findings.append({
                    "type": "dependency_check",
                    "severity": "low",
                    "file": req_path,
                    "message": "Run 'pip-audit' to check for vulnerable dependencies",
                    "fix": "pip install pip-audit && pip-audit",
                })
                break
    
    def _check_permissions(self, path: str) -> None:
        """Check file permissions."""
        sensitive_files = [".env", "credentials.json", "service-account.json"]
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".git")]
            for f in files:
                if f in sensitive_files:
                    file_path = os.path.join(root, f)
                    try:
                        mode = os.stat(file_path).st_mode
                        if mode & 0o077:
                            self.findings.append({
                                "type": "file_permissions",
                                "severity": "medium",
                                "file": file_path,
                                "message": "Sensitive file has overly permissive permissions",
                                "fix": f"chmod 600 {file_path}",
                            })
                    except Exception:
                        pass


def handle_audit_command(args) -> None:
    """Handle audit CLI command."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
    except ImportError:
        print("Error: Rich library required for audit display")
        return
    
    console = Console()
    audit = SecurityAudit()
    
    path = getattr(args, "path", ".")
    results = audit.scan(path)
    
    console.print(Panel.fit(
        f"[bold]Security Audit Results[/bold]\n"
        f"Path: {results['path']}",
        title="PraisonAI Security Audit",
    ))
    console.print()
    
    summary = results["summary"]
    if summary["total"] == 0:
        console.print("[green]✓ No security issues found![/green]")
    else:
        table = Table(title="Summary")
        table.add_column("Severity", style="bold")
        table.add_column("Count", justify="right")
        
        if summary["critical"] > 0:
            table.add_row("[red]Critical[/red]", str(summary["critical"]))
        if summary["high"] > 0:
            table.add_row("[orange1]High[/orange1]", str(summary["high"]))
        if summary["medium"] > 0:
            table.add_row("[yellow]Medium[/yellow]", str(summary["medium"]))
        if summary["low"] > 0:
            table.add_row("[blue]Low[/blue]", str(summary["low"]))
        
        console.print(table)
        console.print()
        
        findings_table = Table(title="Findings")
        findings_table.add_column("Severity")
        findings_table.add_column("Type")
        findings_table.add_column("File")
        findings_table.add_column("Message")
        
        severity_colors = {
            "critical": "red",
            "high": "orange1",
            "medium": "yellow",
            "low": "blue",
        }
        
        for finding in results["findings"]:
            color = severity_colors.get(finding["severity"], "white")
            findings_table.add_row(
                f"[{color}]{finding['severity'].upper()}[/{color}]",
                finding["type"],
                finding["file"],
                finding["message"],
            )
        
        console.print(findings_table)
        console.print()
        
        if not results["passed"]:
            console.print("[red]✗ Audit failed - critical/high issues found[/red]")
        else:
            console.print("[yellow]⚠ Audit passed with warnings[/yellow]")


def add_audit_parser(subparsers) -> None:
    """Add audit subparser to CLI."""
    audit_parser = subparsers.add_parser(
        "audit",
        help="Run security audit on project",
    )
    audit_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to audit (default: current directory)",
    )
    audit_parser.set_defaults(func=handle_audit_command)
