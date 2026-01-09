"""
Docs Code Execution System for PraisonAI.

Extracts and runs Python code blocks from Mintlify documentation.
Designed for zero performance impact when not invoked (lazy-loaded).

Usage:
    praisonai docs run                    # Run all Python blocks
    praisonai docs run --docs-path /path  # Custom docs path
    praisonai docs list                   # List discovered blocks
    praisonai docs run --dry-run          # Extract only, no execution
"""

# Lazy loading - only import when accessed
_LAZY_IMPORTS = {
    "FenceExtractor": "extractor",
    "CodeBlock": "extractor",
    "RunnableClassifier": "classifier",
    "ClassificationResult": "classifier",
    "WorkspaceWriter": "workspace",
    "SnippetRunner": "runner",
    "SnippetResult": "runner",
    "DocsReportBuilder": "reporter",
    "DocsExecutor": "executor",
    "DocsRunReport": "executor",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_LAZY_IMPORTS.keys())
