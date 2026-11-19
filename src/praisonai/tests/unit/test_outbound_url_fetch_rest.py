"""Jobs webhooks and the replay judge use the SDK's pinned fetch (url_safety).

``rebind.test`` answers a public address for the first lookups and 127.0.0.1
after that; a loopback server plays the internal service. No test touches the
network (the conftest egress guard refuses the public address).
"""
from __future__ import annotations

import asyncio
import http.server
import socket
import sys
import threading

import pytest

pytest.importorskip("httpx")

PUBLIC = "93.184.216.34"


@pytest.fixture(autouse=True)
def _no_opt_outs(monkeypatch):
    for name in ("ALLOW_LOCAL_CRAWL", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def internal():
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _hit(self):
            hits.append(self.path)
            body = b"<html><body>INTERNAL-ONLY-CANARY</body></html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _hit

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, hits
    server.shutdown()
    server.server_close()
    thread.join()


def _rebind(monkeypatch, public_lookups):
    real = socket.getaddrinfo
    calls = []

    def resolve(name, port=None, *args, **kwargs):
        if name != "rebind.test":
            return real(name, port, *args, **kwargs)
        calls.append(name)
        ip = PUBLIC if len(calls) <= public_lookups else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, int(port or 0)))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def _finished_job(url):
    from praisonai.jobs.models import Job, JobStatus

    job = Job(prompt="x")
    job.webhook_url = url  # set after construction: the submit-time check is not under test
    job.status = JobStatus.SUCCEEDED
    job.result = "SECRET-RESULT"
    return job


def test_webhook_delivery_refuses_rebound_target(monkeypatch, internal):
    from praisonai.jobs.executor import JobExecutor

    port, hits = internal
    _rebind(monkeypatch, public_lookups=0)
    asyncio.run(JobExecutor(store=None)._send_webhook(_finished_job(f"http://rebind.test:{port}/hook")))
    assert hits == []


def test_webhook_delivery_uses_shared_helper(monkeypatch):
    from praisonai.jobs.executor import JobExecutor
    from praisonaiagents.tools import url_safety

    seen = {}

    def fake_fetch(url, **kwargs):
        seen.update(kwargs, url=url)
        raise url_safety.UnsafeURLError("stop")

    monkeypatch.setattr(url_safety, "safe_fetch", fake_fetch)
    asyncio.run(JobExecutor(store=None)._send_webhook(_finished_job("https://hooks.example.com/x")))
    assert seen["url"] == "https://hooks.example.com/x"
    assert seen["method"] == "POST" and seen["allow_local"] is False
    assert seen["json"]["result"] == "SECRET-RESULT"


def test_replay_judge_fallback_is_checked(monkeypatch, internal):
    import praisonaiagents.tools as tools_pkg
    from praisonai.replay.judge import _crawl_url_for_judge

    port, hits = internal
    _rebind(monkeypatch, public_lookups=0)
    # Force the fallback path: web_crawl unavailable.
    def _missing(name):
        raise ImportError(name)

    monkeypatch.setattr(tools_pkg, "__getattr__", _missing, raising=False)
    if "web_crawl" in vars(tools_pkg):
        monkeypatch.delitem(vars(tools_pkg), "web_crawl")
    monkeypatch.setitem(sys.modules, "praisonaiagents.tools.web_crawl_tools", None)
    out = _crawl_url_for_judge(f"http://rebind.test:{port}/page")
    assert "INTERNAL-ONLY-CANARY" not in out
    assert hits == []
