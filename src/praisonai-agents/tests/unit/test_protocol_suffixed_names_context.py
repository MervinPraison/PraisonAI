"""G-26: Protocol classes get the ``...Protocol`` name; the old name still works.

Each suffixed name must be the same object as the original at every import
path the original is exported from, so ``isinstance`` checks, subclasses
and type hints written against either name agree. A name that no package
re-exports uses its defining module as the package.
"""

import importlib

import pytest

NAMES = [
    ("praisonaiagents.context.protocols", "praisonaiagents.context", "ContextView"),
    ("praisonaiagents.context.protocols", "praisonaiagents.context", "ContextMutator"),
    ("praisonaiagents.context.protocols", "praisonaiagents.context.protocols", "ContextStore"),
    ("praisonaiagents.context.models", "praisonaiagents.context.models", "TokenEstimator"),
    ("praisonaiagents.context.models", "praisonaiagents.context.models", "ContextOptimizer"),
    ("praisonaiagents.context.fast.compressor", "praisonaiagents.context.fast.compressor", "ContextCompressor"),
    ("praisonaiagents.context.fast.search_backends", "praisonaiagents.context.fast.search_backends", "SearchBackend"),
]


@pytest.mark.parametrize("module,package,old", NAMES, ids=[n[2] for n in NAMES])
def test_suffixed_name_is_the_original_class(module, package, old):
    original = getattr(importlib.import_module(module), old)
    for path in (module, package):
        mod = importlib.import_module(path)
        assert getattr(mod, old) is original
        assert getattr(mod, f"{old}Protocol") is original
        if old in getattr(mod, "__all__", ()):
            assert f"{old}Protocol" in mod.__all__
