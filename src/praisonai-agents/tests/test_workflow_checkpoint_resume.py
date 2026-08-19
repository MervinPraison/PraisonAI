"""
Tests for workflow checkpoint resume + definition fingerprinting.

Covers the correctness hazard where resuming against an edited workflow file
silently lands on a stale step index: a stable definition fingerprint is stored
in the checkpoint and compared on resume.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents.workflows import WorkflowManager


WORKFLOW_3_STEPS = """---
name: demo
description: Three step demo
---

## Step 1: One
First step.

```action
Do step one
```

## Step 2: Two
Second step.

```action
Do step two
```

## Step 3: Three
Third step.

```action
Do step three
```
"""

# Same three steps, only whitespace/comment differences -> same fingerprint.
WORKFLOW_3_STEPS_WHITESPACE = """---
name: demo
description: Three step demo (reworded description, extra blank lines)
---


## Step 1: One
First step.



```action
Do step one
```

## Step 2: Two
Second step.

```action
Do step two
```

## Step 3: Three
Third step.

```action
Do step three
```
"""

# A structurally different workflow (a step added) -> different fingerprint.
WORKFLOW_4_STEPS = WORKFLOW_3_STEPS + """
## Step 4: Four
Fourth step.

```action
Do step four
```
"""


def _write_workflow(workspace: str, body: str) -> None:
    wf_dir = os.path.join(workspace, ".praisonai", "workflows")
    os.makedirs(wf_dir, exist_ok=True)
    with open(os.path.join(wf_dir, "demo.md"), "w") as f:
        f.write(body)


def _make_executor(marker_dir: str, crash_on: str = None):
    """Executor that records which steps ran and can simulate a crash.

    A crash raises ``KeyboardInterrupt`` (a ``BaseException``, not an
    ``Exception``) so it escapes the per-step error handling exactly like a real
    interrupt/container recycle would — the failing step's checkpoint is never
    written, so a subsequent resume re-runs that step from the beginning.
    """
    def executor(prompt: str) -> str:
        # The prompt contains the action text; map back to a step marker.
        for step_no, needle in (("1", "step one"), ("2", "step two"),
                                ("3", "step three"), ("4", "step four")):
            if needle in prompt.lower():
                if crash_on == step_no:
                    raise KeyboardInterrupt(f"crash on step {step_no}")
                open(os.path.join(marker_dir, f"step{step_no}"), "w").close()
                return f"ran step {step_no}"
        return "ran"
    return executor


def _ran(marker_dir: str, step_no: str) -> bool:
    return os.path.exists(os.path.join(marker_dir, f"step{step_no}"))


class TestResumeSkipsCompletedSteps:
    def test_resume_runs_only_remaining_steps(self):
        with tempfile.TemporaryDirectory() as workspace:
            _write_workflow(workspace, WORKFLOW_3_STEPS)
            marker_dir = os.path.join(workspace, "markers")
            os.makedirs(marker_dir)

            manager = WorkflowManager(workspace_path=workspace)

            # First run: crash on step 3 (steps 1-2 complete + checkpointed).
            with pytest.raises(KeyboardInterrupt):
                manager.execute(
                    "demo",
                    executor=_make_executor(marker_dir, crash_on="3"),
                    checkpoint="demo",
                )
            assert _ran(marker_dir, "1")
            assert _ran(marker_dir, "2")
            assert not _ran(marker_dir, "3")

            # Fresh markers so re-execution of 1-2 would be detectable.
            for f in os.listdir(marker_dir):
                os.remove(os.path.join(marker_dir, f))

            # Resume: only step 3 should execute.
            result = manager.execute(
                "demo",
                executor=_make_executor(marker_dir),
                checkpoint="demo",
                resume="demo",
            )
            assert result["success"] is True
            assert not _ran(marker_dir, "1")
            assert not _ran(marker_dir, "2")
            assert _ran(marker_dir, "3")
            assert result.get("resumed_from_step") == 2


class TestDefinitionFingerprint:
    def test_whitespace_edit_does_not_change_fingerprint(self):
        with tempfile.TemporaryDirectory() as ws1, tempfile.TemporaryDirectory() as ws2:
            _write_workflow(ws1, WORKFLOW_3_STEPS)
            _write_workflow(ws2, WORKFLOW_3_STEPS_WHITESPACE)
            m1 = WorkflowManager(workspace_path=ws1)
            m2 = WorkflowManager(workspace_path=ws2)
            fp1 = m1._definition_fingerprint(m1.get_workflow("demo"))
            fp2 = m2._definition_fingerprint(m2.get_workflow("demo"))
            assert fp1 == fp2

    def test_structural_edit_changes_fingerprint(self):
        with tempfile.TemporaryDirectory() as ws1, tempfile.TemporaryDirectory() as ws2:
            _write_workflow(ws1, WORKFLOW_3_STEPS)
            _write_workflow(ws2, WORKFLOW_4_STEPS)
            m1 = WorkflowManager(workspace_path=ws1)
            m2 = WorkflowManager(workspace_path=ws2)
            fp1 = m1._definition_fingerprint(m1.get_workflow("demo"))
            fp2 = m2._definition_fingerprint(m2.get_workflow("demo"))
            assert fp1 != fp2

    def test_resume_after_edit_refuses_with_mismatch(self):
        with tempfile.TemporaryDirectory() as workspace:
            _write_workflow(workspace, WORKFLOW_3_STEPS)
            marker_dir = os.path.join(workspace, "markers")
            os.makedirs(marker_dir)
            manager = WorkflowManager(workspace_path=workspace)

            with pytest.raises(KeyboardInterrupt):
                manager.execute(
                    "demo",
                    executor=_make_executor(marker_dir, crash_on="3"),
                    checkpoint="demo",
                )

            # Edit the workflow (add a step) then reload.
            _write_workflow(workspace, WORKFLOW_4_STEPS)
            manager.reload()

            result = manager.execute(
                "demo",
                executor=_make_executor(marker_dir),
                checkpoint="demo",
                resume="demo",
            )
            assert result["success"] is False
            assert "fingerprint mismatch" in result["error"]
            assert "--rebase-checkpoint" in result["error"]

    def test_rebase_checkpoint_forces_resume_after_edit(self):
        with tempfile.TemporaryDirectory() as workspace:
            _write_workflow(workspace, WORKFLOW_3_STEPS)
            marker_dir = os.path.join(workspace, "markers")
            os.makedirs(marker_dir)
            manager = WorkflowManager(workspace_path=workspace)

            with pytest.raises(KeyboardInterrupt):
                manager.execute(
                    "demo",
                    executor=_make_executor(marker_dir, crash_on="3"),
                    checkpoint="demo",
                )

            _write_workflow(workspace, WORKFLOW_4_STEPS)
            manager.reload()
            for f in os.listdir(marker_dir):
                os.remove(os.path.join(marker_dir, f))

            result = manager.execute(
                "demo",
                executor=_make_executor(marker_dir),
                checkpoint="demo",
                resume="demo",
                rebase_checkpoint=True,
            )
            assert result["success"] is True
            # Continues at the same index (step 3) against the edited definition.
            assert not _ran(marker_dir, "1")
            assert not _ran(marker_dir, "2")
            assert _ran(marker_dir, "3")


class TestResumeFailsClosedOnMissingCheckpoint:
    def test_resume_missing_checkpoint_does_not_run(self):
        with tempfile.TemporaryDirectory() as workspace:
            _write_workflow(workspace, WORKFLOW_3_STEPS)
            marker_dir = os.path.join(workspace, "markers")
            os.makedirs(marker_dir)
            manager = WorkflowManager(workspace_path=workspace)

            # No checkpoint was ever saved; an explicit resume must fail closed
            # rather than silently re-running every step from the beginning.
            result = manager.execute(
                "demo",
                executor=_make_executor(marker_dir),
                resume="does-not-exist",
            )
            assert result["success"] is False
            assert "not found" in result["error"]
            assert not _ran(marker_dir, "1")
            assert not _ran(marker_dir, "2")
            assert not _ran(marker_dir, "3")


class TestConfigValueEditChangesFingerprint:
    def test_agent_config_value_change_changes_fingerprint(self):
        with tempfile.TemporaryDirectory() as workspace:
            _write_workflow(workspace, WORKFLOW_3_STEPS)
            manager = WorkflowManager(workspace_path=workspace)
            workflow = manager.get_workflow("demo")

            fp_before = manager._definition_fingerprint(workflow)

            # Same config keys, different value: a semantic edit that must
            # invalidate the checkpoint (keys-only hashing would miss this).
            workflow.steps[0].agent_config = {"instructions": "old"}
            fp_key = manager._definition_fingerprint(workflow)
            workflow.steps[0].agent_config = {"instructions": "new"}
            fp_value = manager._definition_fingerprint(workflow)

            assert fp_before != fp_key
            assert fp_key != fp_value


class TestCheckpointListingAndDelete:
    def test_list_and_delete_checkpoints(self):
        with tempfile.TemporaryDirectory() as workspace:
            _write_workflow(workspace, WORKFLOW_3_STEPS)
            marker_dir = os.path.join(workspace, "markers")
            os.makedirs(marker_dir)
            manager = WorkflowManager(workspace_path=workspace)

            manager.execute(
                "demo",
                executor=_make_executor(marker_dir),
                checkpoint="demo",
            )

            checkpoints = manager.list_checkpoints()
            assert any(cp["name"] == "demo" for cp in checkpoints)
            cp = next(cp for cp in checkpoints if cp["name"] == "demo")
            assert cp["definition_fingerprint"]

            assert manager.delete_checkpoint("demo") is True
            assert not any(c["name"] == "demo" for c in manager.list_checkpoints())
