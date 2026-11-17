"""T-01: clearing warning registries must not trigger lazy imports.

A lazy module (transformers registers ~190 of them) answers unknown
attributes through a module-level __getattr__ that imports the real module.
The autouse fixture used to call getattr(module, "__warningregistry__") on
every entry in sys.modules, so one failed optional import made every later
test on that worker error at setup (500 errors in a full run).
"""
import sys
import types

from tests.conftest import clear_warning_registries


def test_lazy_module_getattr_is_never_called():
    calls = []
    lazy = types.ModuleType("_t01_lazy")
    lazy.__getattr__ = lambda name: calls.append(name) or (_ for _ in ()).throw(ImportError("boom"))
    plain = types.ModuleType("_t01_plain")
    plain.__warningregistry__ = {("msg", Warning, 1): True}
    sys.modules["_t01_lazy"], sys.modules["_t01_plain"] = lazy, plain
    try:
        clear_warning_registries()
    finally:
        del sys.modules["_t01_lazy"], sys.modules["_t01_plain"]
    assert calls == []
    assert plain.__warningregistry__ == {}


def test_non_module_entries_are_skipped():
    sys.modules["_t01_none"] = None  # a blocked import is stored as None
    try:
        clear_warning_registries()
    finally:
        del sys.modules["_t01_none"]
