"""C14 shim: implementation moved to ``praisonai_deploy.cli.commands.deploy``."""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_deploy

ensure_praisonai_deploy()

import praisonai_deploy.cli.commands.deploy as _impl

_sys.modules[__name__] = _impl
