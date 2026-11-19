"""A Slack approval is answered only in its own thread (or a private DM).

When ``conversations.replies`` fails, ``SlackApproval`` falls back to
``conversations.history``. In a shared channel that history holds unrelated
chatter, so only messages in the approval's thread may count there. In a DM
(``D…``) nobody but the approver can post, so the plain fallback stays.
"""

import asyncio

import pytest

from praisonai_bot.bots._slack_approval import SlackApproval

APPROVAL_TS = "1700000000.000100"


def _poll(channel, history):
    approval = SlackApproval(token="xoxb-test", channel=channel, timeout=0.2, poll_interval=0.01)

    async def fake_api(method, payload, session=None):
        if method == "conversations.replies":
            return {"ok": False, "error": "missing_scope"}
        return {"ok": True, "messages": history}

    approval._slack_api = fake_api
    return asyncio.run(approval._poll_for_response(channel, APPROVAL_TS))


def test_unrelated_channel_message_is_not_an_approval():
    decision = _poll("C0SHARED", [{"user": "U_ANYONE", "text": "yes", "ts": "1700000001.0"}])
    assert decision.approved is False
    assert decision.metadata.get("timeout") is True


def test_reply_in_the_approval_thread_still_counts():
    msg = {"user": "U_OWNER", "text": "yes", "ts": "1700000002.0", "thread_ts": APPROVAL_TS}
    assert _poll("C0SHARED", [msg]).approved is True


@pytest.mark.parametrize("text, approved", [("yes", True), ("no", False)])
def test_direct_message_fallback_is_unchanged(text, approved):
    decision = _poll("D0PRIVATE", [{"user": "U_OWNER", "text": text, "ts": "1700000003.0"}])
    assert decision.approved is approved
    assert not decision.metadata.get("timeout")
