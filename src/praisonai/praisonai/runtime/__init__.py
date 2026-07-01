"""Backward-compatible shim for ``praisonai.runtime``.

The warm local runtime moved to :mod:`praisonai_code.runtime` (parent tracking
issue, step C1). This shim re-exports the public surface and aliases the
submodules so existing imports keep working:

    from praisonai.runtime import RuntimeDescriptor, RuntimeClient
    from praisonai.runtime.descriptor import get_runtime_descriptor
    python -m praisonai.runtime
"""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code.runtime as _runtime

# Alias submodules so ``praisonai.runtime.<sub>`` resolves to the moved module.
# These submodules always exist in ``praisonai_code``; let any real import
# error surface here (with its original traceback) instead of being swallowed
# and re-raised later as a confusing missing-submodule error on the old path.
#
# ``__main__`` is deliberately excluded: pre-inserting it into ``sys.modules``
# makes runpy see the old-path ``__main__`` as already loaded under a foreign
# loader, breaking ``python -m praisonai.runtime`` (RuntimeWarning + ImportError).
# The physical delegating shim ``praisonai/runtime/__main__.py`` handles that
# path instead.
for _name in ("descriptor", "client", "server"):
    _mod = __import__(f"praisonai_code.runtime.{_name}", fromlist=[_name])
    _sys.modules[f"{__name__}.{_name}"] = _mod
    # Bind on the package object too so ``import praisonai.runtime.<sub>``
    # followed by attribute access works (sys.modules aliasing alone does not
    # set the parent-package attribute when pre-inserted).
    globals()[_name] = _mod

del _sys, _name, _mod


def __getattr__(name: str):
    return getattr(_runtime, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_runtime)))


__all__ = getattr(_runtime, "__all__", [])
