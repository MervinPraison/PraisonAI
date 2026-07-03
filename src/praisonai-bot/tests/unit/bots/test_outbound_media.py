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
