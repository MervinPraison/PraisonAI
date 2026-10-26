"""spawn_subagent(background=True, deliver=...) inside a gateway turn (#6037).

The model cannot supply the origin chat, so it must come from the turn's
session context, and the result must reach the turn's outbound messenger.
"""

import time

from praisonaiagents.background.job_manager import get_job_manager
from praisonaiagents.gateway.protocols import DeliveryResult
from praisonaiagents.session.context import (
    clear_outbound_messenger,
    clear_session_context,
    register_outbound_messenger,
    set_session_context,
)
from praisonaiagents.tools.subagent_tool import create_subagent_tool


class _StubAgent:
    def chat(self, prompt):
        return "long job done"


class _FakeMessenger:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    async def send(self, target, text, *, media=None):
        self.sent.append((target, text))
        return DeliveryResult(ok=self.ok, target=target)

    def list_targets(self):
        return []


def _spawn_in_turn(messenger, deliver="origin", **kwargs):
    tool = create_subagent_tool(agent_factory=lambda **kw: _StubAgent())
    ctx = set_session_context(
        platform="telegram", chat_id="100", thread_id="7", user_id="alice"
    )
    msg = register_outbound_messenger(messenger)
    try:
        return tool["function"](
            task="summarise", background=True, deliver=deliver, **kwargs
        )
    finally:
        clear_outbound_messenger(msg)
        clear_session_context(ctx)


def _wait_info(job_id):
    jm = get_job_manager()
    jm.get_result(job_id, timeout=5)
    for _ in range(50):
        info = jm.get_job_info(job_id)
        if info.delivered:
            break
        time.sleep(0.02)
    return info


def test_origin_filled_from_session_context_and_delivered_once():
    messenger = _FakeMessenger()
    handle = _spawn_in_turn(messenger)
    info = _wait_info(handle["job_id"])

    assert info.origin["platform"] == "telegram"
    assert info.origin["chat_id"] == "100"
    assert info.origin["thread_id"] == "7"
    assert info.origin["user_id"] == "alice"
    assert info.delivered is True
    assert len(messenger.sent) == 1
    target, text = messenger.sent[0]
    assert target == "origin"
    assert "long job done" in text


def test_explicit_origin_arguments_win():
    messenger = _FakeMessenger()
    handle = _spawn_in_turn(messenger, platform="slack", chat_id="C9")
    info = _wait_info(handle["job_id"])
    assert info.origin["platform"] == "slack"
    assert info.origin["chat_id"] == "C9"
    assert info.origin["thread_id"] == ""
    assert info.origin["user_id"] == "alice"
    # A different chat is not the turn's chat: never send it to chat "100".
    assert messenger.sent == []
    assert info.delivered is False


def test_explicit_other_thread_is_not_auto_sent():
    messenger = _FakeMessenger()
    handle = _spawn_in_turn(messenger, thread_id="99")
    info = _wait_info(handle["job_id"])
    assert info.origin["thread_id"] == "99"
    assert messenger.sent == []
    assert info.delivered is False


def test_non_origin_target_is_not_auto_sent():
    messenger = _FakeMessenger()
    handle = _spawn_in_turn(messenger, deliver="telegram:999")
    info = _wait_info(handle["job_id"])
    assert messenger.sent == []
    assert info.delivered is False


def test_send_policy_denial_blocks_auto_send():
    from praisonaiagents.gateway.protocols import SendDecision
    from praisonaiagents.session.context import (
        clear_send_policy,
        register_send_policy,
    )

    class _Deny:
        def evaluate(self, target, **kw):
            return SendDecision(allow=False, reason="no")

    messenger = _FakeMessenger()
    token = register_send_policy(_Deny())
    try:
        handle = _spawn_in_turn(messenger)
    finally:
        clear_send_policy(token)
    info = _wait_info(handle["job_id"])
    assert messenger.sent == []
    assert info.delivered is False


def test_rejected_send_is_not_marked_delivered():
    messenger = _FakeMessenger(ok=False)
    handle = _spawn_in_turn(messenger)
    jm = get_job_manager()
    jm.get_result(handle["job_id"], timeout=5)
    time.sleep(0.1)
    assert len(messenger.sent) == 1
    assert jm.get_job_info(handle["job_id"]).delivered is False


def test_without_gateway_stays_pull_only():
    tool = create_subagent_tool(agent_factory=lambda **kw: _StubAgent())
    handle = tool["function"](task="t", background=True, deliver="origin")
    jm = get_job_manager()
    jm.get_result(handle["job_id"], timeout=5)
    time.sleep(0.05)
    info = jm.get_job_info(handle["job_id"])
    assert info.delivered is False
    assert info.origin["chat_id"] == ""
