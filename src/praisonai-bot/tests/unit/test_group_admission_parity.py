"""Cross-channel group admission parity via the core primitive (Issue #5908)."""

from types import SimpleNamespace

import pytest

from praisonaiagents.bots.admission import MentionFacts
from praisonai_bot.bots._group_policy import decide_group_admission


def _admit(chat_type="group", explicit=False, reply_to_bot=False, is_command=False, **cfg):
    return decide_group_admission(
        SimpleNamespace(**cfg),
        chat_type=chat_type,
        mention=MentionFacts(explicit=explicit, reply_to_bot=reply_to_bot),
        is_command=is_command,
    )


def test_dm_always_admitted():
    assert _admit(chat_type="dm", group_policy="command_only").admit
    assert _admit(chat_type="im", group_policy="command_only").admit


def test_mention_only_admits_explicit_and_reply_to_bot():
    cfg = dict(group_policy="mention_only", mention_required=True)
    assert _admit(explicit=True, **cfg).admit
    assert _admit(reply_to_bot=True, **cfg).admit
    decision = _admit(**cfg)
    assert not decision.admit
    assert decision.reason_code == "group_mention_only"


def test_command_only_drops_mentions():
    # Gateway sets mention_required=False for command_only; it must not open
    # the gate to all group traffic.
    cfg = dict(group_policy="command_only", mention_required=False)
    assert not _admit(explicit=True, **cfg).admit
    assert _admit(is_command=True, **cfg).admit


def test_observe_flags_passive_record():
    decision = _admit(group_policy="observe", mention_required=False)
    assert not decision.admit and decision.observe


def test_legacy_mention_required_false_responds_all():
    assert _admit(group_policy="mention_only", mention_required=False).admit


@pytest.mark.parametrize("policy", [None, "bogus"])
def test_unset_or_unknown_policy_fails_safe(policy):
    assert not _admit(group_policy=policy).admit
