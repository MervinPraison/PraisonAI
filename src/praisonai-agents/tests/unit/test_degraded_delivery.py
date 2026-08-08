"""Tests for the typed degraded-delivery report (adapt_presentation_with_report)."""

import dataclasses

import pytest

from praisonaiagents.bots import (
    MessagePresentation,
    PresentationBlock,
    PresentationButton,
    PresentationAction,
    PresentationLimits,
    SelectOption,
    DegradedDelivery,
    adapt_presentation,
    adapt_presentation_with_report,
)
from praisonaiagents.bots.presentation import (
    DEGRADE_SELECT_UNSUPPORTED,
    DEGRADE_WEB_APP_UNAVAILABLE,
    DEGRADE_BUTTONS_TRUNCATED,
    DEGRADE_OPTIONS_TRUNCATED,
    DEGRADE_TABLE_AS_TEXT,
    DEGRADE_CHART_AS_TEXT,
    DEGRADE_CALLBACK_DATA_TOO_LONG,
)


def test_no_degradation_returns_none():
    p = MessagePresentation([PresentationBlock.make_text("hello")])
    adapted, report = adapt_presentation_with_report(p, PresentationLimits.slack())
    assert report is None
    assert adapted.blocks[0].text == "hello"


def test_adapted_presentation_matches_adapt_presentation():
    buttons = [PresentationButton(label=f"b{i}", priority=i) for i in range(12)]
    p = MessagePresentation([PresentationBlock.make_buttons(buttons)])
    adapted, _ = adapt_presentation_with_report(p, PresentationLimits.slack())
    baseline = adapt_presentation(p, PresentationLimits.slack())
    assert [b.label for b in adapted.blocks[0].buttons] == [
        b.label for b in baseline.blocks[0].buttons
    ]


def test_select_unsupported_reported():
    sel = PresentationBlock.make_select(
        [SelectOption(label="A", value="a"), SelectOption(label="B", value="b")],
        action_id="pick",
    )
    _, report = adapt_presentation_with_report(
        MessagePresentation([sel]), PresentationLimits.telegram()
    )
    assert isinstance(report, DegradedDelivery)
    assert DEGRADE_SELECT_UNSUPPORTED in report.reasons
    assert report.fallback_text.startswith("(")


def test_web_app_unavailable_reported():
    btn = PresentationButton(
        label="Open",
        action=PresentationAction(type="web_app", web_app_url="https://x.example"),
    )
    p = MessagePresentation([PresentationBlock.make_buttons([btn])])
    _, report = adapt_presentation_with_report(p, PresentationLimits.slack())
    assert report is not None
    assert DEGRADE_WEB_APP_UNAVAILABLE in report.reasons


def test_button_truncation_reported():
    buttons = [PresentationButton(label=f"b{i}", priority=i) for i in range(12)]
    p = MessagePresentation([PresentationBlock.make_buttons(buttons)])
    _, report = adapt_presentation_with_report(p, PresentationLimits.slack())  # cap 5
    assert report is not None
    assert DEGRADE_BUTTONS_TRUNCATED in report.reasons


def test_option_truncation_reported():
    opts = [SelectOption(label=f"o{i}", value=str(i)) for i in range(30)]
    sel = PresentationBlock.make_select(opts, action_id="pick")
    _, report = adapt_presentation_with_report(
        MessagePresentation([sel]), PresentationLimits.discord()  # max_options 25
    )
    assert report is not None
    assert DEGRADE_OPTIONS_TRUNCATED in report.reasons


def test_table_as_text_reported():
    tbl = PresentationBlock.make_table(["a", "b"], [["1", "2"]])
    _, report = adapt_presentation_with_report(
        MessagePresentation([tbl]), PresentationLimits.telegram()
    )
    assert report is not None
    assert DEGRADE_TABLE_AS_TEXT in report.reasons


def test_chart_as_text_reported():
    chart = PresentationBlock.make_chart("bar", [{"label": "s", "points": [1, 2]}])
    _, report = adapt_presentation_with_report(
        MessagePresentation([chart]), PresentationLimits.telegram()
    )
    assert report is not None
    assert DEGRADE_CHART_AS_TEXT in report.reasons


def test_callback_too_long_reported():
    long_value = "x" * 200
    btn = PresentationButton(
        label="pick", action=PresentationAction.reply(long_value)
    )
    p = MessagePresentation([PresentationBlock.make_buttons([btn])])
    _, report = adapt_presentation_with_report(p, PresentationLimits.telegram())
    assert report is not None
    assert DEGRADE_CALLBACK_DATA_TOO_LONG in report.reasons


def test_long_callback_with_store_not_reported_shortened():
    # A store round-trips the value losslessly, so no callback-shortening report.
    store = {}

    class _Store:
        def put(self, ref, value, expires_at=None):
            store[ref] = value

        def get(self, ref):
            return store.get(ref)

    long_value = "x" * 200
    btn = PresentationButton(
        label="pick", action=PresentationAction.reply(long_value)
    )
    p = MessagePresentation([PresentationBlock.make_buttons([btn])])
    _, report = adapt_presentation_with_report(
        p, PresentationLimits.telegram(), callback_store=_Store()
    )
    assert report is None or DEGRADE_CALLBACK_DATA_TOO_LONG not in report.reasons


def test_plain_callback_not_reported_as_shortened():
    # A short plain callback is not a reply and is not shortened; no report.
    btn = PresentationButton(
        label="ok", action=PresentationAction(type="callback", value="ok")
    )
    p = MessagePresentation([PresentationBlock.make_buttons([btn])])
    _, report = adapt_presentation_with_report(p, PresentationLimits.telegram())
    assert report is None or DEGRADE_CALLBACK_DATA_TOO_LONG not in report.reasons


def test_long_select_option_value_reported_when_no_store():
    # An oversized select option value, degraded to a button on Telegram, is
    # hashed (lossy) without a store — the report must surface that.
    long_value = "y" * 200
    sel = PresentationBlock.make_select(
        [SelectOption(label="A", value=long_value)], action_id="pick"
    )
    _, report = adapt_presentation_with_report(
        MessagePresentation([sel]), PresentationLimits.telegram()
    )
    assert report is not None
    assert DEGRADE_CALLBACK_DATA_TOO_LONG in report.reasons


def test_report_is_frozen():
    tbl = PresentationBlock.make_table(["a"], [["1"]])
    _, report = adapt_presentation_with_report(
        MessagePresentation([tbl]), PresentationLimits.telegram()
    )
    assert report is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.reasons = ()  # type: ignore[misc]
