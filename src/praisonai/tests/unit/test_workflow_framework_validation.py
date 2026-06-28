"""Tests for workflow YAML framework validation."""

import pytest


def test_validate_workflow_framework_allows_praisonai():
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    validate_workflow_framework("praisonai")
    validate_workflow_framework(None)


def test_validate_workflow_framework_rejects_crewai():
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    with pytest.raises(ValueError, match="not supported for workflow execution"):
        validate_workflow_framework("crewai", source="workflow.yaml")


def test_framework_from_config_defaults_praisonai():
    from praisonai.framework_adapters.workflow_framework import framework_from_config

    assert framework_from_config({}) == "praisonai"
    assert framework_from_config({"framework": "CrewAI"}) == "crewai"
