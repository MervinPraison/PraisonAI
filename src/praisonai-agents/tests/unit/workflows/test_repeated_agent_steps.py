"""Sequential workflow steps may use the same agent more than once."""

import pytest

from praisonaiagents.agent.agent import Agent
from praisonaiagents.errors import HandoffCycleError
from praisonaiagents.workflows import Workflow


def test_workflow_reuses_agent_after_another_step(monkeypatch):
    calls = []

    def chat(self, prompt, *args, **kwargs):
        calls.append(self.name)
        return f"{self.name}: {prompt}"

    monkeypatch.setattr(Agent, "chat", chat)
    writer = Agent(name="writer", instructions="Write")
    editor = Agent(name="editor", instructions="Review")
    result = Workflow(steps=[writer, editor, writer]).start("bees")
    assert result["status"] == "completed"
    assert calls == ["writer", "editor", "writer"]


def test_revisiting_the_same_workflow_position_still_detects_a_cycle():
    writer = Agent(name="writer", instructions="Write")
    workflow = Workflow(steps=[writer])
    step = workflow._normalize_single_step(writer, 0)
    workflow._check_handoff_cycle(step, 0)
    with pytest.raises(HandoffCycleError):
        workflow._check_handoff_cycle(step, 0)
