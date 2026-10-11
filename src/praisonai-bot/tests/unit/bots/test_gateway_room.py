"""Gateway enactment of multi-agent rooms (Issue #5768)."""

import asyncio

import pytest

from praisonaiagents.rooms import RoomConfig

from praisonai_bot.bots._room import GatewayRoom, build_rooms


class FakeAgent:
    """Sync agent stub that records prompts and optionally @-mentions a peer."""

    def __init__(self, name, mention=None):
        self.name = name
        self.mention = mention
        self.chat_history = ["own-history"]
        self.prompts = []

    def chat(self, prompt, **_):
        assert self.chat_history == []  # member runs on a clean slate
        self.prompts.append(prompt)
        reply = f"{self.name} says hi"
        if self.mention and len(self.prompts) == 1:
            reply += f" @{self.mention}"
        return reply


def _room(**kw):
    agents = {"researcher": FakeAgent("researcher", mention="critic"),
              "critic": FakeAgent("critic")}
    cfg = RoomConfig(name="standup", roster=["researcher", "critic"], **kw)
    return GatewayRoom(cfg, agents), agents


def test_room_runs_bounded_turns_and_records_transcript():
    room, agents = _room()
    out = room.chat("plan the release")

    # Round 0: everyone once; round 1: only the @-mentioned critic.
    assert out.count("**researcher**") == 1
    assert out.count("**critic**") == 2
    assert [m.get("name") for m in room.chat_history] == [
        None, "researcher", "critic", "critic"
    ]
    assert room.chat_history[-1]["round"] == 1
    # Member history restored, and the critic saw the shared transcript.
    assert agents["critic"].chat_history == ["own-history"]
    assert "researcher: researcher says hi @critic" in agents["critic"].prompts[0]


def test_room_resumes_from_persisted_history():
    room, _ = _room()
    room.chat("first")
    persisted = list(room.chat_history)

    # Simulate a restart: a fresh room is handed the persisted transcript.
    fresh, agents = _room()
    fresh.chat_history = persisted
    fresh.chat("second")
    assert len(fresh.chat_history) > len(persisted)
    assert "first" in agents["researcher"].prompts[0]


def test_room_async_path():
    room, _ = _room(max_rounds=1)
    out = asyncio.run(room.achat("hello"))
    assert out.count("**critic**") == 1


def test_build_rooms_from_yaml_block_warns_on_missing_member(caplog):
    agents = {"researcher": FakeAgent("researcher")}
    rooms = build_rooms(
        {"standup": {"agents": ["researcher", "ghost"], "max_rounds": 2}}, agents
    )
    room = rooms["room:standup"]
    assert room.config.max_rounds == 2
    assert "ghost" in caplog.text
    out = room.chat("hi")
    assert "**researcher**" in out and "ghost" not in out


def test_build_rooms_rejects_bad_roster():
    with pytest.raises(ValueError):
        build_rooms({"standup": {"agents": "researcher"}}, {})


def test_room_through_session_manager_persists_transcript():
    from praisonai_bot.bots._session import BotSessionManager

    room, _ = _room()
    mgr = BotSessionManager(platform="test")
    out = asyncio.run(mgr.chat(room, "u1", "kick off"))
    assert "**critic**" in out
    # Session swapped the per-user transcript back out of the shared room.
    assert room.chat_history == []
    # ...and persisted it under the user's session for the next turn/restart.
    history = mgr._load_history("u1")
    assert any(m.get("name") == "critic" for m in history)


def test_gateway_registers_room_route():
    from praisonai_bot.gateway.server import WebSocketGateway

    gw = WebSocketGateway.__new__(WebSocketGateway)
    gw._agents = {"researcher": FakeAgent("researcher"), "critic": FakeAgent("critic")}
    gw._register_rooms_from_config({"standup": {"agents": ["researcher", "critic"]}})
    assert isinstance(gw._agents["room:standup"], GatewayRoom)


def test_schema_accepts_rooms_block():
    from praisonai_bot.bots._config_schema import validate_gateway_config

    cfg = validate_gateway_config({
        "agents": {"a": {}, "b": {}},
        "rooms": {"standup": {"agents": ["a", "b"], "max_rounds": 2}},
        "channels": {"telegram": {"token": "x", "routes": {"group": "room:standup"}}},
    })
    assert cfg.rooms["standup"]["agents"] == ["a", "b"]
