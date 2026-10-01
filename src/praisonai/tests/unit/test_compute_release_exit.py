"""Process-exit teardown must finish before the shared bridge stops."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


CHILD = r'''
import asyncio
from pathlib import Path
import sys
from praisonai._async_bridge import current_bridge
from praisonai.integrations.compute_managed_agent import ComputeManagedAgent
from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

marker = Path(sys.argv[1])
mode = sys.argv[2]
if mode == "warm":
    current_bridge().get()

class Provider:
    async def provision(self, config):
        return InstanceInfo(instance_id="exit-instance", status=InstanceStatus.RUNNING,
                            provider="fake")
    async def execute(self, *args):
        return {"exit_code": 0}
    async def shutdown(self, instance_id):
        await asyncio.sleep(60 if mode == "hung" else 0.05)
        with marker.open("a", encoding="utf-8") as output:
            output.write(instance_id + "\n")

backend = ComputeManagedAgent("docker")
backend._provider = Provider()
asyncio.run(backend._ensure())
if mode == "explicit":
    asyncio.run(backend.ashutdown())
elif mode == "gc":
    import gc
    del backend
    gc.collect()
elif mode == "race":
    import threading
    from praisonai.integrations import compute_managed_agent as module

    entered = threading.Event()
    allow_submission = threading.Event()
    original_release = module._release

    def delayed_release(*args, **kwargs):
        entered.set()
        assert allow_submission.wait(5)
        return original_release(*args, **kwargs)

    module._release = delayed_release
    exit_callback = backend._exit_reclaimer
    holder = [backend]
    del backend
    worker = threading.Thread(target=lambda: holder.pop())
    worker.start()
    assert entered.wait(5)
    timer = threading.Timer(0.1, allow_submission.set)
    timer.start()
    try:
        # GC is inside _release but has not published its future yet.
        exit_callback()
        assert marker.exists(), "exit missed the in-progress GC handoff"
    finally:
        allow_submission.set()
        worker.join(5)
        timer.join(5)
'''


def _child(tmp_path, mode):
    root = Path(__file__).resolve().parents[4]
    marker = tmp_path / "released.txt"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(p) for p in (root / "src").iterdir() if p.is_dir()]
        + [env.get("PYTHONPATH", "")]
    )
    env["PRAISONAI_COMPUTE_RELEASE_EXIT_TIMEOUT"] = "0.2" if mode == "hung" else "2"
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(marker), mode], env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return marker, result


@pytest.mark.parametrize("mode", ["warm", "cold", "explicit", "gc", "race"])
def test_exit_reclaims_instance_once(tmp_path, mode):
    marker, result = _child(tmp_path, mode)
    assert marker.exists(), result.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == ["exit-instance"]


def test_hung_exit_release_is_bounded(tmp_path):
    marker, result = _child(tmp_path, "hung")
    assert not marker.exists()
    assert "could not release" in result.stderr
