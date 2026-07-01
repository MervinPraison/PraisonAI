<<<<<<< claude/issue-2517-20260701-0835
"""praisonai_code.cli — terminal agentic CLI package.

During the incremental C0–C6 migration this package receives the agentic
sub-trees (``features/``, ``commands/``, ``interactive/`` …). Public paths under
``praisonai.cli.*`` remain valid through shims in the main ``praisonai`` package.
"""
=======
"""praisonai_code.cli: terminal agent CLI package.

Sub-packages are moved here incrementally (see parent migration issue). During
the migration, old import paths under ``praisonai.cli`` remain valid through
shims in the main package, and not-yet-moved siblings (``configuration``,
``utils``, ``session``, ``features``) are forwarded back to ``praisonai.cli``
via a temporary meta-path shim.
"""

from ._forward_shim import install as _install_forward_shim

_install_forward_shim()
>>>>>>> main
