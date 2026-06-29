"""Real agentic integration test — LLM via /run (AC-3). Skips without API key."""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

pytest.importorskip("praisonaiui")

pytestmark = pytest.mark.skipif(
    os.environ.get("PRAISONAI_LIVE_TESTS", "0") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="Set PRAISONAI_LIVE_TESTS=1 and OPENAI_API_KEY for real agentic test",
)


def test_run_creates_session():
    from praisonai.integration.host_app import build_host_app

    client = TestClient(build_host_app(pages=["chat"]))
    session_id = "agentic-ac3-test"
    response = client.post(
        "/run",
        json={"message": "Reply with exactly: pong", "session_id": session_id},
    )
    assert response.status_code == 200

    sessions = client.get("/sessions").json()
    ids = [s.get("id") or s.get("session_id") for s in sessions.get("sessions", sessions)]
    assert session_id in ids or any(session_id in str(i) for i in ids)
