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
