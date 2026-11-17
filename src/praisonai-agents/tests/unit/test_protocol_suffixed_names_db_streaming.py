"""G-26: Protocol classes get the ``...Protocol`` name; the old name still works.

Each suffixed name must be the same object as the original at every import
path the original is exported from, so ``isinstance`` checks, subclasses
and type hints written against either name agree.
"""

import importlib

import pytest

NAMES = [
    ("praisonaiagents.db.protocol", "praisonaiagents.db", "DbAdapter"),
    ("praisonaiagents.db.protocol", "praisonaiagents.db", "AsyncDbAdapter"),
    ("praisonaiagents.streaming.events", "praisonaiagents.streaming", "StreamCallback"),
    ("praisonaiagents.streaming.events", "praisonaiagents.streaming", "AsyncStreamCallback"),
]


@pytest.mark.parametrize("module,package,old", NAMES, ids=[n[2] for n in NAMES])
def test_suffixed_name_is_the_original_class(module, package, old):
    original = getattr(importlib.import_module(module), old)
    for path in (module, package):
        mod = importlib.import_module(path)
        assert getattr(mod, old) is original
        assert getattr(mod, f"{old}Protocol") is original
    assert f"{old}Protocol" in importlib.import_module(package).__all__
