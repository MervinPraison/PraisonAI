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
        self.tools = []

    def chat(self, prompt, attachments=None, cancel_token=None):
        assert self.chat_history == []  # member runs on a clean slate
        self.prompts.append(prompt)
        self.seen = {"attachments": attachments, "tools": list(self.tools)}
        reply = f"{self.name} says hi"
        if self.mention and len(self.prompts) == 1:
            reply += f" @{self.mention}"
        return reply

    def clone_for_channel(self):
        return FakeAgent(self.name, self.mention)


def _room(**kw):
    agents = {"researcher": FakeAgent("researcher", mention="critic"),
              "critic": FakeAgent("critic")}
    cfg = RoomConfig(name="standup", roster=["researcher", "critic"], **kw)
    room = GatewayRoom(cfg, agents)
    return room, room.agents


def test_room_runs_bounded_turns_and_records_transcript():
    room, agents = _room()
    out = room.chat("plan the release")

    # Round 0: everyone once; round 1: only the @-mentioned critic.
    assert out.count("**researcher**") == 1
    assert out.count("**critic**") == 2
    assert [m["content"].split(":")[0] for m in room.chat_history] == [
        "plan the release", "researcher", "critic", "critic"
    ]
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
    assert any(m["content"].startswith("critic: ") for m in history)


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


def test_room_transcript_survives_real_session_store(tmp_path):
    """Store drops extra keys; the speaker must survive in role/content."""
    from praisonaiagents.session.store import DefaultSessionStore

    from praisonai_bot.bots._session import BotSessionManager

    room, _ = _room()
    mgr = BotSessionManager(platform="test", store=DefaultSessionStore(session_dir=str(tmp_path)))
    asyncio.run(mgr.chat(room, "u1", "first"))

    fresh, agents = _room()
    mgr2 = BotSessionManager(platform="test", store=DefaultSessionStore(session_dir=str(tmp_path)))
    asyncio.run(mgr2.chat(fresh, "u1", "second"))
    assert "researcher: researcher says hi" in agents["critic"].prompts[0]


def test_human_and_summary_ids_never_collide_with_roster():
    agents = {n: FakeAgent(n) for n in ("user", "human")}
    room = GatewayRoom(RoomConfig(name="r", roster=["user", "human"]), agents)
    agents = room.agents
    room.chat_history = [{"role": "system", "content": "Earlier: shipped v1"}]
    out = room.chat("hi")
    assert "**user**" in out and "**human**" in out
    assert "Earlier: shipped v1" in agents["user"].prompts[0]


def test_route_tool_policy_scopes_member_tools():
    from praisonaiagents.gateway.protocols import ToolPolicy

    from praisonai_bot.bots._session import BotSessionManager

    def safe():
        pass

    def shell():
        pass

    room, agents = _room(max_rounds=1)
    agents["researcher"].tools = [safe, shell]
    mgr = BotSessionManager(platform="test")
    asyncio.run(mgr.chat(room, "u1", "go", tool_policy=ToolPolicy(deny_tools=["shell"])))
    assert agents["researcher"].seen["tools"] == [safe]
    assert agents["researcher"].tools == [safe, shell]  # restored
    assert room._allowed_tools is None


def test_room_forwards_attachments_and_stops_on_cancel():
    room, agents = _room(max_rounds=1)
    room.chat("look", attachments=["/tmp/a.png"])
    assert agents["critic"].seen["attachments"] == ["/tmp/a.png"]

    class Stop:
        def is_set(self):
            return True

    with pytest.raises(InterruptedError):
        room.chat("again", cancel_token=Stop())


def test_room_clones_members_and_never_shares_unclonable_ones():
    class Plain:
        name = "critic"
        chat_history = []

        def chat(self, prompt):  # pragma: no cover - must never be called
            raise AssertionError("shared instance was used")

    class Broken(FakeAgent):
        def clone_for_channel(self):
            raise RuntimeError("boom")

    shared = FakeAgent("researcher")
    room = GatewayRoom(
        RoomConfig(name="r", roster=["researcher", "critic", "broken"]),
        {"researcher": shared, "critic": Plain(), "broken": Broken("broken")},
    )
    assert room.agents["researcher"] is not shared
    assert set(room.agents) == {"researcher"}  # unclonable members pass
    out = room.chat("hi")
    assert "**researcher**" in out and "critic" not in out and "broken" not in out
    assert shared.prompts == [] and shared.chat_history == ["own-history"]


def test_member_tools_restored_when_policy_cleared_mid_turn():
    """A timeout/cancel restore of ``room.tools`` must not strand narrowed tools."""

    def safe():
        pass

    def shell():
        pass

    room, agents = _room(max_rounds=1)
    researcher = agents["researcher"]
    researcher.tools = [safe, shell]
    full = room.tools
    room.tools = [safe]  # session narrows for this turn
    inner_chat = researcher.chat

    def chat(prompt, **kw):
        room.tools = full  # session restores while the member is still running
        return inner_chat(prompt, **kw)

    researcher.chat = chat
    room.chat("go")
    assert researcher.seen["tools"] == [safe]
    assert researcher.tools == [safe, shell]
    assert room._allowed_tools is None


def test_schema_rejects_invalid_room():
    from praisonai_bot.bots._config_schema import validate_gateway_config

    with pytest.raises(Exception, match="rooms.standup"):
        validate_gateway_config({
            "agents": {"a": {}},
            "rooms": {"standup": {"agents": ["a"], "max_rounds": 0}},
        })
