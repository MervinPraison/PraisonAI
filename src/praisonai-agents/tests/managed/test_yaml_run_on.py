"""`run_on:` support in workflow YAML.

Gives no-code users the same shared-sandbox execution the Python API has.
No Docker required: parsing and validation only.
"""

import pytest

from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

BASE = """
name: {name}
{extra}agents:
  writer:
    role: Writer
    goal: write things
steps:
  - agent: writer
    action: "write a file"
"""


def _parse(extra="", name="wf"):
    return YAMLWorkflowParser().parse_string(BASE.format(name=name, extra=extra))


def test_run_on_is_parsed():
    assert _parse("run_on: docker\n").run_on == "docker"


def test_run_on_defaults_to_none():
    """Omitting run_on must leave the workflow running locally, as before."""
    assert _parse().run_on is None


def test_run_on_is_case_and_space_insensitive():
    assert _parse("run_on: DOCKER\n").run_on == "docker"
    assert _parse('run_on: "  docker  "\n').run_on == "docker"


@pytest.mark.parametrize("provider", ["docker", "e2b", "modal", "daytona", "flyio", "local"])
def test_all_known_providers_accepted(provider):
    assert _parse(f"run_on: {provider}\n").run_on == provider


def test_unknown_provider_fails_at_load_time():
    """A typo must fail when the file loads, not at the first tool call."""
    with pytest.raises(ValueError) as exc:
        _parse("run_on: dokcer\n")
    assert "dokcer" in str(exc.value)
    assert "Available:" in str(exc.value), "error should list valid names"


def test_non_string_run_on_rejected():
    with pytest.raises(ValueError, match="must be a provider name string"):
        _parse("run_on: 123\n")


def test_run_on_reaches_the_workflow_object():
    """The parsed value must land on the field AgentFlow.run() actually reads."""
    wf = _parse("run_on: docker\n")
    assert "run_on" in getattr(type(wf), "__dataclass_fields__", {})
    assert wf.run_on == "docker"
