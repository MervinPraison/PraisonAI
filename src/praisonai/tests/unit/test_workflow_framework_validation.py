"""Tests for workflow YAML framework validation."""

import pytest


def test_validate_workflow_framework_allows_praisonai():
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    validate_workflow_framework("praisonai")
    validate_workflow_framework(None)


@pytest.mark.parametrize(
    "framework",
    ["crewai", "openai_agents", "agno", "google_adk", "pydantic_ai"],
)
def test_validate_workflow_framework_rejects_non_native(framework):
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    with pytest.raises(ValueError, match="not supported for workflow execution") as exc:
        validate_workflow_framework(framework, source="workflow.yaml")
    assert framework in str(exc.value)


def test_framework_from_config_defaults_praisonai():
    from praisonai.framework_adapters.workflow_framework import framework_from_config

    assert framework_from_config({}) == "praisonai"
    assert framework_from_config({"framework": "CrewAI"}) == "crewai"
