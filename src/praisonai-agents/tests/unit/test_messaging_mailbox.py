"""Unit tests for the addressed agent-to-agent mailbox (issue #3063)."""

from praisonaiagents.messaging import (
    AgentMailboxProtocol,
    AgentMessage,
    InProcessMailbox,
)


def test_send_receive_addressed():
    """send('b', ...) delivers only to b; c's inbox stays empty."""
    mb = InProcessMailbox()
    mb.send("b", {"task": "write"}, sender="a")

    got = mb.receive("b")
    assert len(got) == 1
    assert got[0].body == {"task": "write"}
    assert mb.receive("c") == []


def test_receive_drains_inbox():
    """receive removes messages so a second receive is empty."""
    mb = InProcessMailbox()
    mb.send("b", "hi", sender="a")
    assert len(mb.receive("b")) == 1
    assert mb.receive("b") == []


def test_receive_respects_max_and_order():
    """receive returns oldest-first and honours the max cap."""
    mb = InProcessMailbox()
    for i in range(5):
        mb.send("b", i, sender="a")
    first = mb.receive("b", max=2)
    assert [m.body for m in first] == [0, 1]
    rest = mb.receive("b")
    assert [m.body for m in rest] == [2, 3, 4]


def test_subscribe_push():
    """A subscribed callback fires on delivery without polling."""
    mb = InProcessMailbox()
    received = []
    mb.subscribe("b", lambda m: received.append(m))

    mb.send("b", "ping", sender="a")
    assert len(received) == 1
    assert received[0].body == "ping"


def test_subscribe_only_own_inbox():
    """A subscriber for b is not fired by a message to c."""
    mb = InProcessMailbox()
    received = []
    mb.subscribe("b", lambda m: received.append(m))

    mb.send("c", "not-for-b", sender="a")
    assert received == []


def test_sender_recorded():
    """Message carries sender/recipient/correlation_id."""
    mb = InProcessMailbox()
    msg_id = mb.send("b", "body", sender="a", correlation_id="req-1")

    msg = mb.receive("b")[0]
    assert msg.id == msg_id
    assert msg.sender == "a"
    assert msg.recipient == "b"
    assert msg.correlation_id == "req-1"
    assert isinstance(msg.ts, float)


def test_pending_count():
    """pending reflects undelivered messages."""
    mb = InProcessMailbox()
    assert mb.pending("b") == 0
    mb.send("b", 1, sender="a")
    mb.send("b", 2, sender="a")
    assert mb.pending("b") == 2
    mb.receive("b", max=1)
    assert mb.pending("b") == 1


def test_inprocess_default_no_redis():
    """The default implementation works with zero external deps."""
    mb = InProcessMailbox()
    assert isinstance(mb, AgentMailboxProtocol)
    mb.send("b", "ok", sender="a")
    assert mb.receive("b")[0].body == "ok"


def test_message_roundtrip_dict():
    """AgentMessage serializes and deserializes losslessly."""
    msg = AgentMessage(sender="a", recipient="b", body={"k": "v"}, correlation_id="c1")
    data = msg.to_dict()
    restored = AgentMessage.from_dict(data)
    assert restored.sender == "a"
    assert restored.recipient == "b"
    assert restored.body == {"k": "v"}
    assert restored.correlation_id == "c1"
    assert restored.id == msg.id


def test_subscriber_exception_does_not_break_delivery():
    """A raising subscriber does not stop the message from being enqueued."""
    mb = InProcessMailbox()

    def boom(_):
        raise RuntimeError("bad subscriber")

    mb.subscribe("b", boom)
    mb.send("b", "still-delivered", sender="a")
    assert mb.receive("b")[0].body == "still-delivered"
