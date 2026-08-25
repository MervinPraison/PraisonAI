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
    EventType,
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


_OPERAND = r'"[a-z_.]+"|EventType\.[A-Z_]+\.value'


def _resolve_operand(token: str) -> str | None:
    """Map one ``msg_type`` comparison operand to the wire string it matches.

    A string literal is its own wire value; an ``EventType.<NAME>.value``
    reference resolves through the enum exactly as Python would at runtime.
    Anything else (an unknown enum member, a non-literal expression) yields
    ``None`` so it can be surfaced rather than silently dropped.
    """
    literal = re.fullmatch(r'"([a-z_.]+)"', token)
    if literal:
        return literal.group(1)
    enum_ref = re.fullmatch(r"EventType\.([A-Z_]+)\.value", token)
    if enum_ref:
        member = getattr(EventType, enum_ref.group(1), None)
        if member is not None:
            return member.value
    return None


def _dispatched_message_types() -> set[str]:
    """Extract the msg_type branches the gateway's WS dispatcher acts on.

    The dispatcher compares ``msg_type`` in two interchangeable styles:

      * string literals — ``msg_type == "hello"``, ``msg_type in ("abort", ...)``;
      * enum-derived     — ``msg_type == EventType.PING.value``,
        ``msg_type in ("abort", EventType.MESSAGE_ABORT.value)``.

    Recognising only the first style would let a branch written purely in the
    second (as ``ping``/``pong`` already are) drift past this lockstep — a
    classified method could go unregistered and surface only as a runtime
    permission error. So every ``EventType.<NAME>.value`` operand is resolved
    through the enum to its wire value and considered alongside the literals.

    Within a single ``in (...)`` branch the operands are *aliases* for one
    dispatch path (``"abort"`` and ``EventType.MESSAGE_ABORT.value`` route to
    the same handler). The registry classifies the canonical name, so each
    branch contributes one representative — the literal if present, else the
    resolved enum value — rather than every alias as a distinct method.
    """
    source = _SERVER.read_text()
    found: set[str] = set()

    for token in re.findall(rf"msg_type == ({_OPERAND})", source):
        resolved = _resolve_operand(token)
        if resolved is not None:
            found.add(resolved)

    for group in re.findall(r"msg_type in \(([^)]*)\)", source):
        operands = [_resolve_operand(t) for t in re.findall(_OPERAND, group)]
        resolved = [o for o in operands if o is not None]
        if not resolved:
            continue
        literals = [
            re.fullmatch(r'"([a-z_.]+)"', t).group(1)
            for t in re.findall(_OPERAND, group)
            if re.fullmatch(r'"[a-z_.]+"', t)
        ]
        found.add(literals[0] if literals else resolved[0])

    return found - _TRANSPORT_TYPES


@pytest.mark.skipif(not _SERVER.exists(), reason="praisonai-bot not present in this checkout")
def test_the_dispatcher_handles_types_this_test_can_see():
    """Positive control: if the extraction breaks, every other test here passes vacuously."""
    types = _dispatched_message_types()
    assert len(types) >= 4, f"extraction found only {types}; the regex has drifted from the source"
    assert "message" in types, "the most basic message type was not extracted"
    # ``abort`` is dispatched via a mixed-style branch
    # (``msg_type in ("abort", EventType.MESSAGE_ABORT.value)``); seeing it
    # proves the enum-derived operand resolution works, so a future branch
    # written enum-only cannot silently drift past this lockstep.
    assert "abort" in types, "the enum-derived branch resolution has drifted from the source"


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
