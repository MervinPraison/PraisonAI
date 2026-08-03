"""Tests for the outbound voice-reply (TTS) helper (Issue #3623).

Mirrors the ``_stt`` inbound tests: config resolution across the accepted
shapes, the ``off``/``always``/``match_inbound`` mode gate, and graceful
degradation when synthesis is unavailable or the reply is too long.
"""

from types import SimpleNamespace

from praisonai_bot.bots._tts import (
    MODE_ALWAYS,
    MODE_MATCH_INBOUND,
    MODE_OFF,
    TtsConfig,
    resolve_tts_config,
    should_voice_reply,
    synthesize_voice_reply,
)


def _cfg(metadata=None, **attrs):
    return SimpleNamespace(metadata=metadata or {}, **attrs)


class TestResolveTtsConfig:
    def test_default_is_off(self):
        cfg = resolve_tts_config(_cfg())
        assert cfg.enabled is False
        assert cfg.mode == MODE_OFF

    def test_bare_bool_true_enables_always(self):
        cfg = resolve_tts_config(_cfg(metadata={"voice": True}))
        assert cfg.enabled is True
        assert cfg.mode == MODE_ALWAYS

    def test_bare_bool_false(self):
        cfg = resolve_tts_config(_cfg(metadata={"voice": False}))
        assert cfg.enabled is False
        assert cfg.mode == MODE_OFF

    def test_dict_full(self):
        cfg = resolve_tts_config(
            _cfg(
                metadata={
                    "voice": {
                        "enabled": True,
                        "mode": "match_inbound",
                        "model": "openai/tts-1",
                        "voice": "alloy",
                        "speed": 1.25,
                        "format": "opus",
                        "max_chars": 1000,
                    }
                }
            )
        )
        assert cfg.enabled is True
        assert cfg.mode == MODE_MATCH_INBOUND
        assert cfg.model == "openai/tts-1"
        assert cfg.voice == "alloy"
        assert cfg.speed == 1.25
        assert cfg.format == "opus"
        assert cfg.max_chars == 1000

    def test_mode_shorthand_enables_without_explicit_enabled(self):
        # A ``mode`` other than off implies the operator wants voice on.
        cfg = resolve_tts_config(_cfg(metadata={"voice": {"mode": "always"}}))
        assert cfg.enabled is True
        assert cfg.mode == MODE_ALWAYS

    def test_hyphenated_mode_normalised(self):
        cfg = resolve_tts_config(
            _cfg(metadata={"voice": {"enabled": True, "mode": "match-inbound"}})
        )
        assert cfg.mode == MODE_MATCH_INBOUND

    def test_unknown_mode_falls_back_to_off(self):
        cfg = resolve_tts_config(
            _cfg(metadata={"voice": {"enabled": True, "mode": "shout"}})
        )
        assert cfg.mode == MODE_OFF

    def test_tts_alias_in_metadata(self):
        cfg = resolve_tts_config(_cfg(metadata={"tts": {"enabled": True, "mode": "always"}}))
        assert cfg.enabled is True
        assert cfg.mode == MODE_ALWAYS

    def test_direct_attribute_fallback(self):
        cfg = resolve_tts_config(_cfg(voice={"enabled": True, "mode": "always"}))
        assert cfg.enabled is True

    def test_string_bools_coerced(self):
        cfg = resolve_tts_config(
            _cfg(metadata={"voice": {"enabled": "false", "mode": "always"}})
        )
        assert cfg.enabled is False


class TestShouldVoiceReply:
    def test_off_never_speaks(self):
        cfg = TtsConfig(enabled=True, mode=MODE_OFF)
        assert should_voice_reply(cfg, inbound_was_voice=True) is False

    def test_disabled_never_speaks(self):
        cfg = TtsConfig(enabled=False, mode=MODE_ALWAYS)
        assert should_voice_reply(cfg, inbound_was_voice=True) is False

    def test_always_speaks_regardless(self):
        cfg = TtsConfig(enabled=True, mode=MODE_ALWAYS)
        assert should_voice_reply(cfg, inbound_was_voice=False) is True
        assert should_voice_reply(cfg, inbound_was_voice=True) is True

    def test_match_inbound_only_on_voice(self):
        cfg = TtsConfig(enabled=True, mode=MODE_MATCH_INBOUND)
        assert should_voice_reply(cfg, inbound_was_voice=False) is False
        assert should_voice_reply(cfg, inbound_was_voice=True) is True


class TestSynthesizeVoiceReply:
    def test_empty_text_returns_none(self):
        assert synthesize_voice_reply("   ", TtsConfig(enabled=True)) is None

    def test_over_max_chars_skips(self):
        cfg = TtsConfig(enabled=True, max_chars=5)
        assert synthesize_voice_reply("way too long", cfg) is None

    def test_delegates_to_tts_tool(self, monkeypatch):
        calls = {}

        def fake_tts_tool(
            text, voice=None, model=None, output_format="ogg", speed=None
        ):
            calls.update(
                text=text,
                voice=voice,
                model=model,
                output_format=output_format,
                speed=speed,
            )
            return {"success": True, "audio_path": "/tmp/reply.ogg"}

        import praisonai_bot.tools.audio as audio_mod

        monkeypatch.setattr(audio_mod, "tts_tool", fake_tts_tool)

        cfg = TtsConfig(enabled=True, voice="alloy", model="openai/tts-1", format="ogg")
        path = synthesize_voice_reply("Hello there", cfg)
        assert path == "/tmp/reply.ogg"
        assert calls["text"] == "Hello there"
        assert calls["voice"] == "alloy"
        assert calls["model"] == "openai/tts-1"
        assert calls["output_format"] == "ogg"

    def test_forwards_speed_to_tts_tool(self, monkeypatch):
        # Regression: a configured ``voice.speed`` must reach the TTS tool
        # instead of being silently dropped (default speaking rate).
        calls = {}

        def fake_tts_tool(
            text, voice=None, model=None, output_format="ogg", speed=None
        ):
            calls["speed"] = speed
            return {"success": True, "audio_path": "/tmp/reply.ogg"}

        import praisonai_bot.tools.audio as audio_mod

        monkeypatch.setattr(audio_mod, "tts_tool", fake_tts_tool)

        cfg = TtsConfig(enabled=True, speed=1.5)
        assert synthesize_voice_reply("Hello", cfg) == "/tmp/reply.ogg"
        assert calls["speed"] == 1.5

    def test_failure_returns_none(self, monkeypatch):
        import praisonai_bot.tools.audio as audio_mod

        monkeypatch.setattr(
            audio_mod,
            "tts_tool",
            lambda *a, **k: {"success": False, "error": "boom"},
        )
        assert synthesize_voice_reply("hi", TtsConfig(enabled=True)) is None


class TestSchema:
    def test_schema_defaults_off(self):
        from praisonai_bot.bots._config_schema import TtsConfigSchema

        schema = TtsConfigSchema()
        assert schema.enabled is False
        assert schema.mode == "off"

    def test_channel_schema_accepts_voice_block(self):
        from praisonai_bot.bots._config_schema import ChannelConfigSchema

        ch = ChannelConfigSchema(
            platform="telegram",
            voice={"enabled": True, "mode": "match_inbound", "voice": "alloy"},
        )
        assert ch.voice is not None
        assert ch.voice.enabled is True
        assert ch.voice.mode == "match_inbound"
