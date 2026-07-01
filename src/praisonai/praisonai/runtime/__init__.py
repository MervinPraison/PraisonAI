"""Backward-compatible shim for ``praisonai.runtime``.

The warm local runtime moved to :mod:`praisonai_code.runtime` (parent tracking
issue, step C1). This shim re-exports the public surface and aliases the
submodules so existing imports keep working:

    from praisonai.runtime import RuntimeDescriptor, RuntimeClient
    from praisonai.runtime.descriptor import get_runtime_descriptor
    python -m praisonai.runtime
"""

import sys as _sys

import praisonai_code.runtime as _runtime

# Alias submodules so ``praisonai.runtime.<sub>`` resolves to the moved module.
# These submodules always exist in ``praisonai_code``; let any real import
# error surface here (with its original traceback) instead of being swallowed
# and re-raised later as a confusing missing-submodule error on the old path.
for _name in ("descriptor", "client", "server", "__main__"):
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
