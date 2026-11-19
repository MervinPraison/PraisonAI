"""HTTPApproval binds through the shared bind guard.

Without ``allowed_approvers`` there is no per-approval token and any visitor
may decide, so only a loopback bind is allowed.
"""

import asyncio

import pytest

pytest.importorskip("aiohttp")

from praisonai_bot.bots._http_approval import HTTPApproval


class _Bound(Exception):
    pass


@pytest.fixture
def sites(monkeypatch):
    monkeypatch.delenv("HTTP_APPROVERS", raising=False)
    from aiohttp import web

    hosts = []

    class FakeSite:
        def __init__(self, runner, host, port, **kw):
            hosts.append(host)

        async def start(self):
            raise _Bound()

    monkeypatch.setattr(web, "TCPSite", FakeSite)
    return hosts


def test_keyless_public_bind_refuses(sites):
    with pytest.raises(ValueError, match="allowed_approvers"):
        asyncio.run(HTTPApproval(host="0.0.0.0")._ensure_server())
    assert sites == []


def test_loopback_default_starts(sites):
    with pytest.raises(_Bound):
        asyncio.run(HTTPApproval()._ensure_server())
    assert sites == ["127.0.0.1"]


def test_public_bind_with_allowlist_starts(sites):
    with pytest.raises(_Bound):
        asyncio.run(HTTPApproval(host="0.0.0.0", allowed_approvers=["alice"])._ensure_server())
    assert sites == ["0.0.0.0"]
