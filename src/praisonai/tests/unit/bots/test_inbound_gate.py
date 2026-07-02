"""Unit tests for the inbound MESSAGE_RECEIVED gating hook.

Verifies that ``MessageHookMixin.fire_message_received`` returns an inbound
gate decision (``drop``/``content``) symmetric with the outbound
``fire_message_sending`` control point, so a hook/plugin can drop or redact an
incoming message before it reaches the agent.
"""

from types import SimpleNamespace

import pytest

from praisonai.bots._protocol_mixin import MessageHookMixin


class _Host(MessageHookMixin):
    """Minimal host exposing the attributes the mixin expects."""

    platform = "test"

    def __init__(self, runner):
        self._runner = runner
        self._agent = SimpleNamespace(agent_name="bot")

    def _get_hook_runner(self):
        return self._runner


class _FakeResult:
    def __init__(self, modified_data=None):
        self.output = SimpleNamespace(modified_data=modified_data)


class _FakeRunner:
    """Fake HookRunner honouring only the surface the mixin touches."""

    def __init__(self, *, blocked=False, results=None):
        self._blocked = blocked
        self._results = results or []

    def execute_sync(self, event, event_input):
        return self._results

    def is_blocked(self, results):
        return self._blocked


def _make_message(content="hello"):
    return SimpleNamespace(
        content=content,
        sender=SimpleNamespace(user_id="u1"),
        channel=SimpleNamespace(channel_id="c1", channel_type="dm"),
        message_id="m1",
    )


def test_no_runner_returns_passthrough():
    host = _Host(runner=None)
    msg = _make_message("hi")
    decision = host.fire_message_received(msg)
    assert decision == {"content": "hi", "drop": False}


def test_hook_deny_drops_message():
    host = _Host(runner=_FakeRunner(blocked=True))
    msg = _make_message("spam")
    decision = host.fire_message_received(msg)
    assert decision["drop"] is True


def test_hook_redacts_content():
    results = [_FakeResult(modified_data={"content": "[REDACTED]"})]
    host = _Host(runner=_FakeRunner(blocked=False, results=results))
    msg = _make_message("my ssn is 123-45-6789")
    decision = host.fire_message_received(msg)
    assert decision["drop"] is False
    assert decision["content"] == "[REDACTED]"
    # message.content is rewritten in place for adapters that ignore the return
    assert msg.content == "[REDACTED]"


def test_hook_passthrough_when_no_modification():
    results = [_FakeResult(modified_data=None)]
    host = _Host(runner=_FakeRunner(blocked=False, results=results))
    msg = _make_message("unchanged")
    decision = host.fire_message_received(msg)
    assert decision == {"content": "unchanged", "drop": False}
    assert msg.content == "unchanged"


def test_hook_error_is_non_fatal():
    class _Boom(_FakeRunner):
        def execute_sync(self, event, event_input):
            raise RuntimeError("boom")

    host = _Host(runner=_Boom())
    msg = _make_message("still delivered")
    decision = host.fire_message_received(msg)
    assert decision == {"content": "still delivered", "drop": False}
