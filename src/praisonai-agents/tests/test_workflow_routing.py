"""
Tests for workflow step routing surfaces (issue #4052).

Covers:
- Markdown workflow branch routing actually taking a branch (matched + unmatched).
- Task(routing=TaskRoutingConfig(...)) mapping onto executor-read attributes
  without clobbering ``condition``.
- Task(when=..., then_task=..., else_task=...) redirecting execution in the
  WorkflowManager step loop.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Workflow, Task
from praisonaiagents.workflows import WorkflowManager
from praisonaiagents.workflows.workflow_configs import TaskRoutingConfig


def _run(manager, workflow, outputs):
    """Execute a registered workflow with a scripted per-step executor.

    ``outputs`` maps step name -> output string the stub executor returns,
    recording the visited order so tests can assert non-linear execution.
    """
    manager._workflows[workflow.name] = workflow
    manager._loaded = True
    visited = []

    def executor(prompt, step=None):  # noqa: ARG001
        # The manager calls the executor per step; capture order via on_step.
        return ""

    order = []

    def on_step(step, idx):
        order.append(step.name)

    # Map outputs by step name using a closure over the running index.
    def scripted_executor(prompt):
        # Determine current step from the last on_step callback.
        name = order[-1]
        return outputs.get(name, "")

    result = manager.execute(
        workflow.name,
        executor=scripted_executor,
        on_step=on_step,
    )
    return order, result


class TestRoutingConfigOnTask:
    def test_routing_config_maps_to_branch_attributes(self):
        t = Task(
            name="decision",
            description="d",
            routing=TaskRoutingConfig(
                branches={"success": ["step2"]},
                next_steps=["step3"],
            ),
        )
        assert t.branch_condition == {"success": ["step2"]}
        assert t.next_steps == ["step3"]
        # condition must stay a dict/str, never a dataclass instance.
        assert isinstance(t.condition, (dict, str))

    def test_plain_task_has_routing_attributes(self):
        t = Task(name="s", description="d")
        assert t.branch_condition is None
        assert t.next_steps is None


class TestMarkdownBranchRouting:
    def _branching_workflow(self):
        # step1 branches to 'success_step' when output contains 'success'.
        step1 = Task(
            name="step1",
            description="classify",
            routing=TaskRoutingConfig(branches={"success": ["success_step"]}),
        )
        fail_step = Task(name="fail_step", description="handle failure")
        success_step = Task(name="success_step", description="handle success")
        return Workflow(
            name="branchflow",
            description="branch test",
            steps=[step1, fail_step, success_step],
        )

    def test_matched_branch_is_taken(self):
        manager = WorkflowManager()
        wf = self._branching_workflow()
        order, result = _run(manager, wf, {"step1": "success"})
        # Non-linear: step1 -> success_step, skipping fail_step.
        assert order == ["step1", "success_step"]
        assert "fail_step" not in order

    def test_unmatched_branch_falls_through_linearly(self):
        manager = WorkflowManager()
        wf = self._branching_workflow()
        order, result = _run(manager, wf, {"step1": "nope"})
        # No branch matched -> linear order.
        assert order == ["step1", "fail_step", "success_step"]


class TestWhenRouting:
    def test_when_true_routes_to_then_task(self):
        manager = WorkflowManager()
        step1 = Task(
            name="gate",
            description="gate",
            when="{{previous_output}} contains yes",
            then_task="then_step",
            else_task="else_step",
        )
        else_step = Task(name="else_step", description="else")
        then_step = Task(name="then_step", description="then")
        wf = Workflow(name="whenflow", description="", steps=[step1, else_step, then_step])
        order, _ = _run(manager, wf, {"gate": "yes please"})
        assert order == ["gate", "then_step"]

    def test_when_false_routes_to_else_task(self):
        manager = WorkflowManager()
        step1 = Task(
            name="gate",
            description="gate",
            when="{{previous_output}} contains yes",
            then_task="then_step",
            else_task="else_step",
        )
        else_step = Task(name="else_step", description="else")
        then_step = Task(name="then_step", description="then")
        wf = Workflow(name="whenflow2", description="", steps=[step1, else_step, then_step])
        order, _ = _run(manager, wf, {"gate": "no thanks"})
        assert order == ["gate", "else_step", "then_step"]
