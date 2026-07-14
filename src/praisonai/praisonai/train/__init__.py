"""C10 shim: training implementation moved to ``praisonai_train.train``.

Old import paths (``praisonai.train.agents``, ``praisonai.train.llm.trainer``,
``python -m praisonai.train.llm.trainer``) keep working and resolve to the
same module objects as ``praisonai_train.train.*``.
"""

from praisonai._bootstrap import ensure_praisonai_train

ensure_praisonai_train()

from praisonai.cli._shim import alias_package

alias_package("praisonai.train", "praisonai_train.train")
