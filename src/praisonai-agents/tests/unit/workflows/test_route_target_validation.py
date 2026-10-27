"""Route references must not silently discard undefined agents."""
import pytest

from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser


PREFIX = """name: route-validation
agents:
  known:
    name: Known
    instructions: Greet.
    llm: openai/fixture-model
steps:
"""


@pytest.mark.parametrize("target", ["missing", "[known, missing]"])
def test_route_rejects_undefined_target(target):
    source = PREFIX + f"  - route:\n      chosen: {target}\n"
    with pytest.raises(ValueError, match="Agent 'missing'.*route 'chosen'"):
        YAMLWorkflowParser().parse_string(source)


@pytest.mark.parametrize("target", ["known", "[known]"])
def test_route_keeps_defined_targets(target):
    source = PREFIX + f"  - route:\n      chosen: {target}\n"
    flow = YAMLWorkflowParser().parse_string(source)
    assert [agent.name for agent in flow.steps[0].routes["chosen"]] == ["Known"]
