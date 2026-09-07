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
    iter_sentences,
    resolve_tts_config,
    should_voice_reply,
    split_sentences,
    stream_voice_reply_clips,
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


class TestSplitSentences:
    def test_empty_returns_empty(self):
        assert split_sentences("   ") == []

    def test_single_sentence_no_terminator(self):
        assert split_sentences("hello there") == ["hello there"]

    def test_multiple_sentences(self):
        assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]

    def test_trailing_remainder_kept(self):
        assert split_sentences("Done. And more") == ["Done.", "And more"]

    def test_decimal_not_split(self):
        # A period inside 3.14 has no following whitespace, so it is not a break.
        assert split_sentences("Pi is 3.14 exactly.") == ["Pi is 3.14 exactly."]

    def test_closing_quote_kept_with_sentence(self):
        assert split_sentences('He said "hi." Then left.') == [
            'He said "hi."',
            "Then left.",
        ]


class TestIterSentences:
    def test_emits_as_terminators_arrive(self):
        chunks = ["Hello", " world.", " How", " are you?", " Bye"]
        assert list(iter_sentences(chunks)) == [
            "Hello world.",
            "How are you?",
            "Bye",
        ]

    def test_flush_remainder_false_drops_tail(self):
        chunks = ["One.", " partial"]
        assert list(iter_sentences(chunks, flush_remainder=False)) == ["One."]

    def test_ignores_empty_chunks(self):
        assert list(iter_sentences(["", "Hi.", "", ""])) == ["Hi."]

    def test_terminator_at_chunk_boundary_not_split_early(self):
        # A "." at the tail of a delta may be a decimal continued by the next
        # delta ("3." + "14") — it must not be finalised as a sentence end.
        assert list(iter_sentences(["Pi is 3.", "14 exactly."])) == [
            "Pi is 3.14 exactly."
        ]

    def test_boundary_terminator_emitted_once_confirmed(self):
        # Held terminator is emitted as soon as a following delta confirms the
        # boundary (whitespace/next clause), not only at flush.
        assert list(iter_sentences(["One.", " Two."])) == ["One.", "Two."]


class TestStreamVoiceReplyClips:
    def test_yields_a_clip_per_sentence(self, monkeypatch):
        seen = []

        def fake_tts_tool(text, voice=None, model=None, output_format="ogg", speed=None):
            seen.append(text)
            return {"success": True, "audio_path": f"/tmp/{len(seen)}.ogg"}

        import praisonai_bot.tools.audio as audio_mod

        monkeypatch.setattr(audio_mod, "tts_tool", fake_tts_tool)

        cfg = TtsConfig(enabled=True, stream=True)
        clips = list(stream_voice_reply_clips(["One.", " Two.", " Three."], cfg))
        assert clips == ["/tmp/1.ogg", "/tmp/2.ogg", "/tmp/3.ogg"]
        assert seen == ["One.", "Two.", "Three."]

    def test_skips_failed_clause_but_keeps_going(self, monkeypatch):
        def fake_tts_tool(text, voice=None, model=None, output_format="ogg", speed=None):
            if "boom" in text:
                return {"success": False, "error": "boom"}
            return {"success": True, "audio_path": "/tmp/ok.ogg"}

        import praisonai_bot.tools.audio as audio_mod

        monkeypatch.setattr(audio_mod, "tts_tool", fake_tts_tool)

        cfg = TtsConfig(enabled=True, stream=True)
        clips = list(stream_voice_reply_clips(["boom now.", " fine now."], cfg))
        assert clips == ["/tmp/ok.ogg"]


class TestSchema:
    def test_schema_defaults_off(self):
        from praisonai_bot.bots._config_schema import TtsConfigSchema

        schema = TtsConfigSchema()
        assert schema.enabled is False
        assert schema.mode == "off"
        assert schema.stream is False

    def test_stream_resolves_from_metadata(self):
        cfg = resolve_tts_config(
            _cfg(metadata={"voice": {"mode": "always", "stream": True}})
        )
        assert cfg.stream is True

    def test_stream_string_bool_coerced(self):
        cfg = resolve_tts_config(
            _cfg(metadata={"voice": {"mode": "always", "stream": "true"}})
        )
        assert cfg.stream is True

    def test_channel_schema_accepts_voice_block(self):
        from praisonai_bot.bots._config_schema import ChannelConfigSchema

        ch = ChannelConfigSchema(
            platform="telegram",
            voice={"enabled": True, "mode": "match_inbound", "voice": "alloy"},
        )
        assert ch.voice is not None
        assert ch.voice.enabled is True
        assert ch.voice.mode == "match_inbound"
