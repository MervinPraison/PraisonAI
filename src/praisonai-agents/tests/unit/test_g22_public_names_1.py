"""Private core names used by other PraisonAI packages get public names (G-22, part 1).

The private names stay; the public name is the same object, so other packages
can move to it once a core release ships it.
"""

import importlib

import pytest

NAMES = [('praisonaiagents.tools.schedule_tools', '_get_store'), ('praisonaiagents.plugins.discovery', '_project_plugins_allowed'), ('praisonaiagents.tools.email_tools', '_parse_email_list'), ('praisonaiagents.gateway.protocols', '_is_trusted_hop'), ('praisonaiagents.gateway.config', '_parse_auth_scopes')]


@pytest.mark.parametrize("module,private", NAMES, ids=[p for _, p in NAMES])
def test_public_name_is_the_private_object(module, private):
    mod = importlib.import_module(module)
    assert getattr(mod, private[1:]) is getattr(mod, private)
