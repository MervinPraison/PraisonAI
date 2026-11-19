"""Strict provider schemas must preserve the generator's existing YAML contract."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from openai.lib._pydantic import to_strict_json_schema
from praisonai.auto import AutoGenerator, WorkflowAutoGenerator
from pydantic import BaseModel


def assert_closed_schema(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False, value
            assert set(value.get("required", [])) == set(value.get("properties", {})), (
                value
            )
        schemas = list(value.get("properties", {}).values())
        if "items" in value:
            schemas.append(value["items"])
        for schema in schemas:
            assert {
                "type",
                "$ref",
                "anyOf",
                "allOf",
                "enum",
                "const",
            } & schema.keys(), schema
        for item in value.values():
            assert_closed_schema(item)
    elif isinstance(value, list):
        for item in value:
            assert_closed_schema(item)


@pytest.mark.offline
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_team_strict_schema_preserves_named_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asynchronous: bool
) -> None:
    target = tmp_path / "agents.yaml"
    generator = AutoGenerator(
        topic="Greet",
        agent_file=str(target),
        framework="praisonai",
        config_list=[{"model": "test-model", "api_key": "test-key"}],
    )
    payload = {
        "roles": [
            {
                "id": "greeter",
                "role": "Greeter",
                "goal": "Greet",
                "backstory": "Helpful",
                "tools": [],
                "tasks": [
                    {
                        "id": "hello",
                        "description": "Say hello",
                        "expected_output": "Hello",
                    }
                ],
            }
        ]
    }

    async def complete(*, response_model: type[BaseModel], **kwargs: Any) -> BaseModel:
        assert_closed_schema(to_strict_json_schema(response_model))
        return response_model.model_validate(payload)

    monkeypatch.setattr(generator, "_structured_completion_async", complete)
    monkeypatch.setattr(generator, "get_user_content", lambda: "Greet")
    monkeypatch.setattr(generator, "_dangerous_tool_names", lambda: set())
    if asynchronous:
        await generator.agenerate()
    else:
        await asyncio.to_thread(generator.generate)
    data = yaml.safe_load(target.read_text())
    assert data["roles"] == {
        "greeter": {
            "role": "Greeter",
            "goal": "Greet",
            "backstory": "Helpful",
            "tools": [],
            "tasks": {
                "hello": {"description": "Say hello", "expected_output": "Hello"}
            },
        }
    }


@pytest.mark.offline
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "steps",
    [
        [{"agent": "greeter", "action": "Greet"}],
        [{"name": "select", "route": [{"id": "default", "targets": ["greeter"]}]}],
        [{"name": "both", "parallel": [{"agent": "greeter", "action": "Greet"}]}],
        [
            {
                "name": "retry",
                "loop": {
                    "agent": "greeter",
                    "action": "Greet",
                    "condition": "not approved",
                    "max_iterations": 3,
                    "feedback_to": "greeter",
                },
            }
        ],
    ],
)
async def test_workflow_strict_schema_preserves_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
    steps: list[dict[str, Any]],
) -> None:
    target = tmp_path / "workflow.yaml"
    generator = WorkflowAutoGenerator(
        topic="Greet",
        workflow_file=str(target),
        framework="praisonai",
        config_list=[{"model": "test-model", "api_key": "test-key"}],
    )
    payload = {
        "name": "Greeting",
        "description": "Greet",
        "agents": [
            {
                "id": "greeter",
                "name": "Greeter",
                "role": "Greeter",
                "goal": "Greet",
                "instructions": "Say hello",
                "tools": [],
            }
        ],
        "steps": steps,
        "gates": None,
    }

    async def complete(*, response_model: type[BaseModel], **kwargs: Any) -> BaseModel:
        assert_closed_schema(to_strict_json_schema(response_model))
        return response_model.model_validate(payload)

    monkeypatch.setattr(generator, "_structured_completion_async", complete)
    monkeypatch.setattr(generator, "_get_prompt", lambda pattern: "Greet")
    monkeypatch.setattr(generator, "_dangerous_tool_names", lambda: set())
    if asynchronous:
        await generator.agenerate()
    else:
        await asyncio.to_thread(generator.generate)
    data = yaml.safe_load(target.read_text())
    assert data["agents"] == {
        "greeter": {
            "name": "Greeter",
            "role": "Greeter",
            "goal": "Greet",
            "instructions": "Say hello",
        }
    }
    expected = json.loads(json.dumps(steps))
    if "route" in expected[0]:
        expected[0]["route"] = {"default": ["greeter"]}
    assert data["steps"] == expected


@pytest.mark.offline
def test_public_models_still_accept_keyed_data() -> None:
    from praisonai.auto import TeamStructure, WorkflowStructure

    team = TeamStructure(
        roles={
            "greeter": {
                "role": "Greeter",
                "goal": "Greet",
                "backstory": "Helpful",
                "tools": [],
                "tasks": {},
            }
        }
    )
    assert isinstance(team.roles, dict)
    workflow = WorkflowStructure(
        name="Custom", description="Custom", agents={}, steps=[{"custom": "existing"}]
    )
    assert workflow.steps == [{"custom": "existing"}]


@pytest.mark.offline
@pytest.mark.parametrize("value_key", [None, "targets"])
def test_duplicate_generated_ids_are_not_silently_overwritten(
    value_key: str | None,
) -> None:
    from praisonai.auto import _index_named_items

    with pytest.raises(ValueError, match="Duplicate generated ID"):
        _index_named_items(
            [{"id": "same", "targets": ["a"]}, {"id": "same", "targets": ["b"]}],
            value_key=value_key,
        )


@pytest.mark.offline
def test_workflow_model_is_available_in_a_cold_process() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from praisonai.auto import WorkflowStructure; print(WorkflowStructure(name='x', description='x', agents={}, steps=[]).model_dump_json())",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert json.loads(result.stdout)["agents"] == {}
