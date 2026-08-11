"""Issue #2388 — outbound media delivery-path safety guard.

Verifies ``validate_media_delivery_path`` blocks credential/system locations a
prompt injection might name for exfiltration, while admitting legitimate
agent-produced files; and that strict mode enforces allowlist/mtime windows.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from praisonai_bot.bots._outbound_media import (
    MediaDeliveryError,
    OutboundMediaPolicy,
    deliver_media_to_adapter,
    validate_media_delivery_path,
)


def test_valid_file_passes(tmp_path):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 data")
    safe = validate_media_delivery_path(str(f))
    assert safe == str(f.resolve())


def test_missing_file_rejected(tmp_path):
    with pytest.raises(MediaDeliveryError, match="not found"):
        validate_media_delivery_path(str(tmp_path / "nope.bin"))


def test_directory_rejected(tmp_path):
    with pytest.raises(MediaDeliveryError, match="not a regular file"):
        validate_media_delivery_path(str(tmp_path))


def test_empty_path_rejected():
    with pytest.raises(MediaDeliveryError):
        validate_media_delivery_path("   ")


def test_url_rejected():
    with pytest.raises(MediaDeliveryError, match="non-local"):
        validate_media_delivery_path("https://evil.example/secret")


def test_system_dir_denied():
    with pytest.raises(MediaDeliveryError, match="protected location"):
        validate_media_delivery_path("/etc/passwd")


def test_home_secret_dir_denied(tmp_path, monkeypatch):
    # Point HOME at a temp dir containing a fake ~/.ssh/id_rsa.
    fake_home = tmp_path / "home"
    ssh = fake_home / ".ssh"
    ssh.mkdir(parents=True)
    key = ssh / "id_rsa"
    key.write_text("PRIVATE KEY")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(fake_home)))

    with pytest.raises(MediaDeliveryError, match="protected location"):
        validate_media_delivery_path(str(key))


def test_symlink_to_secret_denied(tmp_path):
    # A symlink that points into /etc must be rejected after resolution.
    link = tmp_path / "innocent.txt"
    try:
        os.symlink("/etc/hostname", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    with pytest.raises(MediaDeliveryError, match="protected location"):
        validate_media_delivery_path(str(link))


def test_size_cap_enforced(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"0" * 1024)
    policy = OutboundMediaPolicy(max_bytes=512)
    with pytest.raises(MediaDeliveryError, match="exceeds"):
        validate_media_delivery_path(str(f), policy=policy)


def test_strict_rejects_outside_allow_roots(tmp_path):
    f = tmp_path / "out.bin"
    f.write_bytes(b"x")
    # Stale mtime so the recent-window does not rescue it.
    old = 0
    os.utime(f, (old, old))
    policy = OutboundMediaPolicy(
        strict=True, allow_roots=[str(tmp_path / "allowed")], recent_mtime_seconds=1
    )
    with pytest.raises(MediaDeliveryError, match="strict policy"):
        validate_media_delivery_path(str(f), policy=policy)


def test_strict_accepts_under_allow_root(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    f = root / "ok.bin"
    f.write_bytes(b"x")
    policy = OutboundMediaPolicy(strict=True, allow_roots=[str(root)])
    assert validate_media_delivery_path(str(f), policy=policy) == str(f.resolve())


def test_strict_accepts_recent_file(tmp_path):
    f = tmp_path / "fresh.bin"
    f.write_bytes(b"x")  # mtime ~ now
    policy = OutboundMediaPolicy(
        strict=True, allow_roots=[], recent_mtime_seconds=3600
    )
    assert validate_media_delivery_path(str(f), policy=policy) == str(f.resolve())


def test_policy_from_dict():
    p = OutboundMediaPolicy.from_dict(
        {"strict": True, "allow_roots": "/srv/out", "max_bytes": 100}
    )
    assert p.strict is True
    assert p.allow_roots == ["/srv/out"]
    assert p.max_bytes == 100


def test_deliver_via_adapter_send_media_hook(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls = []

    class Adapter:
        platform = "telegram"

        async def send_media(self, channel_id, path, caption=None):
            calls.append((channel_id, path, caption))

    ok = asyncio.run(
        deliver_media_to_adapter(Adapter(), "42", str(f), caption="hi")
    )
    assert ok is True
    assert calls == [("42", str(f), "hi")]


def test_deliver_threads_media_hook_into_thread(tmp_path):
    # A resolved thread_id is forwarded to a thread-aware adapter hook so a
    # threaded target delivers the attachment into the thread (parity with text).
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls = []

    class Adapter:
        platform = "telegram"

        async def send_media(self, channel_id, path, caption=None, thread_id=None):
            calls.append((channel_id, path, caption, thread_id))

    ok = asyncio.run(
        deliver_media_to_adapter(
            Adapter(), "42", str(f), caption="hi", thread_id="789"
        )
    )
    assert ok is True
    assert calls == [("42", str(f), "hi", "789")]


def test_deliver_thread_ignored_for_hook_without_thread_param(tmp_path):
    # An adapter hook lacking ``thread_id`` is unaffected by a threaded target:
    # it is called without the kwarg (no TypeError, no behaviour change).
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls = []

    class Adapter:
        platform = "telegram"

        async def send_media(self, channel_id, path, caption=None):
            calls.append((channel_id, path, caption))

    ok = asyncio.run(
        deliver_media_to_adapter(
            Adapter(), "42", str(f), caption="hi", thread_id="789"
        )
    )
    assert ok is True
    assert calls == [("42", str(f), "hi")]


def test_deliver_telegram_media_uses_message_thread_id(tmp_path):
    # Telegram forum-topic thread is addressed via ``message_thread_id``.
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    photo_calls = []

    class _Bot:
        async def send_photo(self, chat_id, photo, caption=None, message_thread_id=None):
            photo_calls.append((chat_id, caption, message_thread_id))

    class _App:
        bot = _Bot()

    class Adapter:
        platform = "telegram"
        _application = _App()

    ok = asyncio.run(
        deliver_media_to_adapter(
            Adapter(), "-100123", str(f), caption="cap", thread_id="789"
        )
    )
    assert ok is True
    assert photo_calls == [(-100123, "cap", 789)]


def test_deliver_returns_false_when_no_primitive(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"x")

    class Adapter:
        platform = "mystery"

    ok = asyncio.run(deliver_media_to_adapter(Adapter(), "1", str(f)))
    assert ok is False


def test_dotenv_basename_denied(tmp_path):
    # A project-local .env outside ~ must still be rejected (exfil guard).
    f = tmp_path / ".env"
    f.write_text("API_KEY=secret")
    with pytest.raises(MediaDeliveryError, match="protected file"):
        validate_media_delivery_path(str(f))


def test_ssh_key_basename_denied(tmp_path):
    f = tmp_path / "id_rsa"
    f.write_text("PRIVATE KEY")
    with pytest.raises(MediaDeliveryError, match="protected file"):
        validate_media_delivery_path(str(f))


def test_policy_from_dict_quoted_false_disables():
    # bool("false") is True in Python; quoted config must still disable.
    p = OutboundMediaPolicy.from_dict({"enabled": "false", "strict": "no"})
    assert p.enabled is False
    assert p.strict is False


def test_policy_from_dict_quoted_true_enables():
    p = OutboundMediaPolicy.from_dict({"enabled": "true", "strict": "on"})
    assert p.enabled is True
    assert p.strict is True


def test_send_media_hook_without_caption_param(tmp_path):
    # An adapter hook lacking ``caption`` is called once, positionally.
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls = []

    class Adapter:
        platform = "telegram"

        async def send_media(self, channel_id, path):
            calls.append((channel_id, path))

    ok = asyncio.run(
        deliver_media_to_adapter(Adapter(), "42", str(f), caption="hi")
    )
    assert ok is True
    assert calls == [("42", str(f))]


def test_telegram_chat_id_preserves_username():
    from praisonai_bot.bots._outbound_media import _telegram_chat_id

    assert _telegram_chat_id("123") == 123
    assert _telegram_chat_id("-100123") == -100123
    assert _telegram_chat_id("@channelusername") == "@channelusername"


# ── Issue #3184: media upload gets the same retry/backoff as text ─────────


def _media_router(adapter):
    """Build a DeliveryRouter over a fake BotOS wrapping ``adapter``."""
    from praisonai_bot.bots.delivery import DeliveryRouter

    class FakeBotOS:
        def get_bot(self, platform):
            return adapter if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}
    return router


def test_send_media_retries_transient_upload_failure(tmp_path, monkeypatch):
    # A transient upload error is retried with backoff (like text) and finally
    # delivered, instead of being dropped on the first blip.
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 data")

    class Adapter:
        platform = "telegram"
        # Fast backoff so the test does not actually sleep.
        from praisonai_bot.bots._resilience import BackoffPolicy

        _outbound_backoff = BackoffPolicy(initial_ms=1, max_ms=2, max_attempts=3)

        def __init__(self):
            self.calls = 0

        async def send_media(self, channel_id, path, caption=None):
            self.calls += 1
            if self.calls < 3:
                raise ConnectionError("connection reset")

    adapter = Adapter()
    router = _media_router(adapter)

    ok = asyncio.run(router.send_media("telegram:42", str(f)))

    assert ok is True
    assert adapter.calls == 3


def test_send_media_gives_up_after_max_attempts(tmp_path):
    # A persistently failing transient upload eventually returns False (not an
    # unhandled crash) after the attempt budget is spent.
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 data")

    class Adapter:
        platform = "telegram"
        from praisonai_bot.bots._resilience import BackoffPolicy

        _outbound_backoff = BackoffPolicy(initial_ms=1, max_ms=2, max_attempts=2)

        def __init__(self):
            self.calls = 0

        async def send_media(self, channel_id, path, caption=None):
            self.calls += 1
            raise ConnectionError("connection reset")

    adapter = Adapter()
    router = _media_router(adapter)

    ok = asyncio.run(router.send_media("telegram:42", str(f)))

    assert ok is False
    assert adapter.calls == 2


def test_send_media_no_primitive_returns_false_without_retry(tmp_path):
    # An adapter exposing no upload primitive returns False cleanly and is not
    # retried (nothing transient to recover from).
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 data")

    class Adapter:
        platform = "telegram"

    router = _media_router(Adapter())

    ok = asyncio.run(router.send_media("telegram:42", str(f)))

    assert ok is False


def test_discord_media_transient_error_propagates_for_retry(tmp_path):
    # The Discord native path must let a transient ``channel.send`` error
    # propagate so ``deliver_with_retry`` can back off and retry it — the same
    # resilience text and the other transports get. Previously it swallowed the
    # exception into ``False`` on the first blip, silently dropping the file.
    pytest.importorskip("discord")

    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 data")

    class _Channel:
        def __init__(self):
            self.calls = 0

        async def send(self, *args, **kwargs):
            self.calls += 1
            if self.calls < 2:
                raise ConnectionError("connection reset")

    class _Client:
        def __init__(self, channel):
            self._channel = channel

        def get_channel(self, _id):
            return self._channel

    channel = _Channel()

    class Adapter:
        platform = "discord"
        _client = _Client(channel)

    async def _run():
        return await deliver_media_to_adapter(Adapter(), "42", str(f))

    # First call raises (propagates, is NOT swallowed into False)…
    with pytest.raises(ConnectionError):
        asyncio.run(_run())
    assert channel.calls == 1
    # …and a retry succeeds.
    ok = asyncio.run(_run())
    assert ok is True
    assert channel.calls == 2
