"""Tests for the canonical inbound admission primitive (Issue #3780)."""

from praisonaiagents.bots import IngressDecision, resolve_ingress_admission
from praisonaiagents.bots.admission import (
    GATE_ALLOWLIST,
    GATE_BLOCKLIST,
    GATE_DIRECT,
    GATE_GROUP_POLICY,
    GATE_PAIRING,
    REASON_ALLOWED,
    REASON_BLOCKED,
    REASON_COMMAND_ONLY,
    REASON_GROUP_MENTION_ONLY,
    REASON_NOT_IN_ALLOWLIST,
    REASON_OBSERVE,
    REASON_PAIRING_REQUIRED,
)


def test_direct_message_no_restriction_admits():
    d = resolve_ingress_admission(chat_type="dm", sender_id="u1")
    assert d.admit is True
    assert d.reason_code == REASON_ALLOWED
    assert d.gate == GATE_DIRECT


def test_blocklist_takes_precedence_over_allowlist():
    d = resolve_ingress_admission(
        chat_type="dm",
        sender_id="u1",
        allowlist=["u1"],
        blocklist=["u1"],
    )
    assert d.admit is False
    assert d.reason_code == REASON_BLOCKED
    assert d.gate == GATE_BLOCKLIST


def test_not_in_allowlist_drops():
    d = resolve_ingress_admission(
        chat_type="dm", sender_id="stranger", allowlist=["u1", "u2"]
    )
    assert d.admit is False
    assert d.reason_code == REASON_NOT_IN_ALLOWLIST
    assert d.gate == GATE_ALLOWLIST


def test_empty_allowlist_is_no_restriction():
    d = resolve_ingress_admission(chat_type="dm", sender_id="anyone", allowlist=[])
    assert d.admit is True
    assert d.reason_code == REASON_ALLOWED


def test_allowed_sender_passes_allowlist():
    d = resolve_ingress_admission(
        chat_type="dm", sender_id="u1", allowlist=["u1", "u2"]
    )
    assert d.admit is True


def test_unpaired_sender_requires_pairing():
    d = resolve_ingress_admission(chat_type="dm", sender_id="new", paired=False)
    assert d.admit is False
    assert d.reason_code == REASON_PAIRING_REQUIRED
    assert d.gate == GATE_PAIRING


def test_pairing_only_after_allowlist_gate():
    # A blocked/not-allowed sender is dropped before pairing is considered.
    d = resolve_ingress_admission(
        chat_type="dm", sender_id="x", allowlist=["u1"], paired=False
    )
    assert d.reason_code == REASON_NOT_IN_ALLOWLIST


def test_group_respond_all_admits_everything():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="respond_all"
    )
    assert d.admit is True
    assert d.gate == GATE_GROUP_POLICY


def test_group_unset_policy_defaults_to_respond_all():
    d = resolve_ingress_admission(chat_type="group", sender_id="u1")
    assert d.admit is True


def test_group_mention_only_drops_unmentioned():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="mention_only",
        is_mention=False,
    )
    assert d.admit is False
    assert d.reason_code == REASON_GROUP_MENTION_ONLY


def test_group_mention_only_admits_mention():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="mention_only",
        is_mention=True,
    )
    assert d.admit is True


def test_group_mention_only_admits_command():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="mention_only",
        is_command=True,
    )
    assert d.admit is True


def test_group_command_only_drops_non_command():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="command_only",
        is_command=False,
    )
    assert d.admit is False
    assert d.reason_code == REASON_COMMAND_ONLY


def test_group_command_only_admits_command():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="command_only",
        is_command=True,
    )
    assert d.admit is True


def test_group_observe_records_unmentioned_without_run():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="observe",
        is_mention=False,
    )
    assert d.admit is False
    assert d.observe is True
    assert d.reason_code == REASON_OBSERVE


def test_group_observe_admits_when_mentioned():
    d = resolve_ingress_admission(
        chat_type="group", sender_id="u1", group_policy="observe",
        is_mention=True,
    )
    assert d.admit is True
    assert d.observe is False


def test_private_chat_type_bypasses_group_policy():
    # A restrictive group_policy must not apply to a private/DM chat.
    d = resolve_ingress_admission(
        chat_type="private", sender_id="u1", group_policy="command_only",
        is_command=False,
    )
    assert d.admit is True
    assert d.gate == GATE_DIRECT


def test_decision_is_frozen():
    d = resolve_ingress_admission(chat_type="dm", sender_id="u1")
    assert isinstance(d, IngressDecision)
    try:
        d.admit = False  # type: ignore[misc]
    except Exception as exc:  # frozen dataclass raises FrozenInstanceError
        assert "cannot assign" in str(exc).lower() or True
    else:
        raise AssertionError("IngressDecision should be frozen")


def test_deterministic_same_inputs_same_output():
    kwargs = dict(
        chat_type="group", sender_id="u1", group_policy="mention_only",
        is_mention=False,
    )
    assert resolve_ingress_admission(**kwargs) == resolve_ingress_admission(**kwargs)
