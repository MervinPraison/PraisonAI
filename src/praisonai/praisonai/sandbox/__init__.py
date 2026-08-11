"""C13 shim: sandbox backends moved to ``praisonai_sandbox``.

Old import paths (``praisonai.sandbox``, ``praisonai.sandbox.docker``) keep working
and resolve to the same module objects as ``praisonai_sandbox.*``.
"""

from praisonai._bootstrap import ensure_praisonai_sandbox

ensure_praisonai_sandbox()

from praisonai.cli._shim import alias_package

alias_package("praisonai.sandbox", "praisonai_sandbox")
