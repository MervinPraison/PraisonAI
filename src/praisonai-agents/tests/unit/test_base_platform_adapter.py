"""
Unit tests for BasePlatformAdapter — the inheritable channel adapter base.
"""

import asyncio

import pytest

from praisonaiagents.bots import (
    BasePlatformAdapter,
    PlatformCapabilities,
    SendResult,
)


class RecordingBot(BasePlatformAdapter):
    """Minimal adapter that records sends for assertions."""

    capabilities = PlatformCapabilities(
        max_message_length=20,
        supports_edit=True,
        supports_typing=True,
    )

    def __init__(self, fail_times: int = 0, retry_after=None):
        self.sends = []
        self.typing_calls = 0
        self.connected = False
        self._fail_times = fail_times
        self._retry_after = retry_after
        self._counter = 0

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        self.connected = True
        return True

    async def disconnect(self) -> None:
        self.connected = False

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        if self._fail_times > 0:
            self._fail_times -= 1
            return SendResult(
                ok=False, chat_id=chat_id, error="rate_limited",
                retry_after=self._retry_after,
            )
        self._counter += 1
        mid = f"m{self._counter}"
        self.sends.append((chat_id, content, reply_to))
        return SendResult(ok=True, message_id=mid, chat_id=chat_id)

    async def get_chat_info(self, chat_id):
        return {"id": chat_id}

    async def send_typing(self, chat_id):
        self.typing_calls += 1


def run(coro):
    return asyncio.run(coro)


class TestContract:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BasePlatformAdapter()  # type: ignore[abstract]

    def test_default_capabilities(self):
        class Bare(RecordingBot):
            capabilities = PlatformCapabilities()

        bot = Bare()
        assert bot.max_message_length == 4096
        assert bot.supports_typing is True  # default in descriptor
        assert bot.supports_edit is False


class TestDeliver:
    def test_single_short_message(self):
        bot = RecordingBot()
        res = run(bot.deliver("c1", "hello"))
        assert res.ok
        assert res.message_id == "m1"
        assert bot.sends == [("c1", "hello", None)]

    def test_chunking_long_message(self):
        bot = RecordingBot()  # max_message_length=20
        text = "para one here\n\n" + "x" * 45
        res = run(bot.deliver("c1", text))
        assert res.ok
        assert len(res.message_ids) > 1
        assert all(len(c) <= 20 for _, c, _ in bot.sends)

    def test_reply_to_only_first_chunk(self):
        bot = RecordingBot()
        text = "a" * 25 + "\n\n" + "b" * 25
        run(bot.deliver("c1", text, reply_to="r1"))
        reply_targets = [r for _, _, r in bot.sends]
        assert reply_targets[0] == "r1"
        assert all(r is None for r in reply_targets[1:])

    def test_typing_called_when_supported(self):
        bot = RecordingBot()
        run(bot.deliver("c1", "hi"))
        assert bot.typing_calls == 1

    def test_typing_skipped_when_unsupported(self):
        class NoTyping(RecordingBot):
            capabilities = PlatformCapabilities(supports_typing=False)

        bot = NoTyping()
        run(bot.deliver("c1", "hi"))
        assert bot.typing_calls == 0

    def test_empty_string_is_noop(self):
        bot = RecordingBot()
        res = run(bot.deliver("c1", ""))
        assert res.ok
        assert bot.sends == []
        assert res.message_ids == []

    def test_dict_content_passthrough(self):
        bot = RecordingBot()
        payload = {"blocks": [1, 2, 3]}
        run(bot.deliver("c1", payload))
        assert bot.sends == [("c1", payload, None)]


class TestRetry:
    def test_retries_then_succeeds(self):
        bot = RecordingBot(fail_times=2, retry_after=0)
        res = run(bot.deliver("c1", "hi"))
        assert res.ok
        assert res.message_id == "m1"

    def test_gives_up_after_max_retries(self):
        bot = RecordingBot(fail_times=99, retry_after=0)
        res = run(bot.deliver("c1", "hi"))
        assert not res.ok
        assert res.error == "rate_limited"

    def test_send_exception_is_retried(self):
        class Flaky(RecordingBot):
            async def send(self, chat_id, content, *, reply_to=None, metadata=None):
                self._counter += 1
                if self._counter == 1:
                    raise RuntimeError("boom")
                return SendResult(ok=True, message_id="ok", chat_id=chat_id)

        bot = Flaky()
        bot.retry_base_delay = 0
        res = run(bot.deliver("c1", "hi"))
        assert res.ok and res.message_id == "ok"


class TestEditDelete:
    def test_edit_not_supported_fallback(self):
        class NoEdit(RecordingBot):
            capabilities = PlatformCapabilities(supports_edit=False)

        bot = NoEdit()
        res = run(bot.edit_message("c1", "m1", "new"))
        assert not res.ok
        assert res.error == "edit_not_supported"

    def test_delete_default_false(self):
        bot = RecordingBot()
        assert run(bot.delete_message("c1", "m1")) is False


class TestFormatting:
    def test_format_message_identity(self):
        bot = RecordingBot()
        assert bot.format_message("abc") == "abc"

    def test_chunk_helper(self):
        bot = RecordingBot()
        chunks = bot.chunk("x" * 55)
        assert all(len(c) <= 20 for c in chunks)


class TestSendResult:
    def test_to_dict(self):
        r = SendResult(ok=True, message_id="m1", chat_id="c1")
        d = r.to_dict()
        assert d["ok"] and d["message_id"] == "m1" and d["chat_id"] == "c1"
