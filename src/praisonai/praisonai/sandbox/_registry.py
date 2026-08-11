"""C13 shim: ``praisonai.sandbox._registry`` → ``praisonai_sandbox._registry``."""

from __future__ import annotations

import sys

from praisonai._bootstrap import ensure_praisonai_sandbox

ensure_praisonai_sandbox()

import praisonai_sandbox._registry as _reg

sys.modules[__name__] = _reg
