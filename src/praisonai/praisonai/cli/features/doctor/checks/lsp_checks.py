"""
LSP health checks for PraisonAI Doctor.
"""

import asyncio
import logging

from ..models import CheckCategory, CheckResult, CheckStatus
from ..registry import register_check

logger = logging.getLogger(__name__)


@register_check(
    id="lsp_module",
    title="LSP Module Available",
    category=CheckCategory.TOOLS,
    description="Check if LSP module is installed"
)
def check_lsp_module() -> CheckResult:
    """Check if LSP module is available."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("praisonaiagents.lsp")
        
        if spec is not None:
            return CheckResult(
                status=CheckStatus.PASS,
                message="LSP module is available",
                details={"module": "praisonaiagents.lsp"}
            )
        else:
            return CheckResult(
                status=CheckStatus.WARN,
                message="LSP module not found",
                details={"hint": "Install praisonaiagents with LSP support"}
            )
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"Error checking LSP module: {e}",
            details={"error": str(e)}
        )


@register_check(
    id="lsp_client",
    title="LSP Client Import",
    category=CheckCategory.TOOLS,
    description="Check if LSP client can be imported"
)
def check_lsp_client() -> CheckResult:
    """Check if LSP client can be imported."""
    try:
        from praisonaiagents.lsp import LSPClient  # noqa: F401
        
        return CheckResult(
            status=CheckStatus.PASS,
            message="LSP client can be imported",
            details={"class": "LSPClient"}
        )
    except ImportError as e:
        return CheckResult(
            status=CheckStatus.WARN,
            message=f"LSP client import failed: {e}",
            details={"error": str(e)}
        )
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"Error importing LSP client: {e}",
            details={"error": str(e)}
        )


@register_check(
    id="lsp_server_python",
    title="Python LSP Server",
    category=CheckCategory.TOOLS,
    description="Check if Python language server is available"
)
def check_lsp_server_python() -> CheckResult:
    """Check if Python language server is available."""
    import shutil
    
    # Check for common Python language servers
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
            status=CheckStatus.PASS,
            message=f"Python LSP server available: {found[0]['command']}",
            details={"servers": found}
        )
    else:
        return CheckResult(
            status=CheckStatus.WARN,
            message="No Python LSP server found",
            details={
                "hint": "Install with: npm install -g pyright OR pip install python-lsp-server",
                "checked": [s[0] for s in servers]
            }
        )


@register_check(
    id="lsp_server_typescript",
    title="TypeScript LSP Server",
    category=CheckCategory.TOOLS,
    description="Check if TypeScript language server is available"
)
def check_lsp_server_typescript() -> CheckResult:
    """Check if TypeScript language server is available."""
    import shutil
    
    # Check for TypeScript language server
    if shutil.which("typescript-language-server"):
        return CheckResult(
            status=CheckStatus.PASS,
            message="TypeScript LSP server available",
            details={"command": "typescript-language-server"}
        )
    elif shutil.which("tsserver"):
        return CheckResult(
            status=CheckStatus.PASS,
            message="TypeScript server available (tsserver)",
            details={"command": "tsserver"}
        )
    else:
        return CheckResult(
            status=CheckStatus.INFO,
            message="TypeScript LSP server not found (optional)",
            details={
                "hint": "Install with: npm install -g typescript-language-server typescript"
            }
        )


@register_check(
    id="lsp_runtime",
    title="LSP Runtime Check",
    category=CheckCategory.TOOLS,
    description="Check if LSP runtime can start",
    requires_deep=True
)
def check_lsp_runtime() -> CheckResult:
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
                status=CheckStatus.PASS,
                message="LSP runtime started successfully",
                details={"ready": True}
            )
        else:
            return CheckResult(
                status=CheckStatus.WARN,
                message=f"LSP runtime failed to start: {error}",
                details={"ready": False, "error": error}
            )
            
    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAIL,
            message=f"LSP runtime check failed: {e}",
            details={"error": str(e)}
        )


def register_lsp_checks():
    """Register all LSP checks."""
    pass
