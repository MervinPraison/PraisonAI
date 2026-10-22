"""Regression tests for #5945: api_base SSRF screen and per-call compute paths."""

import asyncio
import json
import socket
import shlex

import pytest

from praisonai.capabilities import passthrough as pt
from praisonai.integrations.compute_managed_agent import ComputeManagedAgent, _MARKER


def _fake_resolve(ip):
    def getaddrinfo(host, port, *a, **k):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]
    return getaddrinfo


@pytest.mark.parametrize("ip", [
    "169.254.169.254", "10.0.0.5", "127.0.0.1", "::ffff:127.0.0.1", "0.0.0.0", "224.0.0.1",
])
def test_api_base_hostname_resolving_to_private_is_rejected(monkeypatch, ip):
    monkeypatch.setattr(pt.socket, "getaddrinfo", _fake_resolve(ip))
    with pytest.raises(ValueError, match="private/internal"):
        pt._validate_api_base("http://metadata.google.internal")


def test_api_base_ipv4_mapped_literal_is_rejected():
    with pytest.raises(ValueError, match="private/internal"):
        pt._validate_api_base("http://[::ffff:127.0.0.1]")


def test_api_base_public_host_is_allowed(monkeypatch):
    monkeypatch.setattr(pt.socket, "getaddrinfo", _fake_resolve("104.18.6.192"))
    assert pt._validate_api_base("https://api.example.com") == "https://api.example.com"


def test_api_base_bad_scheme_and_unresolvable(monkeypatch):
    with pytest.raises(ValueError, match="scheme"):
        pt._validate_api_base("file:///etc/passwd")

    def fail(*a, **k):
        raise socket.gaierror("nope")
    monkeypatch.setattr(pt.socket, "getaddrinfo", fail)
    with pytest.raises(ValueError, match="resolved"):
        pt._validate_api_base("https://does-not-exist.invalid")


class _FakeFS:
    """A provider whose 'filesystem' is a dict, driven through execute()."""

    def __init__(self):
        self.files = {}
        self.commands = []

    async def execute(self, instance, cmd, timeout):
        self.commands.append(cmd)
        if cmd.startswith("cat > "):
            head, body = cmd.split("\n", 1)
            path = shlex.split(head[len("cat > "):].split(" <<")[0])[0]
            self.files[path] = body.rsplit("\n", 2)[0]
            await asyncio.sleep(0)
            return {"exit_code": 0}
        if cmd.startswith("python "):
            _, _runner, payload_path = shlex.split(cmd)
            await asyncio.sleep(0.01)   # let the other call interleave
            prompt = json.loads(self.files[payload_path])["prompt"]
            out = {"ok": True, "result": f"answer:{prompt}"}
            return {"stdout": _MARKER + json.dumps(out), "exit_code": 0}
        if cmd.startswith("rm -f "):
            for path in shlex.split(cmd)[2:]:
                self.files.pop(path, None)
            return {"exit_code": 0}
        return {"exit_code": 0}


def test_concurrent_execute_on_warm_instance_keeps_payloads_apart():
    agent = ComputeManagedAgent("fake")
    fs = _FakeFS()
    agent._provider, agent._instance, agent._prepared = fs, "inst", True

    async def run():
        return await asyncio.gather(agent.execute("A"), agent.execute("B"))

    assert asyncio.run(run()) == ["answer:A", "answer:B"]
    assert fs.files == {}  # per-call files cleaned up
    assert not any("dd" in c.split("\n", 1)[0] for c in fs.commands if c.startswith("python "))


def test_async_fallback_validates_api_base_off_event_loop(monkeypatch):
    import threading
    loop_thread = threading.get_ident()
    seen = []

    def getaddrinfo(host, port, *a, **k):
        seen.append(threading.get_ident())
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]

    class _NoRoute:
        pass  # no allm_passthrough_route -> AttributeError -> httpx fallback

    monkeypatch.setattr(pt.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setitem(__import__("sys").modules, "litellm", _NoRoute())
    with pytest.raises(ValueError, match="private/internal"):
        asyncio.run(pt.apassthrough("/v1/x", api_base="http://internal.example"))
    assert seen and seen[0] != loop_thread
