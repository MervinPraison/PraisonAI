"""Tests for workflow YAML framework validation."""

import pytest


def test_validate_workflow_framework_allows_praisonai():
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    validate_workflow_framework("praisonai")
    validate_workflow_framework(None)


def test_validate_workflow_framework_rejects_crewai(caplog):
    import logging
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="not supported for workflow execution"):
            validate_workflow_framework("crewai", source="workflow.yaml")
    assert any("crewai" in r.message for r in caplog.records)


def test_validate_workflow_framework_rejects_openai_agents(caplog):
    import logging
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="not supported for workflow execution"):
            validate_workflow_framework("openai_agents", source="workflow.yaml")
    assert any("openai_agents" in r.message for r in caplog.records)


def test_validate_workflow_framework_rejects_agno(caplog):
    import logging
    from praisonai.framework_adapters.workflow_framework import validate_workflow_framework

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="not supported for workflow execution"):
            validate_workflow_framework("agno", source="workflow.yaml")
    assert any("agno" in r.message for r in caplog.records)


def test_framework_from_config_defaults_praisonai():
    from praisonai.framework_adapters.workflow_framework import framework_from_config

    assert framework_from_config({}) == "praisonai"
    assert framework_from_config({"framework": "CrewAI"}) == "crewai"
