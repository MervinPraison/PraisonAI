"""Temporary forward shims for siblings still living in ``praisonai.cli``.

During the incremental migration, some sub-packages under ``praisonai.cli``
have not moved yet (``configuration``, ``utils``, ``session``, ``features``,
etc.). Modules that *have* moved into ``praisonai_code.cli`` still reference
those siblings with relative imports such as ``from ..configuration.paths import``.

To keep those relative imports working without editing the moved files, this
installs a ``sys.meta_path`` finder that transparently redirects
``praisonai_code.cli.<sibling>`` (and any submodule) to the corresponding
``praisonai.cli.<sibling>`` in the main package, preserving module identity.

These shims are temporary and are expected to be removed once the remaining
siblings move to ``praisonai_code`` (migration step C5).
"""

from __future__ import annotations

import importlib
import sys
from importlib.machinery import ModuleSpec

_CODE_PREFIX = "praisonai_code.cli."
_MAIN_PREFIX = "praisonai.cli."

FORWARDED_SIBLINGS = (
    "configuration",
    "utils",
    "session",
    "features",
)


class _RedirectLoader:
    """Loader returning an already-imported module without re-executing it."""

    def __init__(self, target_module):
        self._target = target_module

    def create_module(self, spec):
        return self._target

    def exec_module(self, module):
        return None


class _ForwardFinder:
    """Redirect not-yet-moved ``praisonai_code.cli.<sibling>`` to the main pkg."""

    _praisonai_forward_shim = True

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(_CODE_PREFIX):
            return None
        remainder = fullname[len(_CODE_PREFIX):]
        top = remainder.split(".", 1)[0]
        if top not in FORWARDED_SIBLINGS:
            return None
        mapped = _MAIN_PREFIX + remainder
        module = sys.modules.get(mapped)
        if module is None:
            module = importlib.import_module(mapped)
        sys.modules[fullname] = module
        spec = ModuleSpec(fullname, _RedirectLoader(module))
        spec.submodule_search_locations = getattr(module, "__path__", None)
        return spec


def install() -> None:
    if any(getattr(f, "_praisonai_forward_shim", False) for f in sys.meta_path):
        return
    sys.meta_path.insert(0, _ForwardFinder())
