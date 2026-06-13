"""Multi-agent session isolation test (AC-9)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

pytest.importorskip("praisonaiui")


class _SessionProvider:
    name = "mock"

    def __init__(self):
        self._sessions = {}

    async def run(self, message, *, session_id=None, agent_name=None, **kwargs):
        sid = session_id or "default"
        self._sessions.setdefault(sid, []).append(message)
        reply = f"echo:{message}"
        yield {"type": "text", "content": reply}
        yield {"type": "done", "content": ""}


@pytest.fixture
def isolated_client(monkeypatch):
    monkeypatch.delenv("PRAISONAI_HOST_LEGACY", raising=False)
    import praisonaiui.server as srv
    from praisonai.integration import host_app

    host_app.reset_configuration()
    provider = _SessionProvider()
    monkeypatch.setattr(srv, "set_provider", lambda p: setattr(srv, "_provider", p))
    app = host_app.build_host_app(pages=["chat"])
    srv.set_provider(provider)
    return TestClient(app), provider


def test_two_sessions_no_cross_leak(isolated_client):
    client, provider = isolated_client
    client.post("/run", json={"message": "secret-a", "session_id": "sess-a"})
    client.post("/run", json={"message": "secret-b", "session_id": "sess-b"})
    assert provider._sessions.get("sess-a") == ["secret-a"]
    assert provider._sessions.get("sess-b") == ["secret-b"]
    assert "secret-b" not in provider._sessions.get("sess-a", [])
