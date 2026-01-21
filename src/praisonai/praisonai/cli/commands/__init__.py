"""
PraisonAI CLI Commands Module.

This module contains all Typer command groups and subcommands.
Each file represents a command group (e.g., config, traces, session).
"""

# Lazy imports to avoid loading all commands at startup
__all__ = [
    'run_app',
    'config_app',
    'traces_app',
    'env_app',
    'session_app',
    'schedule_app',
    'serve_app',
    'completion_app',
    'version_app',
    'debug_app',
    'lsp_app',
    'diag_app',
    'doctor_app',
    'acp_app',
    'mcp_app',
    'rag_app',
    'test_app',
    'examples_app',
    'replay_app',
]


def __getattr__(name: str):
    """Lazy load command apps."""
    if name == 'run_app':
        from .run import app as run_app
        return run_app
    elif name == 'config_app':
        from .config import app as config_app
        return config_app
    elif name == 'traces_app':
        from .traces import app as traces_app
        return traces_app
    elif name == 'env_app':
        from .environment import app as env_app
        return env_app
    elif name == 'session_app':
        from .session import app as session_app
        return session_app
    elif name == 'schedule_app':
        from .schedule import app as schedule_app
        return schedule_app
    elif name == 'serve_app':
        from .serve import app as serve_app
        return serve_app
    elif name == 'completion_app':
        from .completion import app as completion_app
        return completion_app
    elif name == 'version_app':
        from .version import app as version_app
        return version_app
    elif name == 'debug_app':
        from .debug import app as debug_app
        return debug_app
    elif name == 'lsp_app':
        from .lsp import app as lsp_app
        return lsp_app
    elif name == 'diag_app':
        from .diag import app as diag_app
        return diag_app
    elif name == 'doctor_app':
        from .doctor import app as doctor_app
        return doctor_app
    elif name == 'acp_app':
        from .acp import app as acp_app
        return acp_app
    elif name == 'mcp_app':
        from .mcp import app as mcp_app
        return mcp_app
    elif name == 'rag_app':
        from .rag import app as rag_app
        return rag_app
    elif name == 'test_app':
        from .test import app as test_app
        return test_app
    elif name == 'examples_app':
        from .examples import app as examples_app
        return examples_app
    elif name == 'replay_app':
        from .replay import app as replay_app
        return replay_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
