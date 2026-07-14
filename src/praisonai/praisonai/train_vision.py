"""C10 shim: implementation moved to ``praisonai_train.train_vision``."""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_train

ensure_praisonai_train()

import praisonai_train.train_vision as _impl

_sys.modules[__name__] = _impl

if __name__ == "__main__":
    _impl.main()
