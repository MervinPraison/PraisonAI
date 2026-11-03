"""An agent's YAML `execution:` block reaches ExecutionConfig (Issue #6206)."""
from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser


def test_execution_block_passes_budget_and_durable_keys():
    agent = YAMLWorkflowParser()._create_agent("worker", {
        "role": "Worker",
        "execution": {
            "max_budget": 1.5,
            "on_budget_exceeded": "warn",
            "durable": True,
            "resume_run_id": "run-123",
        },
        "max_iter": 7,
    })
    assert agent._max_budget == 1.5
    assert agent._on_budget_exceeded == "warn"
    assert agent.execution.durable is True
    assert agent.execution.resume_run_id == "run-123"
    assert agent.execution.max_iter == 7


def test_flat_max_iter_overrides_execution_block():
    agent = YAMLWorkflowParser()._create_agent("worker", {
        "execution": {"max_iter": 3},
        "max_iter": 9,
    })
    assert agent.execution.max_iter == 9


def test_no_execution_block_keeps_defaults():
    agent = YAMLWorkflowParser()._create_agent("worker", {"role": "Worker"})
    assert not agent._max_budget
