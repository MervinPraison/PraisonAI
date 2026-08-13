"""Tests for WhatsApp LID<->phone identity canonicalization (Issue #3886).

WhatsApp surfaces the same person as either "<lid>@lid" or
"<phone>@s.whatsapp.net". Keying identity on the raw form splits one user into
two principals, breaking the DM allowlist, session/memory continuity and
pairing. These tests verify the adapter's canonicalizer reconciles both forms
to one stable phone identity, and fails open when no mapping is known.
"""

import pytest

from praisonai_bot.bots.whatsapp import WhatsAppIdentityCanonicalizer
from praisonaiagents.gateway import IdentityCanonicalizerProtocol


def test_conforms_to_core_protocol():
    assert isinstance(WhatsAppIdentityCanonicalizer(), IdentityCanonicalizerProtocol)


def test_unknown_lid_returns_unchanged_fail_open():
    c = WhatsAppIdentityCanonicalizer()
    assert c.canonicalize("whatsapp", "999123@lid") == "999123@lid"


def test_phone_form_is_never_altered():
    c = WhatsAppIdentityCanonicalizer()
    assert (
        c.canonicalize("whatsapp", "15551234567@s.whatsapp.net")
        == "15551234567@s.whatsapp.net"
    )


def test_lid_canonicalizes_to_phone_after_learning_from_sender_alt():
    c = WhatsAppIdentityCanonicalizer()
    # LID sender arrives with phone form in SenderAlt.
    c.learn("999123@lid", "15551234567@s.whatsapp.net")
    assert (
        c.canonicalize("whatsapp", "999123@lid") == "15551234567@s.whatsapp.net"
    )


def test_learn_handles_reversed_order_phone_sender_lid_alt():
    c = WhatsAppIdentityCanonicalizer()
    # Phone sender arrives with LID form in SenderAlt.
    c.learn("15551234567@s.whatsapp.net", "999123@lid")
    assert (
        c.canonicalize("whatsapp", "999123@lid") == "15551234567@s.whatsapp.net"
    )


def test_both_forms_resolve_to_same_canonical_identity():
    c = WhatsAppIdentityCanonicalizer()
    c.learn("999123@lid", "15551234567@s.whatsapp.net")
    lid_id = c.canonicalize("whatsapp", "999123@lid")
    phone_id = c.canonicalize("whatsapp", "15551234567@s.whatsapp.net")
    assert lid_id == phone_id == "15551234567@s.whatsapp.net"


def test_lid_with_device_suffix_is_reconciled():
    c = WhatsAppIdentityCanonicalizer()
    c.learn("999123@lid", "15551234567@s.whatsapp.net")
    assert (
        c.canonicalize("whatsapp", "999123:12@lid")
        == "15551234567@s.whatsapp.net"
    )


@pytest.mark.parametrize("bad", ["", None])
def test_learn_ignores_missing_inputs(bad):
    c = WhatsAppIdentityCanonicalizer()
    c.learn(bad, "15551234567@s.whatsapp.net")
    c.learn("999123@lid", bad)
    assert c.canonicalize("whatsapp", "999123@lid") == "999123@lid"


def test_canonicalize_handles_empty_input():
    c = WhatsAppIdentityCanonicalizer()
    assert c.canonicalize("whatsapp", "") == ""


def test_learn_rejects_non_phone_alternate_domain():
    # A group/broadcast alt-JID must never be learned as a phone identity.
    c = WhatsAppIdentityCanonicalizer()
    c.learn("999123@lid", "120363000000000000@g.us")
    assert c.canonicalize("whatsapp", "999123@lid") == "999123@lid"


def test_learn_rejects_unknown_alternate_domain():
    c = WhatsAppIdentityCanonicalizer()
    c.learn("999123@lid", "15551234567@hostile.example")
    assert c.canonicalize("whatsapp", "999123@lid") == "999123@lid"


def test_canonicalize_ignores_malformed_lid_suffix():
    # ``@lid-extra`` is a different (malformed) domain and must pass through.
    c = WhatsAppIdentityCanonicalizer()
    c.learn("999123@lid", "15551234567@s.whatsapp.net")
    assert c.canonicalize("whatsapp", "999123@lid-extra") == "999123@lid-extra"


def test_learn_rejects_lid_to_lid_pairing():
    c = WhatsAppIdentityCanonicalizer()
    c.learn("999123@lid", "888777@lid")
    assert c.canonicalize("whatsapp", "999123@lid") == "999123@lid"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
