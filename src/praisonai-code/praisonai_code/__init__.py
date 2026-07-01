"""praisonai-code — agentic terminal CLI for PraisonAI.

This package hosts the terminal-native agent product (``run``, ``chat``,
``code``, warm runtime, CLI backends) extracted from the ``praisonai``
wrapper. It depends on ``praisonaiagents`` only — never on ``praisonai`` —
to avoid a PyPI dependency cycle.

C0 scaffold: no runtime code has moved here yet. Subsequent steps
(C1–C5) migrate ``runtime/``, ``cli_backends/`` and ``cli/`` into this
package with PEP 562 shims left behind at the old ``praisonai.*`` paths.
"""

__version__ = "0.0.1"

__all__ = ["__version__"]
