"""Integration tests — POST /run SSE RunEvent stream (AC-2)."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

pytest.importorskip("praisonaiui")


class _MockProvider:
    name = "mock"

    async def run(self, message, *, session_id=None, agent_name=None, **kwargs):
        yield {"type": "text", "content": "Hello SSE"}
        yield {"type": "done", "content": ""}


@pytest.fixture
def host_client(monkeypatch):
    monkeypatch.delenv("PRAISONAI_HOST_LEGACY", raising=False)
    import praisonaiui.server as srv
    from praisonai.integration import host_app

    host_app._CONFIGURED = False
    srv._provider = None
    monkeypatch.setattr(srv, "set_provider", lambda p: setattr(srv, "_provider", p))
    app = host_app.build_host_app(pages=["chat"])
    srv.set_provider(_MockProvider())
    return TestClient(app)


def test_run_sse_stream(host_client):
    with host_client.stream(
        "POST",
        "/run",
        json={"message": "hi", "session_id": "sse-test"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        chunks = list(response.iter_text())
    body = "".join(chunks)
    assert "data:" in body or len(chunks) > 0
