"""`stop` must kill the work, not just the pid it wrote down.

The recorded pid is the wrapper shell; the real fine-tune is its children
(dataloader workers, torchrun ranks), which share its process group. Signalling
the pid alone leaves them running on the GPU, reparented to init.

There are no remote tests that exercise a real process, so the transport is a
fake host whose ``run`` executes the script locally under ``/bin/sh``. That is
enough to launch a script that spawns a child, call ``stop``, and assert **the
child is gone** -- not merely that ``stop`` returned True, which is exactly the
assertion that let the original defect through.
"""

import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from praisonai_train.remote.runner import (  # noqa: E402
    RemoteError,
    RemoteRun,
    RemoteRunner,
    _Completed,
)


class LocalHost:
    """A host whose commands run here, in a shell, instead of over ssh."""

    def __init__(self, alias="local"):
        self.alias = alias

    def run(self, command, timeout=None):
        proc = subprocess.run(
            ["/bin/sh", "-c", command],
            capture_output=True, text=True, timeout=timeout,
        )
        return _Completed(proc.returncode, proc.stdout or "", proc.stderr or "")


def _runner_over(host):
    runner = RemoteRunner.__new__(RemoteRunner)
    runner.host = host
    return runner


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _launch_wrapper_with_child(tmp_path, host):
    """Reproduce the launch shape: a wrapper shell whose child is the work.

    Mirrors ``_launch_script`` -- a backgrounded ``sh -c`` whose recorded pid is
    the wrapper, with the actual work a child of it -- without invoking the
    trainer. The child writes its own pid so the test can watch it directly.
    """
    remote_dir = str(tmp_path)
    run = RemoteRun(
        host=host.alias, run_id="run-test", remote_dir=remote_dir,
        log_path=f"{remote_dir}/train.log",
    )
    child_pidfile = f"{remote_dir}/child.pid"
    inner = (
        f"nohup sh -c 'echo $$ > {child_pidfile}; "
        f"sleep 120' >/dev/null 2>&1 & "
        f"echo $! > {run.pid_path}"
    )
    script = (
        f"cd {remote_dir} && "
        f"if command -v setsid >/dev/null 2>&1; then "
        f"setsid sh -c {_sh_quote(inner)}; else {inner}; fi"
    )
    host.run(script)
    # Give the backgrounded child a moment to record its pid.
    for _ in range(50):
        if pathlib.Path(child_pidfile).exists():
            break
        time.sleep(0.05)
    child_pid = int(pathlib.Path(child_pidfile).read_text().strip())
    return run, child_pid


def _sh_quote(s):
    import shlex
    return shlex.quote(s)


def _has_setsid():
    import shutil
    return shutil.which("setsid") is not None


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals only")
class TestStopKillsTheWork:
    def test_the_child_is_gone_after_stop(self, tmp_path):
        host = LocalHost()
        runner = _runner_over(host)
        run, child_pid = _launch_wrapper_with_child(tmp_path, host)

        assert _alive(child_pid), "the child never started; test is inconclusive"

        assert runner.stop(run) is True
        # The whole point: not the return value, the child.
        deadline = time.time() + 5
        while _alive(child_pid) and time.time() < deadline:
            time.sleep(0.05)
        assert not _alive(child_pid), (
            f"child {child_pid} survived stop -- work is still on the GPU")

    def test_stop_reports_false_when_nothing_is_running(self, tmp_path):
        host = LocalHost()
        runner = _runner_over(host)
        remote_dir = str(tmp_path)
        run = RemoteRun(host="local", run_id="run-none",
                        remote_dir=remote_dir,
                        log_path=f"{remote_dir}/train.log")
        # No pid file at all.
        assert runner.stop(run) is False

    def test_stop_reports_false_for_a_dead_pid(self, tmp_path):
        host = LocalHost()
        runner = _runner_over(host)
        remote_dir = str(tmp_path)
        run = RemoteRun(host="local", run_id="run-dead",
                        remote_dir=remote_dir,
                        log_path=f"{remote_dir}/train.log")
        # Spawn and reap a process so its pid is certainly dead.
        dead = subprocess.Popen(["/bin/sh", "-c", "true"])
        dead.wait()
        pathlib.Path(run.pid_path).write_text(str(dead.pid))
        assert runner.stop(run) is False

    def test_stop_does_not_lie_when_a_child_survives_after_wrapper_exits(
        self, tmp_path
    ):
        # The defect one level up: the recorded wrapper exits promptly, but a
        # child in the same group traps SIGTERM and lives on. Probing only the
        # wrapper pid would report `stopped` while the child keeps the GPU.
        if not _has_setsid():
            pytest.skip("setsid required to isolate the run's process group")
        host = LocalHost()
        runner = _runner_over(host)
        remote_dir = str(tmp_path)
        run = RemoteRun(host="local", run_id="run-orphan",
                        remote_dir=remote_dir,
                        log_path=f"{remote_dir}/train.log")
        child_pidfile = f"{remote_dir}/child.pid"
        # A child that traps SIGTERM, records its own pid, then outlives its
        # wrapper: the wrapper backgrounds it and exits at once, so only the
        # child remains in the group after `stop` signals it.
        inner = (
            f"nohup sh -c 'trap \"\" TERM; echo $$ > {child_pidfile}; "
            f"sleep 120' >/dev/null 2>&1 & "
            f"echo $! > {run.pid_path}"
        )
        host.run(f"cd {remote_dir} && setsid sh -c {_sh_quote(inner)}")
        for _ in range(50):
            if pathlib.Path(child_pidfile).exists():
                break
            time.sleep(0.05)
        child_pid = int(pathlib.Path(child_pidfile).read_text().strip())
        try:
            assert _alive(child_pid), "child never started; test inconclusive"
            with pytest.raises(RemoteError, match="did not stop"):
                runner.stop(run)
            assert _alive(child_pid), "child should have survived SIGTERM"
        finally:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except OSError:
                pass

    def test_stop_raises_when_the_process_ignores_sigterm(self, tmp_path):
        host = LocalHost()
        runner = _runner_over(host)
        remote_dir = str(tmp_path)
        run = RemoteRun(host="local", run_id="run-stubborn",
                        remote_dir=remote_dir,
                        log_path=f"{remote_dir}/train.log")
        # A process in its own group that traps SIGTERM: stop must not lie.
        stubborn = subprocess.Popen(
            ["/bin/sh", "-c", "trap '' TERM; while true; do sleep 1; done"],
            preexec_fn=os.setsid,
        )
        try:
            pathlib.Path(run.pid_path).write_text(str(stubborn.pid))
            with pytest.raises(RemoteError, match="did not stop"):
                runner.stop(run)
            assert _alive(stubborn.pid)
        finally:
            os.killpg(os.getpgid(stubborn.pid), signal.SIGKILL)
            stubborn.wait()
