"""Regression tests for the hierarchical manager delegation schema.

Ensures ``ManagerInstructions`` produces an OpenAI-compatible strict JSON
schema (``additionalProperties: false``) so hierarchical ``AgentTeam`` runs do
not fall back on OpenAI's structured-output API.
"""

import pytest
from pydantic import ValidationError

from praisonaiagents.process.manager_schema import ManagerInstructions


def test_schema_has_additional_properties_false():
    schema = ManagerInstructions.model_json_schema()
    assert schema.get("additionalProperties") is False


def test_schema_required_fields():
    schema = ManagerInstructions.model_json_schema()
    assert set(schema.get("required", [])) == {"task_id", "agent_name", "action"}


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ManagerInstructions(
            task_id=1,
            agent_name="Worker",
            action="execute",
            extra_field="surprise",
        )


def test_process_uses_shared_model():
    from praisonaiagents.process.process import ManagerInstructions as ProcessMI

    assert ProcessMI is ManagerInstructions


def test_task_id_description_is_not_one_based():
    """Runtime task IDs are 0-based; the schema must not claim 1-based (issue #3700)."""
    description = ManagerInstructions.model_fields["task_id"].description or ""
    assert "1-based" not in description
    assert "0-based" in description
    assert "manager_task" in description
