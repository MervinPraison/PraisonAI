"""Action-only steps must also join the shared sandbox.

A workflow step that carries an `action` but no pre-defined `agent` builds a
temporary Agent *during* the run -- after the initial attach(). Without the fix
that temp agent runs its shell/file tools locally, silently bypassing the
`run_on:` sandbox. No Docker required: a fake compute records what it patches.
"""

from praisonaiagents.workflows.workflows import Workflow
from praisonaiagents.task.task import Task


class _RecordingShared:
    """Stand-in for SharedCompute that records every agent it attaches."""

    def __init__(self):
        self.attached = []

    def attach(self, agents):
        self.attached.extend(a for a in agents if a is not None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _build_workflow(monkeypatch):
    """A one-step, action-only workflow wired to a recording shared compute."""
    shared = _RecordingShared()

    wf = Workflow(
        name="temp-agent-run-on",
        steps=[Task(name="s1", action="write a file to /workspace")],
        run_on="docker",
    )
    monkeypatch.setattr(wf, "_shared_compute", lambda: shared)
    return wf, shared


def test_action_only_temp_agent_is_attached(monkeypatch):
    wf, shared = _build_workflow(monkeypatch)

    captured = {}

    def fake_chat(self, action, **kwargs):
        # By the time the temp agent chats, it must already be attached.
        captured["names"] = [getattr(a, "name", None) for a in shared.attached]
        return "done"

    from praisonaiagents.agent.agent import Agent
    monkeypatch.setattr(Agent, "chat", fake_chat)

    result = wf.run(input="go")

    assert result["output"] == "done"
    # The temp agent created for the action-only step reached shared.attach()
    # before its chat() ran -- i.e. it joined the sandbox, not run locally.
    assert captured.get("names"), "temp agent was never attached to shared compute"


def test_active_shared_compute_cleared_after_run(monkeypatch):
    wf, _shared = _build_workflow(monkeypatch)

    from praisonaiagents.agent.agent import Agent
    monkeypatch.setattr(Agent, "chat", lambda self, action, **kw: "done")

    wf.run(input="go")

    # The live-sandbox handle must not leak past the run.
    assert getattr(wf, "_active_shared_compute", None) is None
