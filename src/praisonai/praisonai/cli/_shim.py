"""Backward-compatibility shim helpers for the praisonai-code migration.

During the incremental extraction of the agentic terminal CLI into the
``praisonai_code`` package, several sub-packages have moved out of
``praisonai.cli``. To preserve every existing public import path
(``from praisonai.cli.output import ...``, ``import praisonai.cli.state.identifiers``,
etc.) *and* keep module-level globals mutable (some test fixtures reset
singletons on the module object), the old locations forward submodule imports
to the moved package.

Two guarantees matter:

1. **Module identity** — importing a submodule under the old name
   (``praisonai.cli.output.console``) must return the *same* module object as
   the moved one (``praisonai_code.cli.output.console``). Otherwise the file is
   executed twice, producing duplicate class/enum objects that break
   ``isinstance`` / equality checks across the old and new import paths.

2. **Laziness** — submodules are only imported on demand (the CLI relies on
   lazy imports for start-up performance), so nothing is eagerly imported here.

The shim package at the old path keeps its *own* ``__path__`` (the now nearly
empty old directory). Because that directory no longer contains the moved
submodule files, the default path-based finder cannot load them, so resolution
falls through to :class:`_AliasFinder`, which returns the identical module from
the moved package.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from importlib.machinery import ModuleSpec


class _RedirectLoader:
    """Loader that returns an already-imported module without re-executing it."""

    def __init__(self, target_module):
        self._target = target_module

    def create_module(self, spec):
        return self._target

    def exec_module(self, module):
        # The target module is already fully initialised; do nothing.
        return None


class _AliasFinder:
    """Redirect ``old_name`` submodules to the moved ``new_name`` package."""

    def __init__(self, old_name: str, new_name: str):
        self.old_name = old_name
        self.new_name = new_name
        self.old_prefix = old_name + "."
        self._praisonai_shim_for = old_name

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.old_prefix):
            return None
        mapped = self.new_name + fullname[len(self.old_name):]
        module = sys.modules.get(mapped)
        if module is None:
            module = importlib.import_module(mapped)
        sys.modules[fullname] = module
        spec = ModuleSpec(fullname, _RedirectLoader(module))
        spec.submodule_search_locations = getattr(module, "__path__", None)
        return spec


def _register_submodules(old_name: str, new_name: str, module) -> None:
    """Eagerly import the moved subtree and alias each submodule.

    Registering each moved submodule under its old dotted name in
    ``sys.modules`` guarantees that a later ``import old_name.sub`` finds the
    identical object immediately, never re-executing the file (which would
    create duplicate class/enum objects). Modules that fail to import eagerly
    (e.g. optional heavy dependencies not installed) are skipped and resolved
    lazily by :class:`_AliasFinder` on first successful use.
    """
    new_prefix = new_name + "."
    old_prefix = old_name + "."

    # Alias whatever is already imported first (e.g. the package __init__).
    for mod_name, mod in list(sys.modules.items()):
        if mod_name == new_name or mod_name.startswith(new_prefix):
            old_equiv = old_name + mod_name[len(new_name):]
            sys.modules.setdefault(old_equiv, mod)

    search_path = getattr(module, "__path__", None)
    if not search_path:
        return

    for info in pkgutil.walk_packages(search_path, prefix=new_prefix):
        if info.name in sys.modules:
            sub = sys.modules[info.name]
        else:
            try:
                sub = importlib.import_module(info.name)
            except Exception:
                continue
        old_equiv = old_name + info.name[len(new_name):]
        sys.modules.setdefault(old_equiv, sub)


def alias_package(old_name: str, new_name: str) -> object:
    """Forward ``old_name`` attribute and submodule access to ``new_name``.

    Installs a fallback finder so that ``old_name.<sub>`` resolves to the
    identical ``new_name.<sub>`` module object, and delegates attribute lookups
    on the (still-present) shim package to the moved package so that
    ``from old_name import Symbol`` keeps working — lazily, without eagerly
    importing heavy submodules.

    The shim package module itself is *not* replaced in ``sys.modules`` — it
    retains its own ``__path__`` pointing at the old directory, which no longer
    contains the moved submodule files. This guarantees the fallback finder
    (rather than a duplicate on-disk load) resolves each submodule, preserving
    module identity.
    """
    from praisonai._bootstrap import ensure_praisonai_code

    ensure_praisonai_code()
    module = importlib.import_module(new_name)

    if not any(
        getattr(f, "_praisonai_shim_for", None) == old_name for f in sys.meta_path
    ):
        sys.meta_path.insert(0, _AliasFinder(old_name, new_name))

    _register_submodules(old_name, new_name, module)

    shim = sys.modules.get(old_name)
    if shim is not None and shim is not module:
        def __getattr__(name, _module=module):
            return getattr(_module, name)

        shim.__getattr__ = __getattr__
        if hasattr(module, "__all__"):
            shim.__all__ = list(module.__all__)

    return module
