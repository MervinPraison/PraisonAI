"""
LSP health checks for PraisonAI Doctor.
"""

import asyncio
import logging
import shutil

from ..models import CheckCategory, CheckResult, CheckStatus
from ..registry import register_check

logger = logging.getLogger(__name__)


@register_check(
    id="lsp_module",
    title="LSP Module Available",
    category=CheckCategory.TOOLS,
    description="Check if LSP module is installed"
)
def check_lsp_module(config=None) -> CheckResult:
    """Check if LSP module is available."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("praisonaiagents.lsp")
        
        if spec is not None:
            return CheckResult(
                id="lsp_module",
                title="LSP Module Available",
                category=CheckCategory.TOOLS,
                status=CheckStatus.PASS,
                message="LSP module is available",
                metadata={"module": "praisonaiagents.lsp"}
            )
        else:
            return CheckResult(
                id="lsp_module",
                title="LSP Module Available",
                category=CheckCategory.TOOLS,
                status=CheckStatus.WARN,
                message="LSP module not found",
                remediation="Install praisonaiagents with LSP support"
            )
    except Exception as e:
        return CheckResult(
            id="lsp_module",
            title="LSP Module Available",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message=f"Error checking LSP module: {e}",
            metadata={"error": str(e)}
        )


@register_check(
    id="lsp_client",
    title="LSP Client Import",
    category=CheckCategory.TOOLS,
    description="Check if LSP client can be imported"
)
def check_lsp_client(config=None) -> CheckResult:
    """Check if LSP client can be imported."""
    try:
        from praisonaiagents.lsp import LSPClient  # noqa: F401
        
        return CheckResult(
            id="lsp_client",
            title="LSP Client Import",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message="LSP client can be imported",
            metadata={"class": "LSPClient"}
        )
    except ImportError as e:
        return CheckResult(
            id="lsp_client",
            title="LSP Client Import",
            category=CheckCategory.TOOLS,
            status=CheckStatus.WARN,
            message=f"LSP client import failed: {e}",
            metadata={"error": str(e)}
        )
    except Exception as e:
        return CheckResult(
            id="lsp_client",
            title="LSP Client Import",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message=f"Error importing LSP client: {e}",
            metadata={"error": str(e)}
        )


@register_check(
    id="lsp_server_python",
    title="Python LSP Server",
    category=CheckCategory.TOOLS,
    description="Check if Python language server is available"
)
def check_lsp_server_python(config=None) -> CheckResult:
    """Check if Python language server is available."""
    servers = [
        ("pyright-langserver", "pyright"),
        ("pylsp", "python-lsp-server"),
        ("pyls", "python-language-server"),
    ]
    
    found = []
    for cmd, package in servers:
        if shutil.which(cmd):
            found.append({"command": cmd, "package": package})
    
    if found:
        return CheckResult(
            id="lsp_server_python",
            title="Python LSP Server",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message=f"Python LSP server available: {found[0]['command']}",
            metadata={"servers": found}
        )
    else:
        return CheckResult(
            id="lsp_server_python",
            title="Python LSP Server",
            category=CheckCategory.TOOLS,
            status=CheckStatus.WARN,
            message="No Python LSP server found",
            remediation="Install with: npm install -g pyright OR pip install python-lsp-server"
        )


@register_check(
    id="lsp_server_typescript",
    title="TypeScript LSP Server",
    category=CheckCategory.TOOLS,
    description="Check if TypeScript language server is available"
)
def check_lsp_server_typescript(config=None) -> CheckResult:
    """Check if TypeScript language server is available."""
    if shutil.which("typescript-language-server"):
        return CheckResult(
            id="lsp_server_typescript",
            title="TypeScript LSP Server",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message="TypeScript LSP server available",
            metadata={"command": "typescript-language-server"}
        )
    elif shutil.which("tsserver"):
        return CheckResult(
            id="lsp_server_typescript",
            title="TypeScript LSP Server",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message="TypeScript server available (tsserver)",
            metadata={"command": "tsserver"}
        )
    else:
        return CheckResult(
            id="lsp_server_typescript",
            title="TypeScript LSP Server",
            category=CheckCategory.TOOLS,
            status=CheckStatus.SKIP,
            message="TypeScript LSP server not found (optional)",
            remediation="Install with: npm install -g typescript-language-server typescript"
        )


@register_check(
    id="lsp_runtime",
    title="LSP Runtime Check",
    category=CheckCategory.TOOLS,
    description="Check if LSP runtime can start",
    requires_deep=True
)
def check_lsp_runtime(config=None) -> CheckResult:
    """Check if LSP runtime can start."""
    try:
        from praisonai.cli.features.interactive_runtime import create_runtime
        
        async def _check():
            runtime = create_runtime(
                workspace=".",
                lsp=True,
                acp=False
            )
            try:
                await runtime.start()
                ready = runtime.lsp_ready
                error = runtime._lsp_state.error
                return ready, error
            finally:
                await runtime.stop()
        
        ready, error = asyncio.run(_check())
        
        if ready:
            return CheckResult(
                id="lsp_runtime",
                title="LSP Runtime Check",
                category=CheckCategory.TOOLS,
                status=CheckStatus.PASS,
                message="LSP runtime started successfully",
                metadata={"ready": True}
            )
        else:
            return CheckResult(
                id="lsp_runtime",
                title="LSP Runtime Check",
                category=CheckCategory.TOOLS,
                status=CheckStatus.WARN,
                message=f"LSP runtime failed to start: {error}",
                metadata={"ready": False, "error": str(error)}
            )
            
    except Exception as e:
        return CheckResult(
            id="lsp_runtime",
            title="LSP Runtime Check",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message=f"LSP runtime check failed: {e}",
            metadata={"error": str(e)}
        )


def register_lsp_checks():
    """Register all LSP checks."""
    pass
