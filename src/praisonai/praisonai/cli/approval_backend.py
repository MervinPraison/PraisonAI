"""Backward-compatibility shim: ``praisonai.cli.approval_backend`` moved to
``praisonai_code.cli.approval_backend``.
"""

import sys as _sys

import praisonai_code.cli.approval_backend as _impl

_sys.modules[__name__] = _impl
