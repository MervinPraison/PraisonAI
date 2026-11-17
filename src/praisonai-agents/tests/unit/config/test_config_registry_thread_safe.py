"""ConfigRegistry reads must not break while entries are registered (G-23 step 3).

Two threads registering while two read get_unknown_env_vars() raised
"dictionary changed size during iteration" within a second on main. The test
makes that interleaving deterministic: an entry whose env_var lookup registers
another entry mid-iteration.
"""

import pytest

from praisonaiagents.config.resolver import ConfigRegistry


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(ConfigRegistry, "_entries", dict(ConfigRegistry._entries))
    monkeypatch.setattr(ConfigRegistry, "_aliases", dict(ConfigRegistry._aliases))
    return ConfigRegistry


class _RegistersWhileRead:
    scope = None
    aliases = []

    def __init__(self, registry):
        self._registry, self._n = registry, 0

    @property
    def env_var(self):
        self._n += 1
        self._registry.register(f"g23.during.read.{self._n}", env_var=f"PRAISONAI_G23_{self._n}")
        return "PRAISONAI_G23_READER"


def test_unknown_env_vars_survives_a_registration_mid_read(registry):
    registry._entries["g23.reader"] = _RegistersWhileRead(registry)
    registry.get_unknown_env_vars()  # raised RuntimeError before
    assert "g23.during.read.1" in registry._entries


def test_register_and_lookup_still_work(registry):
    registry.register("g23.key", env_var="PRAISONAI_G23_KEY", aliases=["g23.alias"])
    assert registry.get_entry("g23.alias").key == "g23.key"
    assert any(e.key == "g23.key" for e in registry.list_entries())
