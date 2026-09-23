"""Tests for the room config + enacting runtime (Issue #5067)."""

import asyncio

import pytest

from praisonaiagents.rooms import Room, RoomConfig, RoomEvent


def _echo_agents(*names):
    """Build a mapping of agent id -> async reply that names itself."""
    def make(name):
        async def reply(prompt: str) -> str:
            return f"{name} replied"
        return reply

    return {n: make(n) for n in names}


def test_room_config_validation_and_planner_build():
    cfg = RoomConfig(name="standup", roster=["a", "b"], max_rounds=2, max_messages=5)
    planner = cfg.build_planner()
    assert planner.max_rounds == 2
    assert planner.max_messages == 5

    with pytest.raises(ValueError):
        RoomConfig(name="")
    with pytest.raises(ValueError):
        RoomConfig(name="x", planner="unknown")
    with pytest.raises(ValueError):
        RoomConfig(name="x", max_rounds=0)


def test_room_config_from_dict_accepts_agents_or_roster():
    a = RoomConfig.from_dict("r", {"agents": ["x", "y"], "max_rounds": 2})
    assert a.roster == ["x", "y"]
    b = RoomConfig.from_dict("r", {"roster": ["p"], "max_messages": 9})
    assert b.roster == ["p"]
    assert b.max_messages == 9


def test_room_round0_fans_out_to_every_agent():
    cfg = RoomConfig(name="r", roster=["planner", "coder", "reviewer"])
    room = Room(cfg, _echo_agents("planner", "coder", "reviewer"))

    produced = asyncio.run(room.on_message(RoomEvent(speaker="user", content="build X")))

    assert [e.speaker for e in produced] == ["planner", "coder", "reviewer"]
    assert all(e.round == 0 for e in produced)


def test_room_mention_admits_only_mentioned_agent_next_round():
    cfg = RoomConfig(name="r", roster=["a", "b", "c"])

    async def a_reply(prompt: str) -> str:
        return "please review @c"

    async def plain(prompt: str) -> str:
        return "ok"

    agents = {"a": a_reply, "b": plain, "c": plain}
    room = Room(cfg, agents)

    produced = asyncio.run(room.on_message(RoomEvent(speaker="user", content="go")))

    speakers = [e.speaker for e in produced]
    # Round 0: a, b, c all speak. a mentioned @c -> only c admitted in round 1.
    assert speakers[:3] == ["a", "b", "c"]
    assert "c" in speakers[3:]
    assert "b" not in speakers[3:]
    # The admitted round-1 turn carries round == 1.
    round1 = [e for e in produced if e.round == 1]
    assert round1 and all(e.speaker == "c" for e in round1)


def test_room_unknown_roster_id_records_a_pass():
    cfg = RoomConfig(name="r", roster=["ghost", "real"])
    room = Room(cfg, {"real": next(iter(_echo_agents("real").values()))})

    produced = asyncio.run(room.on_message(RoomEvent(speaker="user", content="hi")))

    ghost = [e for e in produced if e.speaker == "ghost"]
    assert ghost and ghost[0].passed is True
    assert any(e.speaker == "real" and not e.passed for e in produced)


def test_room_next_human_reopens_a_fresh_activity():
    cfg = RoomConfig(name="r", roster=["a"])
    room = Room(cfg, _echo_agents("a"))

    first = asyncio.run(room.on_message(RoomEvent(speaker="user", content="one")))
    assert [e.speaker for e in first] == ["a"]

    # A settled room restarts when the next human speaks.
    second = asyncio.run(room.on_message(RoomEvent(speaker="user", content="two")))
    assert [e.speaker for e in second] == ["a"]


def test_room_transcript_replay_is_deterministic():
    cfg = RoomConfig(name="r", roster=["a", "b"])
    room1 = Room(cfg, _echo_agents("a", "b"))
    asyncio.run(room1.on_message(RoomEvent(speaker="user", content="go")))

    # Rebuild a room from the persisted transcript: planner replays identically.
    room2 = Room(cfg, _echo_agents("a", "b"))
    room2.transcript = list(room1.transcript)
    nxt = room2.planner.plan_next(cfg.roster, room2.transcript)
    assert nxt is None  # already settled -> no double-execution
