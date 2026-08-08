"""Tests for creation-time delivery-target preview / validation (Issue #3800).

Covers the core, dependency-free seam: ``DeliveryTarget.preview`` renders the
resolved destination, and ``DeliveryValidation`` / ``ScheduleTargetError``
carry an actionable pre-flight result so an unroutable target is caught the
moment a scheduled/agent-initiated send is created, not only at fire time.
"""

import pytest

from praisonaiagents.gateway import DeliveryValidation, ScheduleTargetError
from praisonaiagents.scheduler import DeliveryTarget


def test_preview_explicit_channel_and_id():
    t = DeliveryTarget.parse("telegram:@alice")
    assert t.preview() == "telegram:@alice"


def test_preview_channel_id_thread():
    t = DeliveryTarget.parse("telegram:123:789")
    assert t.preview() == "telegram:123:789"


def test_preview_bare_platform():
    t = DeliveryTarget.parse("telegram")
    assert t.preview() == "telegram"


def test_preview_symbolic_tokens():
    assert DeliveryTarget.parse("origin").preview() == "origin"
    assert DeliveryTarget.parse("all").preview() == "all"


def test_preview_session_target_appended():
    t = DeliveryTarget.parse("telegram:@alice")
    assert t.preview(session_target="main") == "telegram:@alice (session main)"


def test_delivery_validation_ok_defaults():
    v = DeliveryValidation(ok=True, preview="telegram:@alice")
    assert v.ok is True
    assert v.reason == ""
    assert v.hint == ""
    assert v.preview == "telegram:@alice"


def test_delivery_validation_frozen():
    v = DeliveryValidation(ok=True)
    with pytest.raises(Exception):
        v.ok = False  # type: ignore[misc]


def test_schedule_target_error_composes_message():
    err = ScheduleTargetError(
        "channel 'telegramm' is not configured",
        "Configured: telegram, slack.",
    )
    assert err.reason == "channel 'telegramm' is not configured"
    assert err.hint == "Configured: telegram, slack."
    assert "telegramm" in str(err)
    assert "Configured: telegram, slack." in str(err)
    assert isinstance(err, ValueError)


def test_schedule_target_error_without_hint():
    err = ScheduleTargetError("unroutable target")
    assert str(err) == "unroutable target"
