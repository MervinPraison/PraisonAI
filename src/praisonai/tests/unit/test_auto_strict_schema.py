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
    ("steps", "expected"),
    [
        (
            [{"agent": "greeter", "repeat": {"max_iterations": 3}}],
            [{"agent": "greeter", "repeat": {"max_iterations": 3}}],
        ),
        (
            [{"agent": "greeter", "action": "Greet"}],
            [{"agent": "greeter", "action": "Greet"}],
        ),
        (
            [{"name": "select", "route": [{"id": "default", "targets": ["greeter"]}]}],
            [{"name": "select", "route": {"default": ["greeter"]}}],
        ),
        (
            [{"name": "both", "parallel": [{"agent": "greeter", "action": "Greet"}]}],
            [{"name": "both", "parallel": [{"agent": "greeter", "action": "Greet"}]}],
        ),
        (
            [
                {
                    "name": "retry",
                    "agent": "greeter",
                    "action": "Greet",
                    "loop": {"over": "items"},
                }
            ],
            [
                {
                    "name": "retry",
                    "agent": "greeter",
                    "action": "Greet",
                    "loop": {"over": "items"},
                }
            ],
        ),
        (
            [
                {
                    "agent": "greeter",
                    "action": "Greet",
                    "repeat": {"until": "approved", "max_iterations": 3},
                }
            ],
            [
                {
                    "agent": "greeter",
                    "action": "Greet",
                    "repeat": {"until": "approved", "max_iterations": 3},
                }
            ],
        ),
        (
            [
                {
                    "if": {
                        "condition": "approved",
                        "then": [{"agent": "greeter", "action": "Greet"}],
                        "else": [{"agent": "greeter", "action": "Retry"}],
                    }
                }
            ],
            [
                {
                    "if": {
                        "condition": "approved",
                        "then": [{"agent": "greeter", "action": "Greet"}],
                        "else": [{"agent": "greeter", "action": "Retry"}],
                    }
                }
            ],
        ),
        ([{"include": "greeting-recipe"}], [{"include": "greeting-recipe"}]),
        (
            [
                {
                    "loop": {"over": "items"},
                    "steps": [{"agent": "greeter", "action": "Greet"}],
                }
            ],
            [
                {
                    "loop": {"over": "items"},
                    "steps": [{"agent": "greeter", "action": "Greet"}],
                }
            ],
        ),
        (
            [
                {
                    "loop": {"over": "items"},
                    "steps": [{"route": [{"id": "default", "targets": ["greeter"]}]}],
                }
            ],
            [
                {
                    "loop": {"over": "items"},
                    "steps": [{"route": {"default": ["greeter"]}}],
                }
            ],
        ),
    ],
)
async def test_workflow_strict_schema_preserves_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
    steps: list[dict[str, Any]],
    expected: list[dict[str, Any]],
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
    assert data["steps"] == expected
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    parser = YAMLWorkflowParser()
    workflow = parser.parse_file(target)
    assert len(workflow.steps) == len(expected)
    if "parallel" in expected[0]:
        assert workflow.steps[0].steps == [parser._agents["greeter"]]


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


@pytest.mark.offline
@pytest.mark.parametrize("unknown", [False, True])
async def test_generated_step_options_reach_the_yaml_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unknown: bool
) -> None:
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    target = tmp_path / "workflow.yaml"
    generator = WorkflowAutoGenerator(
        topic="Write report",
        workflow_file=str(target),
        framework="praisonai",
        config_list=[{"model": "test-model", "api_key": "test-key"}],
    )
    options = {
        "agent": "writer",
        "action": "Write",
        "name": "report",
        "output_file": "report.md",
        "context": ["research"],
        "guardrail": "Check the report",
        "max_retries": 2,
        "create_directory": False,
        "async_execution": False,
        "output_variable": "report_result",
        "skip_on_failure": False,
        "retry_delay": 0,
    }
    payload = {
        "name": "Report",
        "description": "Write",
        "agents": [
            {
                "id": "writer",
                "name": "Writer",
                "role": "Writer",
                "goal": "Write",
                "instructions": "Write",
                "tools": [],
            }
        ],
        "steps": [options],
    }

    async def complete(*, response_model: type[BaseModel], **kwargs: Any) -> BaseModel:
        assert_closed_schema(to_strict_json_schema(response_model))
        return response_model.model_validate(payload)

    monkeypatch.setattr(generator, "_structured_completion_async", complete)
    monkeypatch.setattr(generator, "_get_prompt", lambda pattern: "Write")
    monkeypatch.setattr(generator, "_dangerous_tool_names", lambda: set())
    if unknown:
        options["unsupported_option"] = "must not disappear"
        with pytest.raises(ValueError):
            await generator.agenerate()
        assert not target.exists()
        return
    await generator.agenerate()
    assert yaml.safe_load(target.read_text())["steps"] == [options]
    parser = YAMLWorkflowParser()
    parser.parse_file(target)
    agent = parser._agents["writer"]
    assert agent._yaml_output_file == "report.md"
    assert agent._yaml_context == ["research"]
    assert agent._yaml_guardrail == "Check the report"


@pytest.mark.offline
def test_parallel_rejects_patterns_the_reader_would_drop() -> None:
    from praisonai.auto import _get_workflow_models

    model = _get_workflow_models()["WorkflowOutput"]
    with pytest.raises(ValueError):
        model.model_validate(
            {
                "name": "Bad",
                "description": "Bad",
                "agents": [],
                "steps": [
                    {
                        "parallel": [
                            {"route": [{"id": "default", "targets": ["writer"]}]}
                        ]
                    }
                ],
            }
        )


@pytest.mark.offline
def test_merging_rewrites_nested_agent_references(tmp_path: Path) -> None:
    target = tmp_path / "workflow.yaml"
    old = {"name": "Existing", "agents": {"writer": {"name": "Original"}}, "steps": []}
    target.write_text(yaml.safe_dump(old))
    generator = WorkflowAutoGenerator(
        topic="Write",
        workflow_file=str(target),
        framework="praisonai",
        config_list=[{"model": "test-model", "api_key": "test-key"}],
    )
    fresh = {
        "name": "New",
        "agents": {"writer": {"name": "New"}},
        "steps": [
            {
                "if": {
                    "condition": "writer",
                    "then": [{"agent": "writer"}],
                    "else": [{"agent": "writer"}],
                }
            },
            {"loop": {"over": "items", "step": "writer"}},
            {"loop": {"over": "items"}, "step": "writer"},
            {"loop": {"over": "items"}, "steps": [{"agent": "writer"}]},
        ],
    }
    merged = generator.merge_with_existing_workflow(fresh)
    assert merged["agents"]["writer"] == {"name": "Original"}
    assert merged["agents"]["writer_auto_1"] == {"name": "New"}
    assert merged["steps"] == [
        {
            "if": {
                "condition": "writer",
                "then": [{"agent": "writer_auto_1"}],
                "else": [{"agent": "writer_auto_1"}],
            }
        },
        {"loop": {"over": "items", "step": "writer_auto_1"}},
        {"loop": {"over": "items"}, "step": "writer_auto_1"},
        {"loop": {"over": "items"}, "steps": [{"agent": "writer_auto_1"}]},
    ]
    assert fresh["steps"][0]["if"]["then"][0]["agent"] == "writer"
