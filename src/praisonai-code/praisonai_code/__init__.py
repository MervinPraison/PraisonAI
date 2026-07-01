"""praisonai-code — agentic terminal CLI for PraisonAI.

This package hosts the terminal-native agent product (``run``, ``chat``,
``code``, warm runtime, CLI backends) extracted from the ``praisonai``
wrapper. It depends on ``praisonaiagents`` only — never on ``praisonai`` —
to avoid a PyPI dependency cycle.

Migration in progress: ``runtime/`` and ``cli_backends/`` have moved here
(step C1). Subsequent steps (C2–C6) migrate the remaining terminal-agent
modules, with PEP 562 shims left behind at the old ``praisonai.*`` paths
for backward compatibility.
"""

__version__ = "0.0.1"

__all__ = ["__version__"]
