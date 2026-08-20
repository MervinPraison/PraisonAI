"""Compute providers live in praisonai-sandbox, and reaching one is cheap.

They used to sit in the praisonai wrapper, so `tools_run_on="e2b"` required a
distribution with 20 hard dependencies and 8 sibling packages -- a browser
package and a Telegram bot, to run a command in a sandbox. The identical
capability through `run_in="e2b"` needed only praisonai-sandbox[e2b].

These tests pin the property that move bought, and the compatibility that
makes it safe.
"""

import importlib
import sys

import pytest


class _Blocked:
    """Makes the wrapper genuinely unimportable, as it is for a user who
    installed only praisonai-sandbox."""

    def find_spec(self, name, path=None, target=None):
        if name == "praisonai" or name.startswith("praisonai."):
            raise ImportError(f"{name} is not installed")
        return None


def test_a_provider_resolves_without_the_wrapper():
    """The point of the move. If this fails, the providers have drifted back
    behind a dependency users should not need."""
    from praisonaiagents.managed._compute_bridge import _PROVIDERS

    for place, (module, _attr) in _PROVIDERS.items():
        assert not module.startswith("praisonai."), (
            f"{place} resolves through the wrapper ({module}); it should come "
            f"from praisonai_sandbox.compute"
        )


def test_providers_import_with_the_wrapper_absent():
    blocker = _Blocked()
    sys.meta_path.insert(0, blocker)
    dropped = [m for m in list(sys.modules) if m == "praisonai" or m.startswith("praisonai.")]
    saved = {m: sys.modules.pop(m) for m in dropped}
    try:
        with pytest.raises(ImportError):
            importlib.import_module("praisonai")

        from praisonaiagents.managed._compute_bridge import resolve_compute

        for place in ("docker", "e2b", "modal", "local"):
            assert resolve_compute(place) is not None, f"{place} needs the wrapper"
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(saved)


@pytest.mark.parametrize("old_path,name", [
    ("praisonai.integrations.compute.docker", "DockerCompute"),
    ("praisonai.integrations.compute.e2b", "E2BCompute"),
    ("praisonai.integrations.compute.daytona", "DaytonaCompute"),
    ("praisonai.integrations.compute.modal_compute", "ModalCompute"),
])
def test_the_old_import_paths_still_work(old_path, name):
    """Names stay stable across the move; only the implementation relocated."""
    pytest.importorskip("praisonai")
    module = importlib.import_module(old_path)
    assert hasattr(module, name)


def test_the_shim_is_the_same_module_not_a_copy():
    """A re-export shim looks equivalent until someone monkeypatches a
    module-level name through the old path -- the patch lands on the shim and
    the real module never sees it. Aliasing keeps one shared module object."""
    pytest.importorskip("praisonai")
    old = importlib.import_module("praisonai.integrations.compute.docker")
    new = importlib.import_module("praisonai_sandbox.compute.docker")
    assert old is new, "the shim is a copy; patches through the old path would be lost"
