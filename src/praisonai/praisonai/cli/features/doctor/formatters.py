"""
Output formatters for the Doctor CLI module.

Provides text and JSON formatting with secret redaction.
"""

import json
import re
import sys
from typing import Any, Dict, List, Optional, TextIO
from .models import CheckResult, CheckStatus, DoctorReport, ReportSummary


# Patterns for detecting secrets
SECRET_PATTERNS = [
    re.compile(r'(sk-[a-zA-Z0-9]{20,})', re.IGNORECASE),  # OpenAI
    re.compile(r'(sk-ant-[a-zA-Z0-9-]{20,})', re.IGNORECASE),  # Anthropic
    re.compile(r'(AIza[a-zA-Z0-9_-]{35})', re.IGNORECASE),  # Google
    re.compile(r'(tvly-[a-zA-Z0-9]{20,})', re.IGNORECASE),  # Tavily
    re.compile(r'(xai-[a-zA-Z0-9]{20,})', re.IGNORECASE),  # xAI
    re.compile(r'([a-zA-Z0-9_-]*api[_-]?key[a-zA-Z0-9_-]*=\s*["\']?[a-zA-Z0-9_-]{16,})', re.IGNORECASE),
    re.compile(r'([a-zA-Z0-9_-]*token[a-zA-Z0-9_-]*=\s*["\']?[a-zA-Z0-9_-]{16,})', re.IGNORECASE),
    re.compile(r'([a-zA-Z0-9_-]*secret[a-zA-Z0-9_-]*=\s*["\']?[a-zA-Z0-9_-]{16,})', re.IGNORECASE),
    re.compile(r'(password\s*=\s*["\']?[^\s"\']{8,})', re.IGNORECASE),
]

# Known API key environment variable names
API_KEY_ENV_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_API_KEY",
    "HF_TOKEN",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGSMITH_API_KEY",
    "AGENTOPS_API_KEY",
    "WANDB_API_KEY",
    "DATADOG_API_KEY",
    "BRAINTRUST_API_KEY",
    "YDC_API_KEY",
]


def redact_secrets(text: str, show_prefix_suffix: bool = False) -> str:
    """
    Redact secrets from text.
    
    Args:
        text: Text to redact
        show_prefix_suffix: If True, show first 4 and last 4 chars
        
    Returns:
        Text with secrets redacted
    """
    if not text:
        return text
    
    result = text
    
    for pattern in SECRET_PATTERNS:
        def replace_match(match):
            secret = match.group(1)
            if show_prefix_suffix and len(secret) > 12:
                return f"{secret[:4]}...{secret[-4:]}"
            return "***REDACTED***"
        result = pattern.sub(replace_match, result)
    
    return result


def redact_dict(data: Dict[str, Any], show_prefix_suffix: bool = False) -> Dict[str, Any]:
    """
    Recursively redact secrets from a dictionary.
    
    Args:
        data: Dictionary to redact
        show_prefix_suffix: If True, show first 4 and last 4 chars
        
    Returns:
        Dictionary with secrets redacted
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            # Check if key suggests it's a secret
            key_lower = key.lower()
            if any(s in key_lower for s in ["key", "token", "secret", "password", "credential"]):
                if show_prefix_suffix and len(value) > 12:
                    result[key] = f"{value[:4]}...{value[-4:]}"
                else:
                    result[key] = "***REDACTED***"
            else:
                result[key] = redact_secrets(value, show_prefix_suffix)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, show_prefix_suffix)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(v, show_prefix_suffix) if isinstance(v, dict)
                else redact_secrets(v, show_prefix_suffix) if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result


class BaseFormatter:
    """Base class for output formatters."""
    
    def __init__(
        self,
        no_color: bool = False,
        quiet: bool = False,
        redact: bool = True,
        show_prefix_suffix: bool = False,
    ):
        self.no_color = no_color or not sys.stdout.isatty()
        self.quiet = quiet
        self.redact = redact
        self.show_prefix_suffix = show_prefix_suffix
    
    def format_report(self, report: DoctorReport) -> str:
        """Format a complete report."""
        raise NotImplementedError
    
    def format_result(self, result: CheckResult) -> str:
        """Format a single check result."""
        raise NotImplementedError
    
    def write(self, report: DoctorReport, output: Optional[TextIO] = None) -> None:
        """Write formatted report to output."""
        output = output or sys.stdout
        output.write(self.format_report(report))
        if not self.format_report(report).endswith("\n"):
            output.write("\n")


class TextFormatter(BaseFormatter):
    """Text formatter with optional color support."""
    
    # ANSI color codes
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "cyan": "\033[36m",
        "white": "\033[37m",
    }
    
    STATUS_COLORS = {
        CheckStatus.PASS: "green",
        CheckStatus.WARN: "yellow",
        CheckStatus.FAIL: "red",
        CheckStatus.SKIP: "dim",
        CheckStatus.ERROR: "red",
    }
    
    STATUS_SYMBOLS = {
        CheckStatus.PASS: "✓",
        CheckStatus.WARN: "⚠",
        CheckStatus.FAIL: "✗",
        CheckStatus.SKIP: "○",
        CheckStatus.ERROR: "✗",
    }
    
    def _color(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if self.no_color:
            return text
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"
    
    def _status_symbol(self, status: CheckStatus) -> str:
        """Get colored status symbol."""
        symbol = self.STATUS_SYMBOLS.get(status, "?")
        color = self.STATUS_COLORS.get(status, "white")
        return self._color(symbol, color)
    
    def format_result(self, result: CheckResult) -> str:
        """Format a single check result."""
        symbol = self._status_symbol(result.status)
        message = result.message
        if self.redact:
            message = redact_secrets(message, self.show_prefix_suffix)
        
        line = f"{symbol} {result.title}: {message}"
        
        if result.details and not self.quiet:
            details = result.details
            if self.redact:
                details = redact_secrets(details, self.show_prefix_suffix)
            line += f"\n    {self._color(details, 'dim')}"
        
        if result.remediation and result.status in (CheckStatus.FAIL, CheckStatus.ERROR):
            line += f"\n    {self._color('Fix:', 'yellow')} {result.remediation}"
        
        return line
    
    def format_summary(self, summary: ReportSummary, strict: bool = False) -> str:
        """Format the summary section."""
        parts = []
        
        if summary.passed > 0:
            parts.append(self._color(f"{summary.passed} passed", "green"))
        if summary.warnings > 0:
            color = "red" if strict else "yellow"
            parts.append(self._color(f"{summary.warnings} warnings", color))
        if summary.failed > 0:
            parts.append(self._color(f"{summary.failed} failed", "red"))
        if summary.skipped > 0:
            parts.append(self._color(f"{summary.skipped} skipped", "dim"))
        if summary.errors > 0:
            parts.append(self._color(f"{summary.errors} errors", "red"))
        
        return f"{summary.total} checks: " + ", ".join(parts)
    
    def format_report(self, report: DoctorReport) -> str:
        """Format a complete report."""
        lines = []
        
        # Header
        if not self.quiet:
            header = f"PraisonAI Doctor v{report.version}"
            lines.append(self._color(header, "bold"))
            lines.append("━" * 70)
        
        # Results
        for result in report.results:
            lines.append(self.format_result(result))
        
        # Summary
        if not self.quiet:
            lines.append("━" * 70)
        lines.append(self.format_summary(report.summary))
        
        # Duration
        if not self.quiet and report.duration_ms > 0:
            lines.append(self._color(f"Completed in {report.duration_ms:.0f}ms", "dim"))
        
        return "\n".join(lines)


class JsonFormatter(BaseFormatter):
    """JSON formatter with deterministic output."""
    
    def format_result(self, result: CheckResult) -> str:
        """Format a single check result as JSON."""
        data = result.to_dict()
        if self.redact:
            data = redact_dict(data, self.show_prefix_suffix)
        return json.dumps(data, indent=2, sort_keys=True)
    
    def format_report(self, report: DoctorReport) -> str:
        """Format a complete report as JSON."""
        data = report.to_dict()
        if self.redact:
            data = redact_dict(data, self.show_prefix_suffix)
        
        # Ensure deterministic ordering
        return json.dumps(data, indent=2, sort_keys=True)
    
    def write(self, report: DoctorReport, output: Optional[TextIO] = None) -> None:
        """Write formatted report to output."""
        output = output or sys.stdout
        output.write(self.format_report(report))
        output.write("\n")


def get_formatter(
    format_type: str = "text",
    no_color: bool = False,
    quiet: bool = False,
    redact: bool = True,
    show_prefix_suffix: bool = False,
) -> BaseFormatter:
    """
    Get a formatter instance.
    
    Args:
        format_type: "text" or "json"
        no_color: Disable ANSI colors
        quiet: Minimal output
        redact: Redact secrets
        show_prefix_suffix: Show partial secrets
        
    Returns:
        Formatter instance
    """
    if format_type == "json":
        return JsonFormatter(
            no_color=True,  # JSON never has colors
            quiet=quiet,
            redact=redact,
            show_prefix_suffix=show_prefix_suffix,
        )
    return TextFormatter(
        no_color=no_color,
        quiet=quiet,
        redact=redact,
        show_prefix_suffix=show_prefix_suffix,
    )
