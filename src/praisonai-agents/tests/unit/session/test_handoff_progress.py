"""Continuation prompts must distinguish running work from proven completion."""

import pytest

from praisonaiagents.session import build_handoff_prompt


@pytest.mark.parametrize(
    "checkpoint,expected,absent",
    [
        ({"current_step": "deploy"}, "PROGRESS: current step: deploy", ["last completed", "steps done"]),
        ({"completed_steps": 0, "total_steps": 5, "current_step": "deploy"},
         "PROGRESS: 0 of 5 workflow steps done; current step: deploy", ["last completed"]),
        ({"completed_steps": 2, "total_steps": 5, "last_step": "build", "current_step": "deploy"},
         "PROGRESS: 2 of 5 workflow steps done; last completed: build; current step: deploy", []),
        ({"last_step": "build"}, "PROGRESS: last completed: build", ["steps done"]),
        ({"completed_steps": 0, "total_steps": 0, "step_count": 9},
         "PROGRESS: 0 of 0 workflow steps done", ["of 9"]),
        ({"completed_steps": 2, "step_count": 5, "last_step": "build"},
         "PROGRESS: 2 of 5 workflow steps done; last completed: build", []),
    ],
)
def test_handoff_reports_only_the_supplied_progress(checkpoint, expected, absent):
    prompt = build_handoff_prompt(workflow_checkpoint=checkpoint)

    assert expected in prompt
    for text in absent:
        assert text not in prompt
    assert prompt.endswith("before acting.")
