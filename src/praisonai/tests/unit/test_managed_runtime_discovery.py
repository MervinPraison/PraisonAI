"""The first runtime lookup must discover compute-backed placements."""


def test_first_all_names_lookup_registers_compute_and_keeps_aliases(monkeypatch):
    from praisonai.integrations.backend_registry import ManagedBackendRegistry
    from praisonaiagents.managed import _compute_bridge

    monkeypatch.setattr(_compute_bridge, "available_providers", lambda: ["docker"])
    registry = ManagedBackendRegistry()
    registry.register("custom", object, aliases=["custom-alias"])

    assert "docker" in registry.list_all_names()
    assert "custom-alias" in registry.list_all_names()


def test_first_agent_placement_accepts_discovered_runtime(monkeypatch):
    from praisonai.integrations import backend_registry
    from praisonaiagents import Agent
    from praisonaiagents.managed import _compute_bridge

    monkeypatch.setattr(_compute_bridge, "available_providers", lambda: ["docker"])
    registry = backend_registry.ManagedBackendRegistry()
    monkeypatch.setattr(backend_registry, "get_backend_registry", lambda: registry)

    agent = Agent(name="test", instructions="test", run_on="docker")
    assert agent.backend.provider_name == "docker"
