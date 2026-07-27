"""Tests for the published agents.yaml JSON Schema and editor autocomplete wiring.

Covers issue #3427:
- `YAMLConfig.model_json_schema()` is emitted via `generate_agents_schema()`.
- The committed `agents.schema.json` artefact matches the model.
- A scaffolded `agents.yaml` starts with the `# yaml-language-server` header
  and still round-trips through `ConfigValidator` (execution unaffected).
"""

import json
from pathlib import Path

import pytest
import yaml

from praisonai.config.schema import (
    AGENTS_SCHEMA_URL,
    AGENTS_SCHEMA_HEADER,
    generate_agents_schema,
)
from praisonai.config.validator import ConfigValidator


def test_generate_agents_schema_derived_from_yamlconfig():
    schema = generate_agents_schema()
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["$id"] == AGENTS_SCHEMA_URL
    props = schema["properties"]
    for key in ("roles", "agents", "tasks", "tools", "llm", "workflow"):
        assert key in props, f"expected '{key}' in agents schema properties"


def test_committed_artefact_matches_model():
    artefact = (
        Path(__file__).resolve().parents[2]
        / "praisonai"
        / "config"
        / "agents.schema.json"
    )
    assert artefact.exists(), "agents.schema.json artefact must be committed"
    committed = json.loads(artefact.read_text(encoding="utf-8"))
    assert committed == generate_agents_schema(), (
        "agents.schema.json is stale; regenerate via "
        "`praisonai validate schema -o agents.schema.json`"
    )


def test_published_schema_matches_runtime_contract():
    """Editor schema must accept runtime-normalised YAML shapes (issue #3427).

    The runtime (``agents_generator``) auto-fills ``role``/``goal``, maps
    ``instructions`` -> ``backstory``, and accepts list-form ``roles``/
    ``agents``. The published schema must not mark those forms invalid, so:
    - ``AgentConfig`` has no ``required`` block, and
    - ``roles``/``agents`` allow both dict and list forms.
    """
    schema = generate_agents_schema()

    agent_def = schema["$defs"]["AgentConfig"]
    assert "required" not in agent_def, (
        "published AgentConfig must not force role/goal/backstory; "
        "runtime auto-fills / accepts 'instructions'"
    )

    def _collect_types(node):
        types = set()
        if isinstance(node, dict):
            if isinstance(node.get("type"), str):
                types.add(node["type"])
            for branch in node.get("anyOf", []):
                types |= _collect_types(branch)
        return types

    for key in ("roles", "agents"):
        types = _collect_types(schema["properties"][key])
        assert "array" in types, (
            f"'{key}' must accept list form (runtime _list_to_dict)"
        )
        assert "object" in types, (
            f"'{key}' must still accept canonical dict form"
        )


def test_schema_header_points_at_published_url():
    assert AGENTS_SCHEMA_HEADER.startswith("# yaml-language-server: $schema=")
    assert AGENTS_SCHEMA_URL in AGENTS_SCHEMA_HEADER
    assert AGENTS_SCHEMA_HEADER.endswith("\n")


def test_scaffolded_agents_yaml_has_header_and_round_trips(tmp_path):
    try:
        from praisonai.auto import AutoGenerator
    except ImportError:
        pytest.skip("AutoGenerator not available")

    agent_file = tmp_path / "agents.yaml"
    try:
        gen = AutoGenerator(
            topic="Research AI trends",
            agent_file=str(agent_file),
            framework="praisonai",
        )
    except ImportError:
        pytest.skip("No agent framework adapter available")

    json_data = {
        "roles": {
            "researcher": {
                "role": "Researcher",
                "goal": "Research the topic",
                "backstory": "Expert researcher.",
                "tasks": {
                    "research": {
                        "description": "Research AI trends",
                        "expected_output": "A short report",
                    }
                },
                "tools": [],
            }
        }
    }
    gen.convert_and_save(json_data)

    content = agent_file.read_text(encoding="utf-8")
    # Header is the very first line so editors pick up the schema.
    assert content.startswith("# yaml-language-server: $schema=")
    assert AGENTS_SCHEMA_URL in content.splitlines()[0]

    # Leading comment is ignored by safe_load -> execution unaffected.
    loaded = yaml.safe_load(content)
    assert "roles" in loaded and "researcher" in loaded["roles"]

    # Still round-trips through the runtime validator.
    result = ConfigValidator().validate_yaml_string(content)
    assert result.valid, result.errors
