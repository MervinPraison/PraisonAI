"""praisonai_code.cli — agentic terminal CLI.

During the C0–C6 migration only the agentic ``commands`` sub-package has
been moved here. Sibling packages the commands depend on
(``output``, ``state``, ``features``, ``configuration``, ``utils`` …)
still live in ``praisonai.cli`` and are referenced via absolute imports
until their own migration step (C2/C4/C5).
"""
