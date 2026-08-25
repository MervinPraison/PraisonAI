"""Every WebSocket message type the gateway dispatches must be scope-classified.

`resolve_required_scope` fails closed to ADMIN for anything it does not know, which
is the right default and is why it cannot simply be switched on: four of the six
message types the dispatcher handles today are unregistered, so enabling it would
demand ADMIN for the connection handshake and lock out every client.

This suite pins the two lists together. It is a lockstep test in jan's style --
it does not exercise behaviour, it asserts that two independently-maintained lists
agree, which is a failure mode no behavioural test can see: the code compiles, the
unit tests pass, and the omission only appears as a permission error at runtime.
"""

import re
from pathlib import Path

import pytest

from praisonaiagents.gateway.protocols import (
    GATEWAY_METHODS,
    OperatorScope,
    resolve_required_scope,
)

_SERVER = (
    Path(__file__).resolve().parents[3]
    / "praisonai-bot"
    / "praisonai_bot"
    / "gateway"
    / "server.py"
)

# Types handled by the transport itself, before any authorization decision.
_TRANSPORT_TYPES = {"pong", "ping"}


def _dispatched_message_types() -> set[str]:
    """Extract the msg_type branches from the gateway's WS dispatcher."""
    source = _SERVER.read_text()
    found: set[str] = set()
    found.update(re.findall(r'msg_type == "([a-z_.]+)"', source))
    for group in re.findall(r"msg_type in \(([^)]*)\)", source):
        found.update(re.findall(r'"([a-z_.]+)"', group))
    return found - _TRANSPORT_TYPES


@pytest.mark.skipif(not _SERVER.exists(), reason="praisonai-bot not present in this checkout")
def test_the_dispatcher_handles_types_this_test_can_see():
    """Positive control: if the extraction breaks, every other test here passes vacuously."""
    types = _dispatched_message_types()
    assert len(types) >= 4, f"extraction found only {types}; the regex has drifted from the source"
    assert "message" in types, "the most basic message type was not extracted"


@pytest.mark.skipif(not _SERVER.exists(), reason="praisonai-bot not present in this checkout")
def test_every_dispatched_message_type_is_scope_classified():
    unregistered = sorted(t for t in _dispatched_message_types() if t not in GATEWAY_METHODS)
    assert not unregistered, (
        "these WebSocket message types are dispatched but carry no scope classification, "
        f"so resolve_required_scope() would fail them closed to ADMIN: {unregistered}. "
        "Register each via register_gateway_method() before wiring the resolver into dispatch."
    )


def test_an_unknown_method_still_fails_closed():
    """The property the whole design rests on. Must survive any registration change."""
    for unknown in ("sessions.list", "config.write", "definitely.not.a.method", ""):
        assert resolve_required_scope(unknown) is OperatorScope.ADMIN


def test_the_handshake_is_not_accidentally_admin():
    """`hello` runs before a client can hold any scope; requiring ADMIN would lock everyone out."""
    if "hello" not in GATEWAY_METHODS:
        pytest.skip("hello not yet registered")
    assert resolve_required_scope("hello") is not OperatorScope.ADMIN
