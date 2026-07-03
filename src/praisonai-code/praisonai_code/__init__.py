"""praisonai-code — agentic terminal CLI for PraisonAI.

This package hosts the terminal-native agent product (``run``, ``chat``,
``code``, warm runtime, CLI backends) extracted from the ``praisonai``
wrapper. It depends on ``praisonaiagents`` only — never on ``praisonai`` —
to avoid a PyPI dependency cycle.

Migration in progress: ``runtime/`` and ``cli_backends/`` have moved here
(step C1), and the ``interactive``/``execution``/``ui``/``output``/``state``
CLI sub-packages have moved here (step C2). Subsequent steps (C3–C6) migrate
the remaining terminal-agent modules, with PEP 562 shims left behind at the
old ``praisonai.*`` paths for backward compatibility.
"""

__version__ = "0.0.14"

__all__ = ["__version__"]
