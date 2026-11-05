import pytest

from praisonaiagents.gateway import GatewayConfig, SessionConfig
from praisonai_bot.gateway.server import WebSocketGateway


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


def _gateway():
    return WebSocketGateway(config=GatewayConfig(session_config=SessionConfig(persist=False)))


@pytest.mark.asyncio
async def test_join_cannot_resume_a_session_belonging_to_another_agent():
    gateway = _gateway()
    gateway._agents.update({"support": object(), "finance": object()})
    session = gateway.create_session("finance", client_id="original")
    socket = FakeSocket()
    gateway._clients["candidate"] = socket

    await gateway._handle_client_message("candidate", {
        "type": "join", "agent_id": "support", "session_id": session.session_id,
    })

    assert gateway._client_sessions.get("candidate") != session.session_id
    assert session.client_id == "original"
    assert socket.sent[-1]["type"] == "error"


@pytest.mark.asyncio
async def test_join_can_resume_a_session_for_the_requested_agent():
    gateway = _gateway()
    gateway._agents["support"] = object()
    session = gateway.create_session("support", client_id="original")
    gateway._clients["candidate"] = FakeSocket()
    await gateway._handle_client_message("candidate", {
        "type": "join", "agent_id": "support", "session_id": session.session_id,
    })
    assert gateway._client_sessions["candidate"] == session.session_id


@pytest.mark.asyncio
async def test_join_rejects_rehydrated_session_for_another_agent(monkeypatch):
    gateway = _gateway()
    gateway._agents["support"] = object()
    foreign = gateway.create_session("finance", client_id="original")
    gateway._sessions.pop(foreign.session_id)
    monkeypatch.setattr(gateway, "resume_or_create_session", lambda **kwargs: (foreign, []))
    socket = FakeSocket()
    gateway._clients["candidate"] = socket
    await gateway._handle_client_message("candidate", {
        "type": "join", "agent_id": "support", "session_id": foreign.session_id,
    })
    assert gateway._client_sessions.get("candidate") != foreign.session_id
    assert foreign.client_id == "original"
    assert socket.sent[-1]["type"] == "error"


@pytest.mark.asyncio
async def test_join_uses_persisted_agent_id_when_snapshot_is_missing():
    from types import SimpleNamespace

    gateway = _gateway()
    gateway._agents["support"] = object()

    class Store:
        def session_exists(self, session_id):
            return session_id == "stored-session"

        def get_session(self, session_id):
            return SimpleNamespace(agent_id="finance", messages=[])

    gateway._session_store = Store()
    socket = FakeSocket()
    gateway._clients["candidate"] = socket
    await gateway._handle_client_message("candidate", {
        "type": "join", "agent_id": "support", "session_id": "stored-session",
    })
    assert "candidate" not in gateway._client_sessions
    assert gateway._sessions["stored-session"].client_id is None
    assert socket.sent[-1]["type"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("frame", ["join", "hello"])
async def test_confined_operator_cannot_resume_record_without_agent_identity(frame):
    from types import SimpleNamespace

    gateway = _gateway()
    gateway._agents["support"] = object()

    class Store:
        def session_exists(self, session_id):
            return session_id == "legacy-session"

        def get_session(self, session_id):
            return SimpleNamespace(agent_id=None, messages=[])

    gateway._session_store = Store()
    gateway._client_agents["candidate"] = ["support"]
    socket = FakeSocket()
    gateway._clients["candidate"] = socket
    await gateway._handle_client_message("candidate", {
        "type": frame, "agent_id": "support", "session_id": "legacy-session",
    })
    assert "candidate" not in gateway._client_sessions
    assert "legacy-session" not in gateway._sessions
    assert socket.sent[-1]["type"] == ("hello_error" if frame == "hello" else "error")


@pytest.mark.asyncio
async def test_unconfined_operator_can_resume_record_without_agent_identity():
    from types import SimpleNamespace

    gateway = _gateway()
    gateway._agents["support"] = object()

    class Store:
        def session_exists(self, session_id):
            return session_id == "legacy-session"

        def get_session(self, session_id):
            return SimpleNamespace(agent_id=None, messages=[])

    gateway._session_store = Store()
    gateway._clients["candidate"] = FakeSocket()
    await gateway._handle_client_message("candidate", {
        "type": "join", "agent_id": "support", "session_id": "legacy-session",
    })
    assert gateway._client_sessions["candidate"] == "legacy-session"
