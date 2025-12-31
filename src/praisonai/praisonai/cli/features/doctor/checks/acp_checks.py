"""
ACP health checks for PraisonAI Doctor.
"""

import asyncio
import logging

from ..models import CheckCategory, CheckResult, CheckStatus
from ..registry import register_check

logger = logging.getLogger(__name__)


@register_check(
    id="acp_module",
    title="ACP Module Available",
    category=CheckCategory.TOOLS,
    description="Check if ACP module is installed"
)
def check_acp_module() -> CheckResult:
    """Check if ACP module is available."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("praisonai.acp")
        
        if spec is not None:
            return CheckResult(
                status=CheckStatus.PASS,
                message="ACP module is available",
                details={"module": "praisonai.acp"}
            )
        else:
            return CheckResult(
                status=CheckStatus.WARN,
                message="ACP module not found",
                details={"hint": "ACP module should be part of praisonai package"}
            )
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"Error checking ACP module: {e}",
            details={"error": str(e)}
        )


@register_check(
    id="acp_sdk",
    title="ACP SDK Available",
    category=CheckCategory.TOOLS,
    description="Check if agent-client-protocol SDK is installed"
)
def check_acp_sdk() -> CheckResult:
    """Check if ACP SDK is available."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("acp")
        
        if spec is not None:
            return CheckResult(
                status=CheckStatus.PASS,
                message="ACP SDK (agent-client-protocol) is installed",
                details={"package": "agent-client-protocol"}
            )
        else:
            return CheckResult(
                status=CheckStatus.INFO,
                message="ACP SDK not installed (optional)",
                details={"hint": "Install with: pip install agent-client-protocol"}
            )
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"Error checking ACP SDK: {e}",
            details={"error": str(e)}
        )


@register_check(
    id="acp_server",
    title="ACP Server Import",
    category=CheckCategory.TOOLS,
    description="Check if ACP server can be imported"
)
def check_acp_server() -> CheckResult:
    """Check if ACP server can be imported."""
    try:
        from praisonai.acp import ACPServer  # noqa: F401
        
        return CheckResult(
            status=CheckStatus.PASS,
            message="ACP server can be imported",
            details={"class": "ACPServer"}
        )
    except ImportError as e:
        return CheckResult(
            status=CheckStatus.WARN,
            message=f"ACP server import failed: {e}",
            details={"error": str(e)}
        )
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"Error importing ACP server: {e}",
            details={"error": str(e)}
        )


@register_check(
    id="acp_config",
    title="ACP Configuration",
    category=CheckCategory.CONFIG,
    description="Check ACP configuration"
)
def check_acp_config() -> CheckResult:
    """Check ACP configuration."""
    import os
    
    config = {
        "approval_mode": os.environ.get("PRAISONAI_APPROVAL_MODE", "manual"),
        "allow_write": os.environ.get("PRAISONAI_ALLOW_WRITE", "false"),
        "allow_shell": os.environ.get("PRAISONAI_ALLOW_SHELL", "false"),
    }
    
    return CheckResult(
        status=CheckStatus.PASS,
        message=f"ACP configured with approval_mode={config['approval_mode']}",
        details=config
    )


@register_check(
    id="acp_runtime",
    title="ACP Runtime Check",
    category=CheckCategory.TOOLS,
    description="Check if ACP runtime can start",
    requires_deep=True
)
def check_acp_runtime() -> CheckResult:
    """Check if ACP runtime can start."""
    try:
        from praisonai.cli.features.interactive_runtime import create_runtime
        
        async def _check():
            runtime = create_runtime(
                workspace=".",
                lsp=False,
                acp=True
            )
            try:
                await runtime.start()
                ready = runtime.acp_ready
                error = runtime._acp_state.error
                read_only = runtime.read_only
                return ready, error, read_only
            finally:
                await runtime.stop()
        
        ready, error, read_only = asyncio.run(_check())
        
        if ready:
            return CheckResult(
                status=CheckStatus.PASS,
                message="ACP runtime started successfully",
                details={"ready": True, "read_only": read_only}
            )
        else:
            return CheckResult(
                status=CheckStatus.WARN,
                message=f"ACP runtime failed to start: {error}",
                details={"ready": False, "error": error, "read_only": read_only}
            )
            
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"ACP runtime check failed: {e}",
            details={"error": str(e)}
        )


@register_check(
    id="interactive_runtime",
    title="Interactive Runtime Check",
    category=CheckCategory.TOOLS,
    description="Check if full interactive runtime can start",
    requires_deep=True
)
def check_interactive_runtime() -> CheckResult:
    """Check if full interactive runtime can start."""
    try:
        from praisonai.cli.features.interactive_runtime import create_runtime
        
        async def _check():
            runtime = create_runtime(
                workspace=".",
                lsp=True,
                acp=True
            )
            try:
                await runtime.start()
                status = runtime.get_status()
                return status
            finally:
                await runtime.stop()
        
        status = asyncio.run(_check())
        
        lsp_ready = status.get("lsp", {}).get("ready", False)
        acp_ready = status.get("acp", {}).get("ready", False)
        
        if lsp_ready and acp_ready:
            return CheckResult(
                status=CheckStatus.PASS,
                message="Interactive runtime fully operational",
                details=status
            )
        elif lsp_ready or acp_ready:
            return CheckResult(
                status=CheckStatus.WARN,
                message="Interactive runtime partially operational",
                details=status
            )
        else:
            return CheckResult(
                status=CheckStatus.FAIL,
                message="Interactive runtime failed to start",
                details=status
            )
            
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"Interactive runtime check failed: {e}",
            details={"error": str(e)}
        )


def register_acp_checks():
    """Register all ACP checks."""
    pass
