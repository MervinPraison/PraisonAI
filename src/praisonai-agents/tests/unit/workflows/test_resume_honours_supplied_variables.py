"""Resuming a workflow must keep the value the human just supplied.

A paused-for-review run is resumed with the reviewer's answer:

    praisonai workflow run wf --resume --var reviewer_decision=approved

`_prepare_workflow_loop` built `all_variables` from the workflow defaults plus
the caller's `variables`, and then did:

    all_variables = checkpoint_data.get("variables", all_variables)

The checkpoint's variables REPLACED the caller's, so the answer was accepted
and silently discarded -- the run resumed with the same state it paused in,
and any step reading {{reviewer_decision}} saw nothing.

That is the whole mechanism by which a human hands a decision back to a
suspended run, which is why it matters more than its one-line size suggests.
Precedence is now defaults, then checkpoint, then what the caller supplied
now: the freshest statement of intent wins.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.workflows.workflows import Workflow, WorkflowManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mgr = WorkflowManager()
    mgr._ensure_loaded()
    mgr._workflows["review"] = Workflow(
        name="review",
        description="draft then apply a reviewed decision",
        steps=[{"name": "draft", "action": "echo"},
               {"name": "apply", "action": "use {{reviewer_decision}}"}],
        variables={"topic": "x"},
    )
    return mgr


def _resume(mgr, supplied, saved):
    mgr._save_checkpoint(name="pending", workflow_name="review",
                         completed_steps=1, results=[{"step": "draft"}],
                         variables=saved)
    state = mgr._prepare_workflow_loop(
        workflow_name="review", variables=supplied, default_llm=None,
        planning=False, resume="pending", rebase_checkpoint=True)
    return state["state"]["all_variables"]


class TestResumeKeepsTheSuppliedValue:

    def test_the_humans_answer_survives_the_resume(self, manager):
        variables = _resume(manager, {"reviewer_decision": "approved"},
                            {"topic": "x"})
        assert variables.get("reviewer_decision") == "approved", (
            "the value supplied on resume was discarded"
        )

    def test_checkpoint_state_still_survives(self, manager):
        """The fix must not trade one loss for another."""
        variables = _resume(manager, {"reviewer_decision": "approved"},
                            {"topic": "x", "stage": "drafted"})
        assert variables.get("stage") == "drafted"

    def test_the_supplied_value_wins_a_conflict(self, manager):
        """The reviewer is correcting the run; their answer is the newer fact."""
        variables = _resume(manager, {"stage": "revised"},
                            {"stage": "drafted"})
        assert variables.get("stage") == "revised"

    def test_resuming_with_nothing_supplied_is_unchanged(self, manager):
        """The existing behaviour for a plain --resume must not shift."""
        variables = _resume(manager, None, {"topic": "x", "stage": "drafted"})
        assert variables.get("stage") == "drafted"
        assert variables.get("topic") == "x"

    def test_workflow_defaults_are_not_lost(self, manager):
        variables = _resume(manager, {"reviewer_decision": "yes"}, {})
        assert variables.get("topic") == "x"

    def test_all_three_layers_are_present_together(self, manager):
        variables = _resume(manager, {"reviewer_decision": "approved"},
                            {"stage": "drafted"})
        assert variables.get("topic") == "x"            # workflow default
        assert variables.get("stage") == "drafted"      # checkpoint
        assert variables.get("reviewer_decision") == "approved"  # supplied now


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
