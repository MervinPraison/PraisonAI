"""
Suite Runner - Unified execution engine for examples and docs.

Provides shared infrastructure for running code suites with:
- Subprocess execution with streaming and timeouts
- Report generation (JSON, Markdown, CSV)
- Deterministic ordering and logging

All imports are lazy-loaded for zero performance impact.
"""

from __future__ import annotations

__all__ = [
    # Dataclasses
    "RunItem",
    "RunResult", 
    "RunReport",
    # Runner
    "ScriptRunner",
    # Reporter
    "SuiteReporter",
    # Discovery
    "FileDiscovery",
    # Sources
    "ExamplesSource",
    "DocsSource",
    "BatchSource",
    "CLIDocsSource",
    # Executor
    "SuiteExecutor",
]


def __getattr__(name: str):
    """Lazy import for zero startup cost."""
    if name in ("RunItem", "RunResult", "RunReport"):
        from .models import RunItem, RunResult, RunReport
        return {"RunItem": RunItem, "RunResult": RunResult, "RunReport": RunReport}[name]
    
    if name == "ScriptRunner":
        from .runner import ScriptRunner
        return ScriptRunner
    
    if name == "SuiteReporter":
        from .reporter import SuiteReporter
        return SuiteReporter
    
    if name == "FileDiscovery":
        from .discovery import FileDiscovery
        return FileDiscovery
    
    if name == "ExamplesSource":
        from .examples_source import ExamplesSource
        return ExamplesSource
    
    if name == "DocsSource":
        from .docs_source import DocsSource
        return DocsSource
    
    if name == "BatchSource":
        from .batch_source import BatchSource
        return BatchSource
    
    if name == "CLIDocsSource":
        from .cli_docs_source import CLIDocsSource
        return CLIDocsSource
    
    if name == "SuiteExecutor":
        from .executor import SuiteExecutor
        return SuiteExecutor
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
