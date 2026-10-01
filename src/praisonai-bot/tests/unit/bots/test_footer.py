#!/usr/bin/env python3
"""
Tests for the opt-in, privacy-safe per-reply runtime footer (issue #5428).

The footer surfaces only model name, context % and turn latency on the FINAL
reply. Missing fields are omitted (never shown as placeholders), and nothing is
appended when the footer is empty or the feature is disabled.
"""

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
