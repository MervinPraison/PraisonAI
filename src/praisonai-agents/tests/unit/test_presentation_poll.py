"""Tests for the native poll presentation primitive and its degradation."""

import asyncio

from praisonaiagents.bots import (
    MessagePresentation,
    PresentationBlock,
    PresentationLimits,
    ActionType,
    BlockType,
    adapt_presentation,
    adapt_presentation_with_report,
    InteractiveContext,
    PollResult,
    make_poll_result_handler,
    POLL_NAMESPACE,
)


def _poll():
    return PresentationBlock.make_poll(
        "Which time works?",
        ["09:00", "13:00", "16:00"],
        multiple_choice=False,
        anonymous=True,
        duration_seconds=3600,
        action_id="slot",
    )


def test_make_poll_sets_fields():
    block = _poll()
    assert block.type == BlockType.POLL
    assert block.text == "Which time works?"
    assert block.poll_options == ["09:00", "13:00", "16:00"]
    assert block.multiple_choice is False
    assert block.anonymous is True
    assert block.duration_seconds == 3600
    assert block.action_id == "slot"


def test_poll_roundtrips_through_dict():
    block = _poll()
    restored = PresentationBlock.from_dict(block.to_dict())
    assert restored.type == BlockType.POLL.value
    assert restored.poll_options == block.poll_options
    assert restored.multiple_choice == block.multiple_choice
    assert restored.anonymous == block.anonymous
    assert restored.duration_seconds == block.duration_seconds


def test_poll_preserved_on_native_channel():
    p = MessagePresentation([_poll()])
    adapted = adapt_presentation(p, PresentationLimits.telegram())
    assert adapted.blocks[0].type == BlockType.POLL
    assert adapted.blocks[0].poll_options == ["09:00", "13:00", "16:00"]


def test_poll_degrades_to_buttons_when_unsupported():
    limits = PresentationLimits()  # supports_native_poll defaults to False
    p = MessagePresentation([_poll()])
    adapted = adapt_presentation(p, limits)
    # question text + reply-button grid
    assert adapted.blocks[0].type == BlockType.TEXT
    assert adapted.blocks[0].text == "Which time works?"
    assert adapted.blocks[1].type == BlockType.BUTTONS
    labels = [b.label for b in adapted.blocks[1].buttons]
    assert labels == ["09:00", "13:00", "16:00"]
    # reply actions are degraded to callback so channel renderers can carry them
    for b in adapted.blocks[1].buttons:
        assert b.action.type == ActionType.CALLBACK
        assert b.action.value.startswith("reply:")


def test_poll_degradation_reported():
    limits = PresentationLimits()
    p = MessagePresentation([_poll()])
    _, report = adapt_presentation_with_report(p, limits)
    assert report is not None
    assert any("poll" in d for d in report.dropped)
    assert "poll_rendered_as_buttons" in report.reasons


def test_no_report_on_native_channel():
    p = MessagePresentation([_poll()])
    _, report = adapt_presentation_with_report(p, PresentationLimits.telegram())
    assert report is None


def test_input_presentation_not_mutated_by_poll_degradation():
    p = MessagePresentation([_poll()])
    adapt_presentation(p, PresentationLimits())
    assert p.blocks[0].type == BlockType.POLL
    assert len(p.blocks) == 1


def test_poll_result_winner_and_roundtrip():
    result = PollResult(
        poll_id="slot",
        counts={"09:00": 3, "13:00": 5, "16:00": 1},
        total_voters=9,
        closed=True,
    )
    assert result.winner() == "13:00"
    assert PollResult.from_dict(result.to_dict()) == result


def test_poll_result_winner_none_on_tie_or_empty():
    assert PollResult("p", {}).winner() is None
    assert PollResult("p", {"a": 2, "b": 2}).winner() is None


def test_poll_result_handler_routes_result():
    captured = {}

    async def on_result(result, context):
        captured["winner"] = result.winner()
        return "ok"

    handler = make_poll_result_handler(on_result)
    ctx = InteractiveContext(
        callback_data="poll:slot",
        user_id="u1",
        platform_data={"poll_result": PollResult("slot", {"a": 1, "b": 4})},
    )
    out = asyncio.get_event_loop().run_until_complete(handler(ctx))
    assert out == "ok"
    assert captured["winner"] == "b"


def test_poll_result_handler_accepts_dict_payload():
    async def on_result(result, context):
        return result.poll_id

    handler = make_poll_result_handler(on_result)
    ctx = InteractiveContext(
        callback_data="poll:slot",
        user_id="u1",
        platform_data={"poll_result": {"poll_id": "slot", "counts": {"a": 1}}},
    )
    out = asyncio.get_event_loop().run_until_complete(handler(ctx))
    assert out == "slot"


def test_poll_namespace_constant():
    assert POLL_NAMESPACE == "poll"
