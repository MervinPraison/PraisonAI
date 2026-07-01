"""Pydantic AI via praisonai-frameworks entry point — integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("praisonaiagents.frameworks")
pytest.importorskip("pydantic_ai", reason="pydantic-ai optional extra not installed")
pytest.importorskip("praisonai_frameworks")

from praisonai.framework_adapters.registry import (
    FrameworkAdapterRegistry,
    get_default_registry,
    get_install_hint,
    list_available_frameworks,
    list_framework_choices,
)
from praisonai.framework_adapters.validators import assert_framework_available


_PYDANTIC_AI_YAML = """
framework: pydantic_ai
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


def test_pydantic_ai_adapter_resolves_from_frameworks_package():
    adapter = get_default_registry().create("pydantic_ai")
    assert type(adapter).__module__.startswith("praisonai_frameworks")


def test_pydantic_ai_entry_point_only_registry():
    registry = FrameworkAdapterRegistry()
    assert "pydantic_ai" in registry.list_names()
    adapter = registry.create("pydantic_ai")
    assert type(adapter).__module__.startswith("praisonai_frameworks")


def test_pydantic_ai_install_hint_points_to_frameworks():
    hint = get_install_hint("pydantic_ai")
    assert "pydantic" in hint.lower()
    assert "praisonai-frameworks" in hint


def test_pydantic_ai_in_registry_discovery_lists():
    names = list_framework_choices(include_unavailable=True)
    assert "pydantic_ai" in names
    if get_default_registry().is_available("pydantic_ai"):
        assert "pydantic_ai" in list_available_frameworks()


def test_assert_framework_available_pydantic_ai_when_installed():
    if not get_default_registry().is_available("pydantic_ai"):
        pytest.skip("pydantic_ai adapter not available in this environment")
    assert_framework_available("pydantic_ai")


@patch("litellm.completion")
def test_agents_generator_pydantic_ai_via_frameworks_adapter(mock_completion):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Done"
    mock_completion.return_value = mock_response

    registry = FrameworkAdapterRegistry()
    adapter = registry.create("pydantic_ai")

    from praisonai.agents_generator import AgentsGenerator

    gen = AgentsGenerator(
        agent_file="agents.yaml",
        framework="pydantic_ai",
        config_list=[{"model": "openai/gpt-4o-mini", "api_key": "test-key"}],
        agent_yaml=_PYDANTIC_AI_YAML,
        adapter_registry=registry,
    )

    mock_run = MagicMock(return_value="### Pydantic AI Output ###\nFrameworks output")
    adapter.run = mock_run

    def _fake_prepare(_config):
        return {
            "adapter": adapter,
            "config": {
                "framework": "pydantic_ai",
                "topic": "AI trends",
                "roles": gen._load_config()["roles"],
            },
            "topic": "AI trends",
            "tools_dict": {},
        }

    with patch.object(gen, "_prepare_for_run", side_effect=_fake_prepare):
        result = gen.generate_crew_and_kickoff()

    assert "Frameworks output" in result
    mock_run.assert_called_once_with(
        {
            "framework": "pydantic_ai",
            "topic": "AI trends",
            "roles": gen._load_config()["roles"],
        },
        [{"model": "openai/gpt-4o-mini", "api_key": "test-key"}],
        "AI trends",
        tools_dict={},
        agent_callback=None,
        task_callback=None,
        cli_config={},
    )


def test_entry_point_metadata_registers_frameworks_pydantic_ai():
    import importlib.metadata

    eps = {
        ep.name: ep.value
        for ep in importlib.metadata.entry_points(group="praisonai.framework_adapters")
    }
    assert "pydantic_ai" in eps
    assert eps["pydantic_ai"].startswith("praisonai_frameworks")
