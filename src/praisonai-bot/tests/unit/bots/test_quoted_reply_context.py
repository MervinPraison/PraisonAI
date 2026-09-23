"""Tests for quoted-reply context resolution (Issue #5223).

When a user taps *Reply* or quotes an earlier message, the referenced content
must reach the agent as a quoted block so it can honour the referent ("do the
second one") instead of answering context-blind. These tests cover the
Telegram inbound resolver and the core prompt-rendering helper.
"""

from types import SimpleNamespace

from praisonaiagents.bots import BotMessage, QuotedRef
from praisonai_bot.bots._protocol_mixin import MessageHookMixin
from praisonai_bot.bots.telegram import _resolve_quoted_ref


def _bot(bot_id="42"):
    return SimpleNamespace(_bot_user=SimpleNamespace(user_id=bot_id))


def _update(*, reply_text=None, reply_caption=None, reply_from_id=None,
            reply_msg_id="9", quote_text=None):
    replied = None
    if reply_text is not None or reply_caption is not None or reply_from_id is not None:
        replied = SimpleNamespace(
            message_id=reply_msg_id,
            text=reply_text,
            caption=reply_caption,
            from_user=SimpleNamespace(id=reply_from_id) if reply_from_id else None,
        )
    quote = SimpleNamespace(text=quote_text) if quote_text is not None else None
    message = SimpleNamespace(reply_to_message=replied, quote=quote)
    return SimpleNamespace(message=message)


def test_resolves_bot_reply_text():
    ref = _resolve_quoted_ref(
        _update(reply_text="Here are three options: 1) a  2) b  3) c",
                reply_from_id="42"),
        _bot(),
    )
    assert ref is not None
    assert ref.author == "bot"
    assert ref.text.startswith("Here are three options")
    assert ref.message_id == "9"


def test_resolves_peer_reply_text():
    ref = _resolve_quoted_ref(
        _update(reply_text="the earlier peer message", reply_from_id="7"),
        _bot(),
    )
    assert ref is not None
    assert ref.author == "user"


def test_prefers_explicit_quote_span():
    ref = _resolve_quoted_ref(
        _update(reply_text="full message", reply_from_id="7",
                quote_text="selected span"),
        _bot(),
    )
    assert ref is not None
    assert ref.text == "selected span"


def test_uses_caption_when_no_text():
    ref = _resolve_quoted_ref(
        _update(reply_caption="a photo caption", reply_from_id="7"),
        _bot(),
    )
    assert ref is not None
    assert ref.text == "a photo caption"


def test_no_reply_returns_none():
    assert _resolve_quoted_ref(_update(), _bot()) is None


def test_malformed_update_degrades_to_none():
    assert _resolve_quoted_ref(SimpleNamespace(message=None), _bot()) is None


def test_prompt_text_renders_quoted_block():
    msg = BotMessage(
        content="do the second one",
        quoted=QuotedRef(text="Here are three options: 1) a  2) b  3) c",
                         author="bot"),
    )
    out = msg.prompt_text
    assert out.startswith('[In reply to: "Here are three options')
    assert out.endswith("do the second one")


def test_prompt_text_no_quote_is_plain_text():
    assert BotMessage(content="hello").prompt_text == "hello"


def test_prompt_text_empty_quote_ignored():
    msg = BotMessage(content="hello", quoted=QuotedRef(text="   "))
    assert msg.prompt_text == "hello"


def test_botmessage_quoted_roundtrips_through_dict():
    msg = BotMessage(
        content="x",
        quoted=QuotedRef(message_id="9", text="quoted", author="bot"),
    )
    restored = BotMessage.from_dict(msg.to_dict())
    assert restored.quoted is not None
    assert restored.quoted.message_id == "9"
    assert restored.quoted.text == "quoted"
    assert restored.quoted.author == "bot"


# ── MESSAGE_RECEIVED hook boundary (Issue #5223 review) ─────────────────────
# Quoted context must pass through the same inbound gate as ordinary content:
# a redaction/deny hook has to be able to inspect and veto quoted text too.


class _StubOutput:
    def __init__(self, blocked=False, modified=None):
        self.blocked = blocked
        self.modified_input = modified


class _StubResult:
    def __init__(self, output):
        self.output = output


class _StubRunner:
    """Records the content the hook saw and replays a scripted decision."""

    def __init__(self, *, block=False, redact_to=None):
        self.block = block
        self.redact_to = redact_to
        self.seen_content = None

    def execute_sync(self, event, event_input):
        self.seen_content = event_input.content
        out = _StubOutput(
            blocked=self.block,
            modified=({"content": self.redact_to}
                      if self.redact_to is not None else None),
        )
        return [_StubResult(out)]

    def is_blocked(self, results):
        return any(getattr(r.output, "blocked", False) for r in results)


class _Host(MessageHookMixin):
    platform = "telegram"

    def __init__(self, runner):
        self._agent = SimpleNamespace(_hook_runner=runner, agent_name="bot")


def _quoted_msg():
    return BotMessage(
        content="do the second one",
        quoted=QuotedRef(text="secret: hunter2", author="bot"),
    )


def test_hook_sees_quoted_text_in_content():
    runner = _StubRunner()
    host = _Host(runner)
    host.fire_message_received(_quoted_msg())
    # The rendered turn (content + quoted block) was exposed to the hook.
    assert "secret: hunter2" in runner.seen_content
    assert "do the second one" in runner.seen_content


def test_hook_can_drop_message_with_quoted_secret():
    host = _Host(_StubRunner(block=True))
    result = host.fire_message_received(_quoted_msg())
    assert result["drop"] is True


def test_hook_redaction_clears_quoted_ref():
    host = _Host(_StubRunner(redact_to="[REDACTED]"))
    msg = _quoted_msg()
    result = host.fire_message_received(msg)
    # Redacted content is authoritative; the separately-resolved quote is
    # dropped so unredacted quoted text cannot be re-appended post-hook.
    assert result["content"] == "[REDACTED]"
    assert msg.quoted is None
    assert msg.prompt_text == "[REDACTED]"


def test_no_quote_leaves_plain_content_to_hook():
    runner = _StubRunner()
    host = _Host(runner)
    host.fire_message_received(BotMessage(content="hello"))
    assert runner.seen_content == "hello"
