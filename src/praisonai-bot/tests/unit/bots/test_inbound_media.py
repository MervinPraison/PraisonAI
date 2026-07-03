"""Inbound media handling for gateway bots (Issue #2350).

Verifies the shared ``cache_inbound_media`` helper (size cap, magic-byte
validation, SSRF guard) and that ``BotSessionManager.chat()`` threads inbound
media paths through to ``agent.chat(prompt, attachments=...)`` so the agent's
existing vision capability can act on user-sent photos/documents.
"""

from __future__ import annotations

import os

import pytest

from praisonai_bot.bots._media import (
    cache_inbound_media,
    InboundMediaError,
    _is_safe_url,
    resolve_max_inbound_media_bytes,
    DEFAULT_MAX_INBOUND_MEDIA_BYTES,
)
from praisonai_bot.bots._session import BotSessionManager


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_cache_image_bytes_writes_validated_file():
    path = cache_inbound_media(PNG, kind="image")
    try:
        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read() == PNG
    finally:
        os.remove(path)


def test_cache_rejects_wrong_magic_bytes():
    with pytest.raises(InboundMediaError):
        cache_inbound_media(b"this is not an image" * 4, kind="image")


def test_cache_enforces_size_cap():
    with pytest.raises(InboundMediaError):
        cache_inbound_media(PNG, kind="image", max_bytes=4)


def test_document_kind_skips_magic_gate():
    path = cache_inbound_media(b"%PDF-1.4 hello", kind="document", filename="a.pdf")
    try:
        assert path.endswith(".pdf")
    finally:
        os.remove(path)


def test_ssrf_guard_blocks_private_and_non_http():
    assert not _is_safe_url("http://127.0.0.1/secret")
    assert not _is_safe_url("http://localhost/secret")
    assert not _is_safe_url("file:///etc/passwd")
    assert not _is_safe_url("http://169.254.169.254/latest/meta-data")


def test_riff_wav_does_not_pass_image_validator():
    # A WAV is a RIFF container (tag "WAVE"); it must not be cached as an image.
    wav = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 16
    with pytest.raises(InboundMediaError):
        cache_inbound_media(wav, kind="image")
    # ...but it should validate as audio.
    path = cache_inbound_media(wav, kind="audio")
    try:
        assert os.path.exists(path)
    finally:
        os.remove(path)


def test_negative_inbound_media_limit_rejected():
    from praisonai_bot.bots._config_schema import ChannelConfigSchema
    with pytest.raises(Exception):
        ChannelConfigSchema(platform="telegram", max_inbound_media_bytes=-1)


class _Cfg:
    def __init__(self, metadata=None, attr=None):
        self.metadata = metadata if metadata is not None else {}
        if attr is not None:
            self.max_inbound_media_bytes = attr


def test_resolve_cap_defaults_when_unset():
    # Core BotConfig has neither the attribute nor a metadata override.
    assert resolve_max_inbound_media_bytes(_Cfg()) == DEFAULT_MAX_INBOUND_MEDIA_BYTES


def test_resolve_cap_metadata_override_disables():
    # Operator passthrough via config.metadata must reach the adapters,
    # including 0 to disable inbound media.
    assert resolve_max_inbound_media_bytes(_Cfg(metadata={"max_inbound_media_bytes": 0})) == 0
    assert resolve_max_inbound_media_bytes(_Cfg(metadata={"max_inbound_media_bytes": 123})) == 123


def test_resolve_cap_attribute_used_when_no_metadata():
    assert resolve_max_inbound_media_bytes(_Cfg(attr=999)) == 999


class _FakeVisionAgent:
    def __init__(self):
        self.chat_history = []
        self.seen_attachments = None

    def chat(self, prompt, attachments=None):
        self.seen_attachments = attachments
        return f"saw {len(attachments or [])} attachment(s)"


@pytest.mark.asyncio
async def test_chat_threads_attachments_to_agent():
    agent = _FakeVisionAgent()
    mgr = BotSessionManager(platform="telegram")
    path = cache_inbound_media(PNG, kind="image")
    try:
        await mgr.chat(agent, "user", "what is this?", attachments=[path])
    finally:
        os.remove(path)
    assert agent.seen_attachments == [path]


class _FakeNoVisionAgent:
    def __init__(self):
        self.chat_history = []
        self.called = False

    def chat(self, prompt):
        self.called = True
        return "ok"


class _WrapperVisionAgent:
    """A wrapper that forwards **kwargs (incl. attachments) to a vision agent."""

    def __init__(self):
        self.chat_history = []
        self.seen_attachments = None

    def chat(self, prompt, **kwargs):
        self.seen_attachments = kwargs.get("attachments")
        return "ok"


@pytest.mark.asyncio
async def test_chat_threads_attachments_to_kwargs_wrapper():
    # A wrapper exposing chat(prompt, **kwargs) should still receive
    # attachments rather than have them silently dropped (Issue #2350).
    agent = _WrapperVisionAgent()
    mgr = BotSessionManager(platform="telegram")
    path = cache_inbound_media(PNG, kind="image")
    try:
        await mgr.chat(agent, "user", "what is this?", attachments=[path])
    finally:
        os.remove(path)
    assert agent.seen_attachments == [path]


@pytest.mark.asyncio
async def test_chat_skips_attachments_when_agent_unsupported():
    agent = _FakeNoVisionAgent()
    mgr = BotSessionManager(platform="telegram")
    # Should not raise even though attachments are supplied to an agent whose
    # chat() does not accept an attachments kwarg.
    result = await mgr.chat(agent, "user", "hi", attachments=["/tmp/x.png"])
    assert agent.called
    assert result == "ok"
