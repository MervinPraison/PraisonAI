"""OpenAI Agents via praisonai-frameworks entry point — integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("praisonaiagents.frameworks")
pytest.importorskip("agents")
pytest.importorskip("praisonai_frameworks")

from praisonai.framework_adapters.registry import (
    FrameworkAdapterRegistry,
    get_default_registry,
    get_install_hint,
    list_available_frameworks,
    list_framework_choices,
)
from praisonai.framework_adapters.validators import assert_framework_available


_OPENAI_AGENTS_YAML = """
framework: openai_agents
topic: AI trends
roles:
  researcher:
    role: Research_Analyst
    goal: Find accurate information on {topic}
    backstory: Expert researcher
    tasks:
      research:
        description: Research {topic}
        expected_output: A concise summary
"""


def test_openai_agents_adapter_resolves_from_frameworks_package():
    adapter = get_default_registry().create("openai_agents")
    assert type(adapter).__module__.startswith("praisonai_frameworks")


def test_openai_agents_entry_point_only_registry():
    registry = FrameworkAdapterRegistry()
    assert "openai_agents" in registry.list_names()
    adapter = registry.create("openai_agents")
    assert type(adapter).__module__.startswith("praisonai_frameworks")


def test_openai_agents_install_hint_points_to_frameworks():
    hint = get_install_hint("openai_agents")
    assert "openai-agents" in hint or "openai_agents" in hint
    assert "praisonai-frameworks" in hint


def test_openai_agents_in_registry_discovery_lists():
    names = list_framework_choices(include_unavailable=True)
    assert "openai_agents" in names
    if get_default_registry().is_available("openai_agents"):
        assert "openai_agents" in list_available_frameworks()


def test_assert_framework_available_openai_agents_when_installed():
    if not get_default_registry().is_available("openai_agents"):
        pytest.skip("openai_agents adapter not available in this environment")
    assert_framework_available("openai_agents")


@patch("litellm.completion")
def test_agents_generator_openai_agents_via_frameworks_adapter(mock_completion):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Done"
    mock_completion.return_value = mock_response

    registry = FrameworkAdapterRegistry()
    adapter = registry.create("openai_agents")

    from praisonai.agents_generator import AgentsGenerator

    gen = AgentsGenerator(
        agent_file="agents.yaml",
        framework="openai_agents",
        config_list=[{"model": "openai/gpt-4o-mini", "api_key": "test-key"}],
        agent_yaml=_OPENAI_AGENTS_YAML,
        adapter_registry=registry,
    )

    mock_run = MagicMock(return_value="### OpenAI Agents Output ###\nFrameworks output")
    adapter.run = mock_run

    def _fake_prepare(_config):
        return {
            "adapter": adapter,
            "config": {
                "framework": "openai_agents",
                "topic": "AI trends",
                "roles": gen._load_config()["roles"],
            },
            "topic": "AI trends",
            "tools_dict": {},
        }

    with patch.object(gen, "_prepare_for_run", side_effect=_fake_prepare):
        result = gen.generate_crew_and_kickoff()

    assert "Frameworks output" in result
    mock_run.assert_called_once()


def test_entry_point_metadata_registers_frameworks_openai_agents():
    import importlib.metadata

    eps = {
        ep.name: ep.value
        for ep in importlib.metadata.entry_points(group="praisonai.framework_adapters")
    }
    assert "openai_agents" in eps
    assert eps["openai_agents"].startswith("praisonai_frameworks")
