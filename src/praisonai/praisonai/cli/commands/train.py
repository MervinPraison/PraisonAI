"""C10 shim: implementation moved to ``praisonai_train.cli.commands.train``."""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_train

ensure_praisonai_train()

import praisonai_train.cli.commands.train as _impl

_sys.modules[__name__] = _impl
