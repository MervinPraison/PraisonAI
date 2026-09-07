"""Tests for the pure conversation-room turn planner (Issue #4917)."""

import pytest

from praisonaiagents.rooms import (
    RoomEvent,
    RoomTurnPlannerProtocol,
    RoundRobinRoomPlanner,
    extract_mentions,
)


def test_extract_mentions_basic_and_dedup_order():
    assert extract_mentions("hey @coder and @reviewer, then @coder again") == [
        "coder",
        "reviewer",
    ]


def test_extract_mentions_ignores_email_like():
    assert extract_mentions("mail me at foo@bar.com") == []
    assert extract_mentions("") == []


def test_planner_satisfies_protocol():
    assert isinstance(RoundRobinRoomPlanner(), RoomTurnPlannerProtocol)


def test_round0_schedules_every_agent_in_roster_order():
    roster = ["planner", "coder", "reviewer"]
    planner = RoundRobinRoomPlanner()
    transcript = [RoomEvent(speaker="user", content="build X", round=0)]

    assert planner.plan_next(roster, transcript) == "planner"

    transcript.append(RoomEvent(speaker="planner", content="step 1", round=0))
    assert planner.plan_next(roster, transcript) == "coder"

    transcript.append(RoomEvent(speaker="coder", content="done", round=0))
    assert planner.plan_next(roster, transcript) == "reviewer"

    transcript.append(RoomEvent(speaker="reviewer", content="lgtm", round=0))
    # No @mentions -> round settles -> None.
    assert planner.plan_next(roster, transcript) is None


def test_no_turn_before_a_human_message():
    roster = ["a", "b"]
    planner = RoundRobinRoomPlanner()
    assert planner.plan_next(roster, []) is None
    # Only agent events, no human seed -> still None.
    assert planner.plan_next(roster, [RoomEvent(speaker="a", round=0)]) is None


def test_empty_roster_returns_none():
    planner = RoundRobinRoomPlanner()
    assert planner.plan_next([], [RoomEvent(speaker="user")]) is None


def test_mention_admits_only_mentioned_agent_in_next_round():
    roster = ["planner", "coder", "reviewer"]
    planner = RoundRobinRoomPlanner()
    transcript = [
        RoomEvent(speaker="user", content="build X", round=0),
        RoomEvent(speaker="planner", content="@coder please implement", round=0),
        RoomEvent(speaker="coder", content="ok", round=0),
        RoomEvent(speaker="reviewer", content="looks fine", round=0),
    ]
    # Round 0 filled; planner mentioned coder -> only coder admitted to round 1.
    assert planner.plan_next(roster, transcript) == "coder"

    transcript.append(RoomEvent(speaker="coder", content="fixed", round=1))
    # coder didn't mention anyone -> round 2 empty -> None.
    assert planner.plan_next(roster, transcript) is None


def test_mention_of_non_roster_is_ignored():
    roster = ["a", "b"]
    planner = RoundRobinRoomPlanner()
    transcript = [
        RoomEvent(speaker="user", content="go", round=0),
        RoomEvent(speaker="a", content="@nobody hi", round=0),
        RoomEvent(speaker="b", content="done", round=0),
    ]
    assert planner.plan_next(roster, transcript) is None


def test_pass_consumes_the_turn():
    roster = ["a", "b"]
    planner = RoundRobinRoomPlanner()
    transcript = [
        RoomEvent(speaker="user", content="go", round=0),
        RoomEvent(speaker="a", content="", round=0, passed=True),
    ]
    # a already spoke (passed) -> next is b, not a again.
    assert planner.plan_next(roster, transcript) == "b"


def test_max_rounds_cap_stops_scheduling():
    roster = ["a", "b"]
    planner = RoundRobinRoomPlanner(max_rounds=1, max_messages=100)
    transcript = [
        RoomEvent(speaker="user", content="go", round=0),
        RoomEvent(speaker="a", content="@b hey", round=0),
        RoomEvent(speaker="b", content="@a back", round=0),
    ]
    # Round 0 full and max_rounds=1 forbids round 1 -> None.
    assert planner.plan_next(roster, transcript) is None


def test_max_messages_cap_stops_scheduling():
    roster = ["a", "b", "c"]
    planner = RoundRobinRoomPlanner(max_rounds=5, max_messages=2)
    transcript = [
        RoomEvent(speaker="user", content="go", round=0),
        RoomEvent(speaker="a", content="hi", round=0),
    ]
    assert planner.plan_next(roster, transcript) is None


def test_determinism_same_input_same_output():
    roster = ["planner", "coder", "reviewer"]
    planner = RoundRobinRoomPlanner()
    transcript = [
        RoomEvent(speaker="user", content="build X", round=0),
        RoomEvent(speaker="planner", content="@reviewer @coder", round=0),
    ]
    first = planner.plan_next(roster, transcript)
    for _ in range(5):
        assert planner.plan_next(roster, transcript) == first
    # Mentions honoured in roster order (coder before reviewer), not mention order.
    assert first == "coder"


def test_room_restarts_on_next_human_message():
    roster = ["a", "b"]
    planner = RoundRobinRoomPlanner()
    transcript = [
        RoomEvent(speaker="user", content="hi", round=0),
        RoomEvent(speaker="a", content="one", round=0),
        RoomEvent(speaker="b", content="two", round=0),
    ]
    # First activity settled.
    assert planner.plan_next(roster, transcript) is None

    # A new human message on the same durable transcript reopens round 0.
    transcript.append(RoomEvent(speaker="user", content="again", round=0))
    assert planner.plan_next(roster, transcript) == "a"

    transcript.append(RoomEvent(speaker="a", content="one", round=0))
    assert planner.plan_next(roster, transcript) == "b"

    transcript.append(RoomEvent(speaker="b", content="two", round=0))
    assert planner.plan_next(roster, transcript) is None


def test_max_messages_cap_is_per_activity_not_lifetime():
    roster = ["a", "b"]
    planner = RoundRobinRoomPlanner(max_rounds=5, max_messages=3)
    transcript = [
        RoomEvent(speaker="user", content="go", round=0),
        RoomEvent(speaker="a", content="hi", round=0),
        RoomEvent(speaker="b", content="yo", round=0),
    ]
    # First activity reached its 3-message cap.
    assert planner.plan_next(roster, transcript) is None

    # Second human message starts a fresh activity; the cap counts from there,
    # not lifetime history, so scheduling resumes.
    transcript.append(RoomEvent(speaker="user", content="more", round=0))
    assert planner.plan_next(roster, transcript) == "a"


def test_mention_admission_scoped_to_current_activity():
    roster = ["a", "b"]
    planner = RoundRobinRoomPlanner()
    transcript = [
        # Prior settled activity with a stale @mention still in history.
        RoomEvent(speaker="user", content="first", round=0),
        RoomEvent(speaker="a", content="@b ping", round=0),
        RoomEvent(speaker="b", content="pong", round=1),
        # New activity: opener with no mentions.
        RoomEvent(speaker="user", content="second", round=0),
        RoomEvent(speaker="a", content="quiet", round=0),
        RoomEvent(speaker="b", content="quiet", round=0),
    ]
    # The stale round-0 @mention from the prior activity must not leak into the
    # new activity's round 1.
    assert planner.plan_next(roster, transcript) is None


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        RoundRobinRoomPlanner(max_rounds=0)
    with pytest.raises(ValueError):
        RoundRobinRoomPlanner(max_messages=0)
