"""
ACP health checks for PraisonAI Doctor.
"""

import asyncio
import logging
import os

from ..models import CheckCategory, CheckResult, CheckStatus
from ..registry import register_check

logger = logging.getLogger(__name__)


@register_check(
    id="acp_module",
    title="ACP Module Available",
    category=CheckCategory.TOOLS,
    description="Check if ACP module is installed"
)
def check_acp_module(config=None) -> CheckResult:
    """Check if ACP module is available."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("praisonai.acp")
        
        if spec is not None:
            return CheckResult(
                id="acp_module",
                title="ACP Module Available",
                category=CheckCategory.TOOLS,
                status=CheckStatus.PASS,
                message="ACP module is available",
                metadata={"module": "praisonai.acp"}
            )
        else:
            return CheckResult(
                id="acp_module",
                title="ACP Module Available",
                category=CheckCategory.TOOLS,
                status=CheckStatus.WARN,
                message="ACP module not found",
                remediation="ACP module should be part of praisonai package"
            )
    except Exception as e:
        return CheckResult(
            id="acp_module",
            title="ACP Module Available",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message=f"Error checking ACP module: {e}",
            metadata={"error": str(e)}
        )


@register_check(
    id="acp_sdk",
    title="ACP SDK Available",
    category=CheckCategory.TOOLS,
    description="Check if agent-client-protocol SDK is installed"
)
def check_acp_sdk(config=None) -> CheckResult:
    """Check if ACP SDK is available."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("acp")
        
        if spec is not None:
            return CheckResult(
                id="acp_sdk",
                title="ACP SDK Available",
                category=CheckCategory.TOOLS,
                status=CheckStatus.PASS,
                message="ACP SDK (agent-client-protocol) is installed",
                metadata={"package": "agent-client-protocol"}
            )
        else:
            return CheckResult(
                id="acp_sdk",
                title="ACP SDK Available",
                category=CheckCategory.TOOLS,
                status=CheckStatus.SKIP,
                message="ACP SDK not installed (optional)",
                remediation="Install with: pip install agent-client-protocol"
            )
    except Exception as e:
        return CheckResult(
            id="acp_sdk",
            title="ACP SDK Available",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message=f"Error checking ACP SDK: {e}",
            metadata={"error": str(e)}
        )


@register_check(
    id="acp_server",
    title="ACP Server Import",
    category=CheckCategory.TOOLS,
    description="Check if ACP server can be imported"
)
def check_acp_server(config=None) -> CheckResult:
    """Check if ACP server can be imported."""
    try:
        from praisonai.acp import ACPServer  # noqa: F401
        
        return CheckResult(
            id="acp_server",
            title="ACP Server Import",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message="ACP server can be imported",
            metadata={"class": "ACPServer"}
        )
    except ImportError as e:
        return CheckResult(
            id="acp_server",
            title="ACP Server Import",
            category=CheckCategory.TOOLS,
            status=CheckStatus.WARN,
            message=f"ACP server import failed: {e}",
            metadata={"error": str(e)}
        )
    except Exception as e:
        return CheckResult(
            id="acp_server",
            title="ACP Server Import",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message=f"Error importing ACP server: {e}",
            metadata={"error": str(e)}
        )


@register_check(
    id="acp_config",
    title="ACP Configuration",
    category=CheckCategory.CONFIG,
    description="Check ACP configuration"
)
def check_acp_config(config=None) -> CheckResult:
    """Check ACP configuration."""
    acp_conf = {
        "approval_mode": os.environ.get("PRAISONAI_APPROVAL_MODE", "manual"),
        "allow_write": os.environ.get("PRAISONAI_ALLOW_WRITE", "false"),
        "allow_shell": os.environ.get("PRAISONAI_ALLOW_SHELL", "false"),
    }
    
    return CheckResult(
        id="acp_config",
        title="ACP Configuration",
        category=CheckCategory.CONFIG,
        status=CheckStatus.PASS,
        message=f"ACP configured with approval_mode={acp_conf['approval_mode']}",
        metadata=acp_conf
    )


@register_check(
    id="acp_runtime",
    title="ACP Runtime Check",
    category=CheckCategory.TOOLS,
    description="Check if ACP runtime can start",
    requires_deep=True
)
def check_acp_runtime(config=None) -> CheckResult:
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
                return ready, error
            finally:
                await runtime.stop()
        
        ready, error = asyncio.run(_check())
        
        if ready:
            return CheckResult(
                id="acp_runtime",
                title="ACP Runtime Check",
                category=CheckCategory.TOOLS,
                status=CheckStatus.PASS,
                message="ACP runtime started successfully",
                metadata={"ready": True}
            )
        else:
            return CheckResult(
                id="acp_runtime",
                title="ACP Runtime Check",
                category=CheckCategory.TOOLS,
                status=CheckStatus.WARN,
                message=f"ACP runtime failed to start: {error}",
                metadata={"ready": False, "error": str(error)}
            )
            
    except Exception as e:
        return CheckResult(
            id="acp_runtime",
            title="ACP Runtime Check",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message=f"ACP runtime check failed: {e}",
            metadata={"error": str(e)}
        )


def register_acp_checks():
    """Register all ACP checks."""
    pass
