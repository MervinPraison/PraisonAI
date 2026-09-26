"""Regression tests for issue #5321.

Constructing ``AgentsGenerator`` directly (the path taken by every non-Python
launch surface: ``praisonai <file.yaml>``, ``praisonai serve``, ``praisonai
eval``) must wire the wrapper's default retrievers/readers/rerankers into the
core-SDK registries, exactly like ``praisonai.run()`` / ``arun()`` do. Before
the fix the wiring lived only in the Python entry point, so YAML
``retriever: fusion`` silently no-op'd on the CLI.
"""

import pytest


def test_agents_generator_construction_wires_default_adapters():
    """AgentsGenerator.__init__ registers the default adapters (fusion, etc.)."""
    import praisonai.adapters as adapters
    from praisonai.agents_generator import AgentsGenerator
    from praisonaiagents.knowledge.retrieval import get_retriever_registry

    generator = AgentsGenerator(
        agent_file="nonexistent.yaml",
        framework="praisonai",
        config_list=[],
    )
    assert generator is not None
    assert adapters._defaults_registered is True
    assert "fusion" in get_retriever_registry().list_retrievers()


def test_register_default_adapters_is_idempotent():
    """Calling twice is a no-op (fast path), preserving backward compat."""
    import praisonai.adapters as adapters

    adapters.register_default_adapters()
    assert adapters._defaults_registered is True
    # Second call must not raise and must remain registered.
    adapters.register_default_adapters()
    assert adapters._defaults_registered is True
