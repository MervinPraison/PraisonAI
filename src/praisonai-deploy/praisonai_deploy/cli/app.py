"""Typer CLI for standalone ``praisonai-deploy``.

The deploy command group (``run``, ``doctor``, ``init``, ``validate``, ``plan``,
``status``, ``destroy``, plus cloud shortcuts) is mounted as ``praisonai deploy``
via ``_DEPLOY_RESIDENT_COMMANDS`` routing in ``praisonai_code.cli.app``.
"""

from __future__ import annotations

from praisonai_deploy.cli.commands.deploy import app

__all__ = ["app"]
