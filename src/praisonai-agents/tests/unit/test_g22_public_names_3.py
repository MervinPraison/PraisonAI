"""Private core names used by other PraisonAI packages get public names (G-22, part 3).

The private names stay; the public name is the same object, so other packages
can move to it once a core release ships it.
"""

import importlib

import pytest

NAMES = [('praisonaiagents.workflows.diagram', '_flow_graph')]


@pytest.mark.parametrize("module,private", NAMES, ids=[p for _, p in NAMES])
def test_public_name_is_the_private_object(module, private):
    mod = importlib.import_module(module)
    assert getattr(mod, private[1:]) is getattr(mod, private)
