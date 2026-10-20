"""Inbound voice notes reach the agent on Discord and Signal (Issue #5929)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from praisonaiagents.bots import BotConfig

from praisonai_bot.bots import _stt
from praisonai_bot.bots._stt import DEFAULT_VOICE_PLACEHOLDER, transcribe_audio_bytes

OGG = b"OggS" + b"\x00" * 64


def _run(coro):
    return asyncio.run(coro)


def test_transcribe_audio_bytes_returns_transcript():
    with patch.object(_stt, "transcribe_media_path", return_value="hello there"):
        assert _run(transcribe_audio_bytes(OGG, BotConfig(token="x"))) == "hello there"


def test_transcribe_audio_bytes_degrades_to_placeholder():
    cfg = BotConfig(token="x")
    with patch.object(_stt, "transcribe_media_path", return_value=None):
        assert _run(transcribe_audio_bytes(OGG, cfg)) == DEFAULT_VOICE_PLACEHOLDER
    # Invalid audio bytes fail magic-byte validation -> placeholder, no raise.
    assert _run(transcribe_audio_bytes(b"not audio", cfg)) == DEFAULT_VOICE_PLACEHOLDER
    # STT disabled -> placeholder without transcribing.
    off = BotConfig(token="x", metadata={"stt": False})
    with patch.object(_stt, "transcribe_media_path") as tm:
        assert _run(transcribe_audio_bytes(OGG, off)) == DEFAULT_VOICE_PLACEHOLDER
        tm.assert_not_called()


def test_discord_transcribes_audio_attachment():
    from praisonai_bot.bots.discord import DiscordBot

    bot = DiscordBot(token="x")

    async def _read():
        return OGG

    att = SimpleNamespace(content_type="audio/ogg", size=len(OGG), filename="voice.ogg", read=_read)
    with patch.object(_stt, "transcribe_media_path", return_value="reschedule the 3pm"):
        assert _run(bot._transcribe_audio(SimpleNamespace(attachments=[att]))) == "reschedule the 3pm"
    img = SimpleNamespace(content_type="image/png", size=10, filename="a.png", read=_read)
    assert _run(bot._transcribe_audio(SimpleNamespace(attachments=[img]))) is None


class _Resp:
    status = 200

    def __init__(self, data):
        self.content = SimpleNamespace(read=self._read)
        self._data = data

    async def _read(self, n):
        return self._data[:n]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def test_signal_transcribes_audio_attachment():
    from praisonai_bot.bots.signal import SignalBot

    bot = SignalBot(account="+15550000000", bridge_url="http://bridge:8080")
    urls = []

    def _get(url):
        urls.append(url)
        return _Resp(OGG)

    bot._http_session = SimpleNamespace(get=_get)
    data_msg = {"attachments": [{"id": "abc", "contentType": "audio/aac", "filename": "v.m4a"}]}
    with patch.object(_stt, "transcribe_media_path", return_value="call me back"):
        assert _run(bot._transcribe_audio(data_msg)) == "call me back"
    assert urls == ["http://bridge:8080/v1/attachments/abc"]
    assert _run(bot._transcribe_audio({"attachments": []})) is None
