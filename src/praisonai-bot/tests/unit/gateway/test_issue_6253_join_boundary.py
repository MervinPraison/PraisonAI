import pytest

from praisonaiagents.gateway import GatewayConfig
from praisonai_bot.gateway.server import WebSocketGateway


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_join_cannot_resume_a_session_belonging_to_another_agent():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="test-token"))
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
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="test-token"))
    gateway._agents["support"] = object()
    session = gateway.create_session("support", client_id="original")
    gateway._clients["candidate"] = FakeSocket()
    await gateway._handle_client_message("candidate", {
        "type": "join", "agent_id": "support", "session_id": session.session_id,
    })
    assert gateway._client_sessions["candidate"] == session.session_id


@pytest.mark.asyncio
async def test_join_rejects_rehydrated_session_for_another_agent(monkeypatch):
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="test-token"))
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
