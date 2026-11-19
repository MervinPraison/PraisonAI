"""The dashboard and the Replay viewer follow the shared bind rule.

Loopback binds run keyless but answer only loopback-named, same-site requests.
A non-loopback bind needs a token (``PRAISONAI_DASHBOARD_TOKEN`` /
``PRAISONAI_REPLAY_TOKEN``) and every request must then carry it.
"""
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("starlette")
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

TOKEN = "dashboard-replay-test-token-0123456789"


def _page():
    return Starlette(routes=[Route("/", lambda request: PlainTextResponse("page"))])


@pytest.fixture
def served(monkeypatch):
    """Capture what would be served instead of running uvicorn."""
    seen = {}
    fake = SimpleNamespace(run=lambda app, **kw: seen.update(app=app, **kw))
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    for name in ("PRAISONAI_DASHBOARD_TOKEN", "PRAISONAI_REPLAY_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return seen


# --- Replay viewer -----------------------------------------------------------


@pytest.fixture
def replay(monkeypatch):
    from praisonai.replay import live

    monkeypatch.setattr(live, "replay_app", lambda *a, **k: _page())
    return live


def test_replay_refuses_a_public_bind_without_a_token(served, replay):
    with pytest.raises(ValueError, match="PRAISONAI_REPLAY_TOKEN"):
        replay.watch(host="0.0.0.0", open_browser=False)
    assert "app" not in served


def test_replay_public_bind_enforces_the_token(served, replay, monkeypatch):
    monkeypatch.setenv("PRAISONAI_REPLAY_TOKEN", TOKEN)
    replay.watch(host="0.0.0.0", open_browser=False)
    client = TestClient(served["app"], base_url="http://203.0.113.5:8090")
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"Authorization": f"Bearer {TOKEN}"}).text == "page"


def test_replay_loopback_refuses_a_foreign_page(served, replay):
    replay.watch(host="127.0.0.1", open_browser=False)
    app = served["app"]
    assert TestClient(app, base_url="http://127.0.0.1:8090").get("/").text == "page"
    assert TestClient(app, base_url="http://foreign.example:8090").get("/").status_code == 403


# --- Dashboard ---------------------------------------------------------------


def _run_dashboard(host):
    from praisonai.cli.commands import dashboard

    ctx = SimpleNamespace(invoked_subcommand=None)
    dashboard.unified(ctx, port=3999, host=host, auto_start=False, aiui=False)


def test_dashboard_refuses_a_public_bind_without_a_token(served):
    import typer

    with pytest.raises((typer.Exit, SystemExit)):
        _run_dashboard("0.0.0.0")
    assert "app" not in served


def test_dashboard_public_bind_enforces_the_token(served, monkeypatch):
    monkeypatch.setenv("PRAISONAI_DASHBOARD_TOKEN", TOKEN)
    _run_dashboard("0.0.0.0")
    client = TestClient(served["app"], base_url="http://203.0.113.5:3999")
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_dashboard_loopback_refuses_a_foreign_page(served):
    _run_dashboard("127.0.0.1")
    app = served["app"]
    assert TestClient(app, base_url="http://127.0.0.1:3999").get("/health").status_code == 200
    assert TestClient(app, base_url="http://foreign.example:3999").get("/health").status_code == 403


def test_replay_view_cli_follows_the_bind_rule(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from praisonai.cli.commands import replay as replay_cli

    spawned = []
    monkeypatch.setenv("PRAISONAI_TRACES_DIR", str(tmp_path))
    monkeypatch.delenv("PRAISONAI_REPLAY_TOKEN", raising=False)
    monkeypatch.setattr(replay_cli, "_aiui_installed", lambda: True)
    monkeypatch.setattr(replay_cli, "_open_browser", lambda *a: None)
    monkeypatch.setattr(replay_cli, "_spawn_aiui", lambda *a: spawned.append(a) or SimpleNamespace(
        wait=lambda: 0, poll=lambda: 0))

    refused = CliRunner().invoke(replay_cli.app, ["view", "--host", "0.0.0.0"])
    assert refused.exit_code == 1 and spawned == []

    monkeypatch.setenv("PRAISONAI_REPLAY_TOKEN", TOKEN)
    served = CliRunner().invoke(replay_cli.app, ["view", "--host", "0.0.0.0"])
    assert served.exit_code == 0, served.output
    env = spawned[0][3]
    assert env["AIUI_URL_TOKEN"] == TOKEN and env["AIUI_REQUIRE_TOKEN"] == "1"
