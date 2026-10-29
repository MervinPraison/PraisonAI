"""Tests for InterruptController.protect() windows (#6122)."""

from types import SimpleNamespace

from praisonaiagents.agent.interrupt import InterruptController, protect_turn
from praisonaiagents.agent.tool_execution import _active_turn_cancel
from praisonaiagents.tools.subagent_tool import create_subagent_tool


def test_protect_window_is_nested_and_scoped():
    ctrl = InterruptController()
    assert not ctrl.is_protected()
    with ctrl.protect():
        with ctrl.protect():
            assert ctrl.is_protected()
        assert ctrl.is_protected()
    assert not ctrl.is_protected()


def test_protect_does_not_block_request():
    ctrl = InterruptController()
    with ctrl.protect():
        ctrl.request("user_stop_command")
        assert ctrl.is_set()


def test_protect_turn_tolerates_missing_controller():
    with protect_turn(None):
        pass
    with protect_turn(object()):
        pass


def test_foreground_subagent_protects_parent_turn():
    ctrl = InterruptController()
    parent = SimpleNamespace(interrupt_controller=ctrl)
    seen = []

    class _Sub:
        def chat(self, prompt):
            seen.append(ctrl.is_protected())
            return "done"

    spawn = create_subagent_tool(agent_factory=lambda **_: _Sub())["function"]
    token = _active_turn_cancel.set((parent, None))
    try:
        result = spawn("do work")
    finally:
        _active_turn_cancel.reset(token)

    assert result["success"]
    assert seen == [True]
    assert not ctrl.is_protected()


class _Compactor:
    """Records whether the turn was protected while compacting."""

    def __init__(self, ctrl, fail=False):
        self.ctrl, self.fail, self.seen = ctrl, fail, []

    def _run(self, messages):
        self.seen.append(self.ctrl.is_protected())
        if self.fail:
            raise RuntimeError("compaction failed")
        return messages, SimpleNamespace(original_tokens=2, compacted_tokens=1, messages_removed=0)

    compact = _run

    def needs_compaction(self, _messages):
        return False


def _agent_with(ctrl):
    from praisonaiagents import Agent
    agent = Agent(name="t", instructions="t")
    agent.interrupt_controller = ctrl
    agent._persist_compaction_checkpoint = lambda _r: None
    return agent


def _policy():
    from praisonaiagents.context.policy import CompactionStrategy
    return SimpleNamespace(strategy=CompactionStrategy.TRUNCATE)


def test_proactive_compaction_protects_turn():
    import pytest
    ctrl = InterruptController()
    agent = _agent_with(ctrl)
    ok = _Compactor(ctrl)
    agent._apply_compaction([{"role": "user", "content": "x"}], ok, _policy())
    assert ok.seen == [True] and not ctrl.is_protected()

    bad = _Compactor(ctrl, fail=True)
    with pytest.raises(RuntimeError):
        agent._apply_compaction([{"role": "user", "content": "x"}], bad, _policy())
    assert bad.seen == [True] and not ctrl.is_protected()


def test_proactive_compaction_async_protects_turn():
    import asyncio
    ctrl = InterruptController()
    agent = _agent_with(ctrl)
    ok = _Compactor(ctrl)
    asyncio.run(agent._apply_compaction_async([{"role": "user", "content": "x"}], ok, _policy()))
    assert ok.seen == [True] and not ctrl.is_protected()
