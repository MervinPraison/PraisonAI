"""
Doctor CLI module for PraisonAI.

Provides comprehensive health checks, diagnostics, and validation for the PraisonAI ecosystem.

Commands:
    praisonai doctor              - Run fast default checks
    praisonai doctor env          - Environment and API key validation
    praisonai doctor config       - Configuration file validation
    praisonai doctor tools        - Tool availability checks
    praisonai doctor db           - Database connectivity checks
    praisonai doctor mcp          - MCP server validation
    praisonai doctor obs          - Observability provider checks
    praisonai doctor skills       - Agent skills validation
    praisonai doctor memory       - Memory/session storage checks
    praisonai doctor permissions  - Filesystem permission checks
    praisonai doctor network      - Network connectivity checks
    praisonai doctor performance  - Import time analysis
    praisonai doctor ci           - CI-optimized checks
    praisonai doctor selftest     - Minimal agent dry-run
"""

__version__ = "1.0.0"

__all__ = [
    "DoctorHandler",
    "DoctorEngine",
    "CheckResult",
    "CheckStatus",
    "DoctorReport",
    "CheckRegistry",
    "TextFormatter",
    "JsonFormatter",
]


def __getattr__(name: str):
    """Lazy load doctor components to minimize import overhead."""
    if name == "DoctorHandler":
        from .handler import DoctorHandler
        return DoctorHandler
    elif name == "DoctorEngine":
        from .engine import DoctorEngine
        return DoctorEngine
    elif name == "CheckResult":
        from .models import CheckResult
        return CheckResult
    elif name == "CheckStatus":
        from .models import CheckStatus
        return CheckStatus
    elif name == "DoctorReport":
        from .models import DoctorReport
        return DoctorReport
    elif name == "CheckRegistry":
        from .registry import CheckRegistry
        return CheckRegistry
    elif name == "TextFormatter":
        from .formatters import TextFormatter
        return TextFormatter
    elif name == "JsonFormatter":
        from .formatters import JsonFormatter
        return JsonFormatter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
