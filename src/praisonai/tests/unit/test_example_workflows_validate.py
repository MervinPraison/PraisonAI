"""Round-trip validation for shipped example workflows (issue #4052 Defect 4).

Every workflow under ``examples/yaml/workflows/`` must pass the Pydantic schema
validator, so the validator and the runtime no longer parse different dialects.
"""

from pathlib import Path

import pytest
import yaml

from praisonai.config.validator import ConfigValidator

# repo_root/src/praisonai/tests/unit/this_file -> up 4 to repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKFLOWS_DIR = _REPO_ROOT / "examples" / "yaml" / "workflows"


def _workflow_files():
    if not _WORKFLOWS_DIR.exists():
        return []
    return sorted(
        list(_WORKFLOWS_DIR.glob("*.yaml")) + list(_WORKFLOWS_DIR.glob("*.yml"))
    )


@pytest.mark.skipif(not _workflow_files(), reason="example workflows not present")
@pytest.mark.parametrize("wf_path", _workflow_files(), ids=lambda p: p.name)
def test_example_workflow_passes_schema_validation(wf_path):
    validator = ConfigValidator()
    result = validator.validate_yaml_file(str(wf_path))
    assert result.valid, f"{wf_path.name} failed validation: {result.errors}"


def test_undefined_agent_reference_is_rejected():
    """A workflow that references an undefined agent must fail validation."""
    data = {
        "name": "bad",
        "agents": {
            "classifier": {
                "role": "Classifier",
                "goal": "classify",
                "instructions": "do it",
            }
        },
        "steps": [{"agent": "does_not_exist", "action": "go"}],
    }
    validator = ConfigValidator()
    result = validator.validate_config(data)
    assert not result.valid
    assert any("does_not_exist" in e for e in result.errors)


def _one_agent_config():
    return {
        "classifier": {
            "role": "Classifier",
            "goal": "classify",
            "instructions": "do it",
        }
    }


def test_undefined_agent_in_route_payload_is_rejected():
    """Undefined agents nested in a bare ``route:`` mapping must be rejected."""
    data = {
        "name": "bad-route",
        "agents": _one_agent_config(),
        "steps": [
            {"agent": "classifier", "action": "classify"},
            {
                "name": "routing",
                "route": {
                    "technical": ["classifier"],
                    "creative": ["ghost_writer"],
                    "default": ["classifier"],
                },
            },
        ],
    }
    result = ConfigValidator().validate_config(data)
    assert not result.valid
    assert any("ghost_writer" in e for e in result.errors)


def test_undefined_agent_in_parallel_payload_is_rejected():
    """Undefined agents nested in a bare ``parallel:`` list must be rejected."""
    data = {
        "name": "bad-parallel",
        "agents": _one_agent_config(),
        "steps": [
            {
                "name": "fanout",
                "parallel": [
                    {"agent": "classifier", "action": "a"},
                    {"agent": "phantom", "action": "b"},
                ],
            }
        ],
    }
    result = ConfigValidator().validate_config(data)
    assert not result.valid
    assert any("phantom" in e for e in result.errors)


def test_loop_over_variable_is_not_flagged_as_agent():
    """``loop: {over: <var>}`` names a variable, not an agent — must not error."""
    data = {
        "name": "good-loop",
        "agents": _one_agent_config(),
        "steps": [
            {
                "agent": "classifier",
                "action": "Analyze {{item}}",
                "loop": {"over": "topics"},
            }
        ],
    }
    result = ConfigValidator().validate_config(data)
    assert result.valid, result.errors
