"""
PraisonAI Code CLI Commands Module.

Agentic Typer command groups moved from ``praisonai.cli.commands`` as part
of the praisonai-code extraction (issue #2516 / parent #2512). Bot-channel
commands remain in ``praisonai.cli.commands``.

Lazy imports keep startup fast; each attribute maps to the ``app`` object of
the corresponding command module.
"""

__all__ = [
    'run_app',
    'config_app',
    'traces_app',
    'env_app',
    'session_app',
    'usage_app',
    'schedule_app',
    'serve_app',
    'completion_app',
    'version_app',
    'debug_app',
    'lsp_app',
    'diag_app',
    'doctor_app',
    'setup_app',
    'acp_app',
    'mcp_app',
    'rag_app',
    'test_app',
    'examples_app',
    'replay_app',
    'github_app',
    'langextract_app',
    'agent_app',
    'command_app',
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
    elif name == 'usage_app':
        from .usage import app as usage_app
        return usage_app
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
    elif name == 'setup_app':
        from .setup import app as setup_app
        return setup_app
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
    elif name == 'github_app':
        from .github import app as github_app
        return github_app
    elif name == 'langextract_app':
        from .langextract import app as langextract_app
        return langextract_app
    elif name == 'agent_app':
        from .agent import app as agent_app
        return agent_app
    elif name == 'command_app':
        from .command import app as command_app
        return command_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
