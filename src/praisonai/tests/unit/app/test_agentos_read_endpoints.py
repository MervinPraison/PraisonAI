"""AgentOS can be inspected over HTTP.

It could list agents and take a chat turn, and nothing else: a session could not
be replayed, a run inspected, or a pending approval seen -- even though the
protocols to expose all three already existed.
"""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from praisonai.app.agentos import AgentOS  # noqa: E402


def _client(**attrs):
    os_ = AgentOS(agents=[], name="demo")
    for key, value in attrs.items():
        setattr(os_, key, value)
    return TestClient(os_.get_app())


class FakeRun:
    def __init__(self, run_id, status="done"):
        self.run_id = run_id
        self.status = status
        self.agent = "researcher"


class FakeLedger:
    def __init__(self, runs):
        self._runs = runs

    def list_all(self, limit=200):
        return self._runs[:limit]

    def get(self, run_id):
        return next((r for r in self._runs if r.run_id == run_id), None)


class FakeSessionStore:
    def __init__(self, history):
        self._history = history

    def recent(self, limit=10):
        return [{"session_id": "s1", "messages": len(self._history)}][:limit]

    def session_exists(self, session_id):
        return session_id == "s1"

    def get_chat_history(self, session_id, max_messages=None):
        return self._history


class TestMissingStoresFailLoudly:
    """503 rather than [] -- an empty list is indistinguishable from 'none yet'."""

    @pytest.mark.parametrize("path", ["/api/runs", "/api/sessions"])
    def test_absent_store_returns_503_naming_what_to_configure(self, path):
        response = _client().get(path)
        assert response.status_code == 503
        assert "configured" in response.json()["detail"]

    def test_control_pre_existing_routes_are_unchanged(self):
        client = _client()
        assert client.get("/health").status_code == 200
        assert client.get("/api/agents").status_code == 200


class TestRuns:
    def test_runs_are_listed_when_a_ledger_is_attached(self):
        client = _client(run_ledger=FakeLedger([FakeRun("r1"), FakeRun("r2")]))
        body = client.get("/api/runs").json()
        assert body["count"] == 2
        assert {r["run_id"] for r in body["runs"]} == {"r1", "r2"}

    def test_a_single_run_can_be_fetched(self):
        client = _client(run_ledger=FakeLedger([FakeRun("r1")]))
        assert client.get("/api/runs/r1").json()["run_id"] == "r1"

    def test_an_unknown_run_is_404_not_an_empty_object(self):
        client = _client(run_ledger=FakeLedger([FakeRun("r1")]))
        assert client.get("/api/runs/nope").status_code == 404

    def test_limit_is_honoured(self):
        client = _client(run_ledger=FakeLedger([FakeRun(f"r{i}") for i in range(5)]))
        assert client.get("/api/runs?limit=2").json()["count"] == 2


class TestSessions:
    def test_a_session_can_be_replayed(self):
        history = [{"role": "user", "content": "hi"}]
        client = _client(session_store=FakeSessionStore(history))
        body = client.get("/api/sessions/s1").json()
        assert body["session_id"] == "s1"
        assert body["messages"] == history

    def test_an_unknown_session_is_404(self):
        client = _client(session_store=FakeSessionStore([]))
        assert client.get("/api/sessions/nope").status_code == 404

    def test_sessions_are_listed(self):
        client = _client(session_store=FakeSessionStore([{"role": "user", "content": "hi"}]))
        assert client.get("/api/sessions").json()["count"] == 1

    def test_store_without_session_exists_treats_empty_history_as_404(self):
        # A store that cannot answer session_exists must not report an unknown
        # id as a healthy 200 with an empty transcript.
        client = _client(session_store=HistoryOnlyStore({"s1": [{"role": "user", "content": "hi"}]}))
        assert client.get("/api/sessions/s1").status_code == 200
        assert client.get("/api/sessions/nope").status_code == 404


class TestBoundedLimits:
    """Client-controlled limits are bounded -- a negative value must not remove
    the SQL LIMIT (SQLite treats LIMIT -1 as unlimited)."""

    @pytest.mark.parametrize(
        "path", ["/api/runs?limit=-1", "/api/runs?limit=0", "/api/runs?limit=99999"]
    )
    def test_out_of_range_run_limit_is_rejected(self, path):
        client = _client(run_ledger=FakeLedger([FakeRun("r1")]))
        assert client.get(path).status_code == 422

    def test_out_of_range_session_limit_is_rejected(self):
        client = _client(session_store=FakeSessionStore([]))
        assert client.get("/api/sessions?limit=-1").status_code == 422


class TestApprovals:
    def test_configured_requirements_are_listed(self):
        from praisonaiagents.approval import get_approval_registry

        registry = get_approval_registry()
        registry.add_requirement("delete_file", risk_level="high")
        try:
            body = _client().get("/api/approvals").json()
            tools = {r["tool"]: r["risk_level"] for r in body["requirements"]}
            assert tools.get("delete_file") == "high"
        finally:
            registry.remove_requirement("delete_file")


class HistoryOnlyStore:
    """A session store that exposes only get_chat_history (no session_exists)."""

    def __init__(self, histories):
        self._histories = histories

    def get_chat_history(self, session_id, max_messages=None):
        return self._histories.get(session_id, [])
