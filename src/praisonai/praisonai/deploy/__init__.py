"""C14 shim: deploy module moved to ``praisonai_deploy``.

Old import paths (``praisonai.deploy``, ``praisonai.deploy.models``) keep working
and resolve to the same module objects as ``praisonai_deploy.*``.
"""

from praisonai._bootstrap import ensure_praisonai_deploy

ensure_praisonai_deploy()

from praisonai.cli._shim import alias_package

alias_package("praisonai.deploy", "praisonai_deploy")
