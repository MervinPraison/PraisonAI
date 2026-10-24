"""Regression tests for #5945: per-call compute paths and api_base screening."""

import asyncio
import json
import shlex

import pytest

from praisonai.capabilities import passthrough as pt
from praisonai.integrations.compute_managed_agent import ComputeManagedAgent, _MARKER


def test_api_base_ipv4_mapped_literal_is_rejected():
    with pytest.raises(ValueError, match="private or restricted"):
        pt._validate_api_base("http://[::ffff:127.0.0.1]")


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

