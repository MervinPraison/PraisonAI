"""Backward-compatible shim for ``praisonai.cli_backends``.

The CLI backend implementations moved to :mod:`praisonai_code.cli_backends`
(parent tracking issue, step C1). This shim re-exports the public surface and
aliases the submodules so existing imports keep working:

    from praisonai.cli_backends import resolve_cli_backend_config
    from praisonai.cli_backends import ClaudeCodeBackend
    from praisonai.cli_backends.registry import resolve_cli_backend
"""

import sys as _sys

import praisonai_code.cli_backends as _cli_backends

# Alias submodules so ``praisonai.cli_backends.<sub>`` resolves to the moved
# module. These submodules always exist in ``praisonai_code``; let any real
# import error surface here (with its original traceback) instead of being
# swallowed and re-raised later as a confusing missing-submodule error on the
# old path.
for _name in ("registry", "claude"):
    _mod = __import__(f"praisonai_code.cli_backends.{_name}", fromlist=[_name])
    _sys.modules[f"{__name__}.{_name}"] = _mod

del _sys, _name


def __getattr__(name: str):
    return getattr(_cli_backends, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_cli_backends)))


__all__ = getattr(_cli_backends, "__all__", [])
