"""Backward-compatibility shim: ``praisonai.cli.output`` moved to
``praisonai_code.cli.output``.
"""

from praisonai.cli._shim import alias_package as _alias_package

_alias_package(__name__, "praisonai_code.cli.output")
