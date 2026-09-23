"""Tests for the inbound platform-event core contract (Issue #5161).

Reactions, edits, deletions, membership changes and thread lifecycle are
delivered by the platform SDK but were previously dropped before reaching the
agent or a hook. These tests pin the new shared *core* contract:

  * the six new ``HookEvent`` members exist and are distinct
  * the normalised ``PlatformEvent`` / ``PlatformEventInput`` payloads round-trip

The wrapper's emission seam (``MessageHookMixin.fire_platform_event``) is
covered by the praisonai-bot test suite, which owns the adapter layer.
"""

import pytest

from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.hooks.events import PlatformEventInput
from praisonaiagents.bots import PlatformEvent


NEW_EVENTS = [
    "REACTION_RECEIVED",
    "MESSAGE_EDITED",
    "MESSAGE_DELETED",
    "MEMBER_JOINED",
    "MEMBER_LEFT",
    "THREAD_CREATED",
]


@pytest.mark.parametrize("name", NEW_EVENTS)
def test_new_hook_events_exist(name):
    assert hasattr(HookEvent, name)


def test_new_hook_events_are_distinct():
    values = {getattr(HookEvent, n).value for n in NEW_EVENTS}
    assert len(values) == len(NEW_EVENTS)


def test_platform_event_to_dict_omits_raw():
    evt = PlatformEvent(
        kind="reaction_added",
        platform="discord",
        chat_id="c1",
        user_id="u1",
        message_id="m1",
        emoji="✅",
        raw={"native": object()},
    )
    d = evt.to_dict()
    assert d["kind"] == "reaction_added"
    assert d["emoji"] == "✅"
    assert "raw" not in d


def test_platform_event_input_serialises_fields():
    inp = PlatformEventInput(
        session_id="",
        cwd=".",
        event_name=HookEvent.MESSAGE_EDITED,
        timestamp="0",
        kind="message_edited",
        platform="discord",
        chat_id="c1",
        user_id="u1",
        message_id="m1",
        new_text="corrected question",
    )
    d = inp.to_dict()
    assert d["kind"] == "message_edited"
    assert d["new_text"] == "corrected question"
    assert d["event_name"] == "message_edited"
