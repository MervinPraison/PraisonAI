#!/usr/bin/env python3
"""
Tests for the opt-in, privacy-safe per-reply runtime footer (issue #5428).

The footer surfaces only model name, context % and turn latency on the FINAL
reply. Missing fields are omitted (never shown as placeholders), and nothing is
appended when the footer is empty or the feature is disabled.
"""

import asyncio
import types

from praisonai_bot.bots._streaming import append_footer, build_footer_line


def test_full_footer_line():
    assert build_footer_line(
        model="gpt-4o",
        served_model="gpt-4o-2024-08-06",
        context_pct=41,
        latency_s=3.8,
    ) == "gpt-4o (served: gpt-4o-2024-08-06) · 41% ctx · 3.8s"


def test_model_and_latency_only():
    assert build_footer_line(model="gpt-4o", latency_s=4.2) == "gpt-4o · 4.2s"


def test_served_model_hidden_when_same_as_model():
    # No "(served: ...)" when the served deployment matches the configured model.
    assert build_footer_line(model="gpt-4o", served_model="gpt-4o") == "gpt-4o"


def test_missing_fields_are_omitted_not_placeheld():
    # Only a context % available -> just that field, no "?" placeholders.
    assert build_footer_line(context_pct=38) == "38% ctx"


def test_empty_when_no_fields():
    assert build_footer_line() == ""


def test_context_pct_rounded_to_int():
    assert build_footer_line(context_pct=37.6) == "38% ctx"


def test_invalid_numbers_are_dropped():
    assert build_footer_line(model="m", context_pct=float("nan")) == "m"
    assert build_footer_line(model="m", latency_s=float("inf")) == "m"
    assert build_footer_line(model="m", latency_s=-1) == "m"


def test_blank_model_is_dropped():
    assert build_footer_line(model="   ", latency_s=1.0) == "1.0s"


def test_append_footer_adds_separator():
    assert (
        append_footer("Here is your answer.", "gpt-4o · 4.2s")
        == "Here is your answer.\n\n— gpt-4o · 4.2s"
    )


def test_append_footer_noop_on_empty_line():
    assert append_footer("body", "") == "body"


# ---------------------------------------------------------------------------
# Handler-level delivery behaviour (opt-in wiring + voice exclusion).
#
# TelegramBot carries a heavy optional ``telegram`` dependency, so rather than
# construct the whole bot we bind the two unbound methods under test to a light
# stub that supplies just the attributes they touch. This exercises the real
# code paths (opt-in gating, model/latency capture, footer-in-text-not-voice)
# deterministically and without network or the telegram package.
# ---------------------------------------------------------------------------

from praisonai_bot.bots.telegram import TelegramBot  # noqa: E402


def _make_stub(footer_enabled, llm="gpt-4o"):
    stub = types.SimpleNamespace()
    stub.config = types.SimpleNamespace(footer=footer_enabled)
    stub._agent = types.SimpleNamespace(llm=llm)
    return stub


def test_footer_line_disabled_returns_empty():
    stub = _make_stub(footer_enabled=False)
    line = TelegramBot._footer_line(stub, turn_started_at=None)
    assert line == ""


def test_footer_line_enabled_includes_model():
    stub = _make_stub(footer_enabled=True, llm="gpt-4o")
    line = TelegramBot._footer_line(stub, turn_started_at=None)
    assert line == "gpt-4o"


def test_footer_line_enabled_includes_model_and_latency():
    import time

    stub = _make_stub(footer_enabled=True, llm="gpt-4o")
    started = time.monotonic() - 2.0
    line = TelegramBot._footer_line(stub, turn_started_at=started)
    assert line.startswith("gpt-4o · ")
    assert line.endswith("s")


def test_footer_line_non_string_llm_omits_model():
    stub = _make_stub(footer_enabled=True, llm=object())
    line = TelegramBot._footer_line(stub, turn_started_at=None)
    assert line == ""


def _run_send(stub, response, footer_line):
    sent_text = {}
    voiced_text = {}

    async def fake_send_long(chat_id, text, reply_to=None):
        sent_text["value"] = text

    async def fake_voice(chat_id, text, *, inbound_was_voice=False):
        voiced_text["value"] = text

    stub._send_long_message = fake_send_long
    stub._maybe_send_voice_reply = fake_voice
    asyncio.run(
        TelegramBot._send_response_with_media(
            stub, 123, response, reply_to=1, footer_line=footer_line
        )
    )
    return sent_text.get("value"), voiced_text.get("value")


def test_send_appends_footer_to_text_only():
    stub = types.SimpleNamespace()
    sent, voiced = _run_send(stub, "Here is your answer.", "gpt-4o · 4.2s")
    # Footer appears in the delivered text …
    assert sent == "Here is your answer.\n\n— gpt-4o · 4.2s"
    # … but never in the text handed to voice synthesis.
    assert voiced == "Here is your answer."


def test_send_without_footer_leaves_text_unchanged():
    stub = types.SimpleNamespace()
    sent, voiced = _run_send(stub, "Plain reply.", "")
    assert sent == "Plain reply."
    assert voiced == "Plain reply."
