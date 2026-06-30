"""LangGraph via praisonai-frameworks entry point — integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("praisonaiagents.frameworks")

pytest.importorskip("langgraph")
frameworks = pytest.importorskip("praisonai_frameworks")

from praisonai.framework_adapters.registry import (
    FrameworkAdapterRegistry,
    get_default_registry,
    get_install_hint,
    list_available_frameworks,
    list_framework_choices,
)
from praisonai.framework_adapters import registry as registry_module
from praisonai.framework_adapters.validators import assert_framework_available


_LANGGRAPH_YAML = """
framework: langgraph
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


def test_langgraph_adapter_resolves_from_frameworks_package():
    adapter = get_default_registry().create("langgraph")
    assert type(adapter).__module__.startswith("praisonai_frameworks")


def test_langgraph_entry_point_only_registry():
    registry = FrameworkAdapterRegistry()
    assert "langgraph" in registry.list_names()
    adapter = registry.create("langgraph")
    assert type(adapter).__module__.startswith("praisonai_frameworks")


def test_langgraph_install_hint_points_to_frameworks():
    hint = get_install_hint("langgraph")
    assert "praisonai-frameworks" in hint


def test_langgraph_in_registry_discovery_lists():
    names = list_framework_choices(include_unavailable=True)
    assert "langgraph" in names
    if get_default_registry().is_available("langgraph"):
        assert "langgraph" in list_available_frameworks()


def test_assert_framework_available_langgraph_when_installed():
    if not get_default_registry().is_available("langgraph"):
        pytest.skip("langgraph adapter not available in this environment")
    assert_framework_available("langgraph")


@patch("litellm.completion")
def test_agents_generator_langgraph_via_frameworks_adapter(mock_completion):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Done"
    mock_completion.return_value = mock_response

    registry = FrameworkAdapterRegistry()
    adapter = registry.create("langgraph")

    from praisonai.agents_generator import AgentsGenerator

    gen = AgentsGenerator(
        agent_file="agents.yaml",
        framework="langgraph",
        config_list=[{"model": "openai/gpt-4o-mini", "api_key": "test-key"}],
        agent_yaml=_LANGGRAPH_YAML,
        adapter_registry=registry,
    )

    mock_run = MagicMock(return_value="### LangGraph Output ###\nFrameworks langgraph output")
    adapter.run = mock_run

    def _fake_prepare(_config):
        return {
            "adapter": adapter,
            "config": {
                "framework": "langgraph",
                "topic": "AI trends",
                "roles": gen._load_config()["roles"],
            },
            "topic": "AI trends",
            "tools_dict": {},
        }

    with patch.object(gen, "_prepare_for_run", side_effect=_fake_prepare):
        result = gen.generate_crew_and_kickoff()

    assert "Frameworks langgraph output" in result
    mock_run.assert_called_once()


def test_entry_point_metadata_registers_frameworks_langgraph():
    import importlib.metadata

    eps = {
        ep.name: ep.value
        for ep in importlib.metadata.entry_points(group="praisonai.framework_adapters")
    }
    assert "langgraph" in eps
    assert eps["langgraph"].startswith("praisonai_frameworks")
