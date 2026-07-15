"""C11 shim: implementation moved to ``praisonai_browser.cli.commands.browser``."""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_browser

ensure_praisonai_browser()

import praisonai_browser.cli.commands.browser as _impl

_sys.modules[__name__] = _impl
