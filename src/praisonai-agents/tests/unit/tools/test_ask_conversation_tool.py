"""
Tests for the agent-facing ask_conversation tool (Issue #3689).

Covers the request/reply built-in that resolves the active conversation
requester from the per-turn session context, reuses the send-policy guard, and
always returns a typed outcome (reply | timeout | undelivered | no_route) —
never a silent hang.
"""

import asyncio
import json

from praisonaiagents.tools import ask_conversation
from praisonaiagents.gateway import (
    ConversationReply,
    ConversationRequestProtocol,
    SendDecision,
    SendPolicy,
)
from praisonaiagents.session.context import (
    register_conversation_requester,
    get_conversation_requester,
    clear_conversation_requester,
    register_send_policy,
    clear_send_policy,
)


class FakeRequester:
    """Minimal ConversationRequestProtocol implementation for tests."""

    def __init__(self, reply=None):
        self.asked = []
        self._reply = reply or ConversationReply(
            status="reply", target="slack:ops", text="yes, staging is green"
        )

    async def ask(self, target, text, *, timeout_s=120.0):
        self.asked.append((target, text, timeout_s))
        return self._reply


def test_requester_satisfies_protocol():
    assert isinstance(FakeRequester(), ConversationRequestProtocol)


def test_no_gateway_fails_cleanly():
    result = ask_conversation("slack:ops", "Can we deploy?")
    assert "No active gateway" in result


def test_ask_routes_to_requester_and_returns_reply():
    requester = FakeRequester()
    token = register_conversation_requester(requester)
    try:
        out = ask_conversation("slack:ops", "Can we deploy build 42?", timeout_s=60)
        parsed = json.loads(out)
        assert parsed == {
            "status": "reply",
            "from": "slack:ops",
            "text": "yes, staging is green",
        }
        assert requester.asked == [("slack:ops", "Can we deploy build 42?", 60.0)]
    finally:
        clear_conversation_requester(token)
    assert get_conversation_requester() is None


def test_timeout_outcome_is_typed():
    requester = FakeRequester(reply=ConversationReply(status="timeout", target="slack:ops"))
    token = register_conversation_requester(requester)
    try:
        out = ask_conversation("slack:ops", "still there?")
        parsed = json.loads(out)
        assert parsed["status"] == "timeout"
        assert "text" not in parsed
    finally:
        clear_conversation_requester(token)


def test_no_route_outcome_is_typed():
    requester = FakeRequester(reply=ConversationReply(status="no_route"))
    token = register_conversation_requester(requester)
    try:
        out = ask_conversation("bogus:target", "hi")
        parsed = json.loads(out)
        assert parsed["status"] == "no_route"
    finally:
        clear_conversation_requester(token)


def test_default_timeout_is_passed_through():
    requester = FakeRequester()
    token = register_conversation_requester(requester)
    try:
        ask_conversation("slack:ops", "hi")
        assert requester.asked[0][2] == 120.0
    finally:
        clear_conversation_requester(token)


def test_invalid_timeout_falls_back_to_default():
    requester = FakeRequester()
    token = register_conversation_requester(requester)
    try:
        ask_conversation("slack:ops", "hi", timeout_s="not-a-number")
        assert requester.asked[0][2] == 120.0
    finally:
        clear_conversation_requester(token)


def test_non_positive_and_non_finite_timeouts_fall_back_to_default():
    requester = FakeRequester()
    token = register_conversation_requester(requester)
    try:
        for bad in (0, -5, float("nan"), float("inf"), float("-inf")):
            requester.asked.clear()
            ask_conversation("slack:ops", "hi", timeout_s=bad)
            assert requester.asked[0][2] == 120.0
    finally:
        clear_conversation_requester(token)


def test_absurdly_large_timeout_is_clamped():
    requester = FakeRequester()
    token = register_conversation_requester(requester)
    try:
        ask_conversation("slack:ops", "hi", timeout_s=10_000_000)
        assert requester.asked[0][2] == 3600.0
    finally:
        clear_conversation_requester(token)


def test_denied_ask_is_not_delivered():
    requester = FakeRequester()
    rtoken = register_conversation_requester(requester)
    ptoken = register_send_policy(SendPolicy(default="deny", allow=["origin"]))
    try:
        out = ask_conversation("slack:#exec", "leak?")
        parsed = json.loads(out)
        assert parsed["status"] == "undelivered"
        assert "not permitted" in parsed["detail"]
        # The requester was never invoked.
        assert requester.asked == []
    finally:
        clear_send_policy(ptoken)
        clear_conversation_requester(rtoken)


def test_allowed_ask_passes_through_policy():
    requester = FakeRequester()
    rtoken = register_conversation_requester(requester)
    ptoken = register_send_policy(SendPolicy(default="deny", allow=["slack:ops"]))
    try:
        out = ask_conversation("slack:ops", "deploy?")
        parsed = json.loads(out)
        assert parsed["status"] == "reply"
        assert requester.asked[0][0] == "slack:ops"
    finally:
        clear_send_policy(ptoken)
        clear_conversation_requester(rtoken)


def test_requester_exception_yields_undelivered():
    class Broken:
        async def ask(self, target, text, *, timeout_s=120.0):
            raise RuntimeError("boom")

    token = register_conversation_requester(Broken())
    try:
        out = ask_conversation("slack:ops", "hi")
        parsed = json.loads(out)
        assert parsed["status"] == "undelivered"
        assert "boom" in parsed["detail"]
    finally:
        clear_conversation_requester(token)


def test_ask_works_inside_running_loop():
    requester = FakeRequester()

    async def main():
        token = register_conversation_requester(requester)
        try:
            return ask_conversation("slack:ops", "hi")
        finally:
            clear_conversation_requester(token)

    result = asyncio.run(main())
    assert json.loads(result)["status"] == "reply"


def test_reply_as_dict_shape():
    r = ConversationReply(status="reply", target="slack:ops", text="ok", detail="msg-1")
    assert r.as_dict() == {
        "status": "reply",
        "from": "slack:ops",
        "text": "ok",
        "detail": "msg-1",
    }
    # Non-reply statuses omit text.
    assert ConversationReply(status="timeout").as_dict() == {"status": "timeout"}
