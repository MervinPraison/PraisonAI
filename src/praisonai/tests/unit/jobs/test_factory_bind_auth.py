"""Jobs API applies the same keyless-bind check on the ``--factory`` path.

``uvicorn praisonai.jobs.server:create_app --factory --host X`` never sets
``PRAISONAI_JOBS_BIND_HOST``; a request that reaches a non-loopback socket
address must still be refused without ``PRAISONAI_JOBS_API_KEY``.
"""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from praisonai.jobs.executor import JobExecutor
from praisonai.jobs.server import create_app
from praisonai.jobs.store import InMemoryJobStore


@pytest.fixture
def factory_app(monkeypatch):
    def _make(api_key=None):
        monkeypatch.delenv("PRAISONAI_JOBS_BIND_HOST", raising=False)
        if api_key:
            monkeypatch.setenv("PRAISONAI_JOBS_API_KEY", api_key)
        else:
            monkeypatch.delenv("PRAISONAI_JOBS_API_KEY", raising=False)
        store = InMemoryJobStore(max_jobs=10)
        return create_app(store=store, executor=JobExecutor(store=store, max_concurrent=1))

    return _make


def test_keyless_request_on_lan_address_is_refused(factory_app):
    client = TestClient(factory_app(), base_url="http://10.0.0.5:8005")
    assert client.get("/api/v1/runs").status_code == 401
    # Liveness probe stays open.
    assert client.get("/health").status_code == 200


def test_keyless_factory_refuses_even_loopback_requests(factory_app):
    """The factory cannot know its bind host: keyless, it serves nothing."""
    client = TestClient(factory_app(), base_url="http://127.0.0.1:8005")
    assert client.get("/api/v1/runs").status_code == 401
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("server, off_loopback", [
    (("10.0.0.5", 8005), True),
    (("fd00::5", 8005), True),
    (("127.0.0.1", 8005), False),
    (("::1", 8005), False),
    (("::ffff:127.0.0.1", 8005), False),
    (None, False),  # unix socket
])
def test_socket_address_classification(server, off_loopback):
    # The test client cannot carry an IPv6 server address, so check the
    # classifier the middleware uses directly.
    from types import SimpleNamespace

    from praisonai.jobs.server import _arrived_off_loopback

    assert _arrived_off_loopback(SimpleNamespace(scope={"server": server})) is off_loopback


def test_api_key_unlocks_lan_address(factory_app):
    client = TestClient(factory_app(api_key="k-123"), base_url="http://10.0.0.5:8005")
    assert client.get("/api/v1/runs").status_code == 401
    ok = client.get("/api/v1/runs", headers={"Authorization": "Bearer k-123"})
    assert ok.status_code == 200


@pytest.mark.parametrize("declared, local_ok", [
    (None, False),          # uvicorn --factory: nothing declared
    ("0.0.0.0", False),     # start_server(host="0.0.0.0") declares a public bind
    ("127.0.0.1", True),    # start_server() default / declared loopback
])
def test_one_keyless_rule_for_every_launch_path(factory_app, monkeypatch, declared, local_ok):
    """start_server() and the factory answer the same requests for the same
    declared bind: keyless, only a declared loopback bind serves, and only
    to requests that reached a loopback address."""
    factory_app()  # clears env
    if declared:
        monkeypatch.setenv("PRAISONAI_JOBS_BIND_HOST", declared)
    app = create_app(store=InMemoryJobStore(max_jobs=1))
    local = TestClient(app, base_url="http://127.0.0.1:8005")
    lan = TestClient(app, base_url="http://10.0.0.5:8005")
    assert (local.get("/api/v1/runs").status_code == 200) is local_ok
    assert lan.get("/api/v1/runs").status_code == 401


def test_start_server_refuses_keyless_public_bind(monkeypatch):
    monkeypatch.delenv("PRAISONAI_JOBS_API_KEY", raising=False)
    from unittest.mock import patch

    from praisonai.jobs.server import start_server

    with patch("uvicorn.run") as run:
        with pytest.raises(ValueError, match="PRAISONAI_JOBS_API_KEY"):
            start_server(host="0.0.0.0")
    run.assert_not_called()


def test_start_server_public_bind_with_key_starts(monkeypatch):
    monkeypatch.setenv("PRAISONAI_JOBS_API_KEY", "k-123")
    from unittest.mock import patch

    from praisonai.jobs.server import start_server

    with patch("uvicorn.run") as run:
        start_server(host="0.0.0.0")
    assert run.call_args.kwargs["host"] == "0.0.0.0"
