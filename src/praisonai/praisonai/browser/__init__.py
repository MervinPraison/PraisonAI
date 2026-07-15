"""C11 shim: browser implementation moved to ``praisonai_browser``.

Old import paths (``praisonai.browser``, ``praisonai.browser.server``,
``python -m praisonai.browser.server``) keep working and resolve to the
same module objects as ``praisonai_browser.*``.
"""

from praisonai._bootstrap import ensure_praisonai_browser

ensure_praisonai_browser()

from praisonai.cli._shim import alias_package

alias_package("praisonai.browser", "praisonai_browser")
