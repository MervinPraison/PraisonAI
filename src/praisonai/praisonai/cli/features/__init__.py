"""
CLI Features Module for PraisonAI (compatibility shim).

The agentic feature modules were extracted to ``praisonai_code.cli.features``
as part of the incremental C0–C6 migration (issue #2512). This package now acts
as a **compatibility shim**:

- Five bot-channel features remain here as real modules:
  ``gateway``, ``bots_cli``, ``onboard``, ``approval``, ``serve``.
- Every other feature submodule (``mcp``, ``workflow``, ``doctor``, ``tui`` …)
  is resolved from ``praisonai_code.cli.features`` by extending ``__path__`` to
  include that package's directory.
- Attribute access (lazy handler loaders such as ``MCPHandler``) is delegated to
  ``praisonai_code.cli.features``.

This preserves every public import such as
``from praisonai.cli.features.mcp import MCPHandler`` and
``from praisonai.cli.features import MCPHandler`` without touching call sites.
"""

import os as _os

# Extend the package search path so that feature submodules living in
# ``praisonai_code.cli.features`` are importable under the historical
# ``praisonai.cli.features`` namespace. The local directory stays first, so the
# five bot-channel modules that remain here take precedence.
try:  # pragma: no cover - defensive
    import praisonai_code.cli.features as _code_features

    for _code_dir in getattr(_code_features, "__path__", []):
        if _code_dir not in __path__:
            __path__.append(_code_dir)
    del _code_dir
except Exception:  # pragma: no cover - code package optional at import time
    _code_features = None


# Handler names re-exported for ``from praisonai.cli.features import X`` access.
__all__ = [
    'GuardrailHandler',
    'MetricsHandler',
    'ImageHandler',
    'TelemetryHandler',
    'MCPHandler',
    'FastContextHandler',
    'KnowledgeHandler',
    'SessionHandler',
    'ToolsHandler',
    'HandoffHandler',
    'AutoMemoryHandler',
    'TodoHandler',
    'RouterHandler',
    'FlowDisplayHandler',
    'WorkflowHandler',
    'N8nHandler',
    'ExternalAgentsHandler',
    'SlashCommandHandler',
    'AutonomyModeHandler',
    'CostTrackerHandler',
    'RepoMapHandler',
    'InteractiveTUIHandler',
    'GitIntegrationHandler',
    'SandboxExecutorHandler',
    'MessageQueueHandler',
    'AtMentionCompleter',
    'CombinedCompleter',
    'FileSearchService',
    'EvalHandler',
    'CompareHandler',
    'SkillsHandler',
    'HooksHandler',
    'CheckpointsHandler',
    'BackgroundHandler',
    'ThinkingHandler',
    'CompactionHandler',
    'OutputStyleHandler',
    'OllamaHandler',
    'CapabilitiesHandler',
    'PerformanceHandler',
    'BenchmarkHandler',
    'LiteHandler',
    'create_agent_centric_tools',
    'InteractiveRuntime',
    'RuntimeConfig',
    'CodeIntelligenceRouter',
    'ActionOrchestrator',
    'get_interactive_tools',
    'resolve_tool_groups',
    'ToolConfig',
    'TOOL_GROUPS',
]


def __getattr__(name):
    """Delegate handler/attribute access to ``praisonai_code.cli.features``."""
    if _code_features is not None:
        try:
            return getattr(_code_features, name)
        except AttributeError:
            pass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    base = set(globals().keys()) | set(__all__)
    if _code_features is not None:
        base |= set(dir(_code_features))
    return sorted(base)


del _os
