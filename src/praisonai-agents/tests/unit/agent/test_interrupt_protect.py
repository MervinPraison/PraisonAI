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
