"""Tenki command results and provider-managed idle shutdown."""

import asyncio
import base64
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from praisonai_sandbox.compute.tenki import TenkiCompute
from praisonaiagents.managed.protocols import ComputeConfig, InstanceStatus


@pytest.fixture
def provider(monkeypatch):
    timers = []

    class SessionNotFoundError(Exception):
        pass

    class SessionTerminatedError(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "tenki",
        SimpleNamespace(
            SessionNotFoundError=SessionNotFoundError,
            SessionTerminatedError=SessionTerminatedError,
        ),
    )

    class Timer:
        def __init__(self, interval, callback, args):
            self.interval = interval
            self.callback = callback
            self.args = args
            self.cancelled = False
            self.started = False
            self.daemon = False
            timers.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def fire(self):
            self.callback(*self.args)

    monkeypatch.setattr("praisonai_sandbox.compute.tenki.threading.Timer", Timer)
    sandbox = Mock(id="sandbox-test", state="RUNNING")
    sandbox.exec.return_value = SimpleNamespace(
        stdout=b"output",
        stderr=b"",
        exit_code=0,
        timed_out=False,
    )
    compute = TenkiCompute(api_key="test", workspace_id="workspace-test")
    compute._client = Mock()
    compute._client.create.return_value = sandbox
    return compute, sandbox, timers


def provision(provider, **kwargs):
    return provider[0]._provision_sync(ComputeConfig(**kwargs)).instance_id


def test_provision_starts_idle_timer_without_deprecated_sdk_option(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider, idle_timeout_s=17)
    assert "idle_timeout_minutes" not in compute._client.create.call_args.kwargs
    assert "max_duration" not in compute._client.create.call_args.kwargs
    assert timers[-1].interval == 17
    assert timers[-1].started and timers[-1].daemon
    timers[-1].fire()
    sandbox.terminate.assert_called_once()
    assert compute._get_status_sync(instance_id).status == InstanceStatus.STOPPED
    assert not compute._sandboxes


def test_auto_shutdown_can_be_disabled(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider, auto_shutdown=False, idle_timeout_s=0)
    compute._execute_sync(instance_id, "true", 30)
    assert not timers
    sandbox.terminate.assert_not_called()
    compute._shutdown_sync(instance_id)
    sandbox.terminate.assert_called_once()


@pytest.mark.parametrize("timeout", [0, -1])
def test_invalid_idle_timeout_fails_before_creating_sandbox(provider, timeout):
    compute, _, _ = provider
    with pytest.raises(ValueError, match="idle_timeout_s"):
        provision(provider, idle_timeout_s=timeout)
    compute._client.create.assert_not_called()


@pytest.mark.parametrize(
    "timed_out,exit_code", [(False, 0), (False, 7), (True, 0), (True, 143)]
)
def test_execute_preserves_output_and_never_reports_timeout_as_success(
    provider, timed_out, exit_code
):
    compute, sandbox, timers = provider
    instance_id = provision(provider)
    previous_timer = timers[-1]
    sandbox.exec.return_value = SimpleNamespace(
        stdout=b"partial\xff",
        stderr=b"diagnostic",
        exit_code=exit_code,
        timed_out=timed_out,
    )
    result = asyncio.run(compute.execute(instance_id, "sleep 10", timeout=1))
    assert result["stdout"] == "partial\ufffd"
    assert result["stderr"] == (
        "diagnostic\nCommand timed out" if timed_out else "diagnostic"
    )
    assert result["exit_code"] == (124 if timed_out else exit_code)
    sandbox.exec.assert_called_once_with("bash", "-lc", "sleep 10", timeout=1)
    assert previous_timer.cancelled
    previous_timer.fire()
    sandbox.terminate.assert_not_called()
    timers[-1].fire()
    sandbox.terminate.assert_called_once()


def test_execute_error_rearms_idle_cleanup(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider)
    sandbox.exec.side_effect = RuntimeError("connection failed")
    assert compute._execute_sync(instance_id, "true", 30)["exit_code"] == -1
    timers[-1].fire()
    sandbox.terminate.assert_called_once()


def test_overlapping_commands_are_not_idle_until_both_finish(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider)
    idle_timer = timers[-1]
    started = [Event(), Event()]
    release = [Event(), Event()]

    def execute(*args, **kwargs):
        index = int(args[-1])
        started[index].set()
        assert release[index].wait(5)
        return SimpleNamespace(stdout=b"done", stderr=b"", exit_code=0, timed_out=False)

    sandbox.exec.side_effect = execute
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(compute._execute_sync, instance_id, "0", 30)
        second = executor.submit(compute._execute_sync, instance_id, "1", 30)
        try:
            assert all(event.wait(5) for event in started)
            idle_timer.fire()
            sandbox.terminate.assert_not_called()
            release[0].set()
            assert first.result(timeout=5)["exit_code"] == 0
            assert len(timers) == 1
            release[1].set()
            assert second.result(timeout=5)["exit_code"] == 0
            assert len(timers) == 2
        finally:
            for event in release:
                event.set()
    timers[-1].fire()
    sandbox.terminate.assert_called_once()


@pytest.mark.parametrize("operation", ["upload", "download"])
@pytest.mark.parametrize("timed_out", [False, True])
def test_file_operations_guard_idle_cleanup_and_reject_timeout(
    provider, tmp_path, operation, timed_out
):
    compute, sandbox, timers = provider
    instance_id = provision(provider)
    previous_timer = timers[-1]
    local = tmp_path / "file.bin"
    local.write_bytes(b"original")

    def execute(*args, **kwargs):
        previous_timer.fire()
        sandbox.terminate.assert_not_called()
        assert previous_timer.cancelled
        return SimpleNamespace(
            stdout=base64.b64encode(b"remote"),
            stderr=b"",
            exit_code=0,
            timed_out=timed_out,
        )

    sandbox.exec.side_effect = execute
    if operation == "upload":
        result = asyncio.run(
            compute.upload_file(instance_id, str(local), "/tmp/file.bin")
        )
    else:
        result = asyncio.run(
            compute.download_file(instance_id, "/tmp/file.bin", str(local))
        )
        assert local.read_bytes() == (b"original" if timed_out else b"remote")
    assert result is not timed_out
    assert len(timers) == 2
    timers[-1].fire()
    sandbox.terminate.assert_called_once()


@pytest.mark.parametrize("manager", ["pip", "npm"])
def test_timed_out_package_install_terminates_half_provisioned_sandbox(
    provider, manager
):
    compute, sandbox, timers = provider
    sandbox.exec.return_value.timed_out = True
    with pytest.raises(RuntimeError, match=f"{manager} install failed"):
        provision(provider, packages={manager: ["example"]})
    sandbox.terminate.assert_called_once()
    assert not compute._sandboxes
    assert not timers


def test_failed_install_cleanup_is_tracked_and_retried_on_idle(provider):
    compute, sandbox, timers = provider
    sandbox.exec.return_value.timed_out = True
    sandbox.terminate.side_effect = [RuntimeError("unavailable"), None]
    with pytest.raises(RuntimeError, match="pip install failed"):
        provision(provider, packages={"pip": ["example"]})
    assert len(compute._sandboxes) == 1
    timers[-1].fire()
    assert not compute._sandboxes
    assert sandbox.terminate.call_count == 2


def test_idle_cleanup_failure_is_retried(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider)
    sandbox.terminate.side_effect = [RuntimeError("unavailable"), None]
    previous_timer = timers[-1]
    previous_timer.fire()
    assert instance_id in compute._sandboxes
    assert len(timers) == 2
    previous_timer.fire()
    assert sandbox.terminate.call_count == 1
    timers[-1].fire()
    assert not compute._sandboxes
    assert sandbox.terminate.call_count == 2


def test_explicit_shutdown_cancels_timer_and_is_idempotent(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider)
    asyncio.run(compute.shutdown(instance_id))
    assert timers[-1].cancelled
    timers[-1].fire()
    asyncio.run(compute.shutdown(instance_id))
    sandbox.terminate.assert_called_once()


def test_explicit_shutdown_failure_retains_instance_and_idle_retry(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider)
    sandbox.terminate.side_effect = [RuntimeError("unavailable"), None]
    with pytest.raises(RuntimeError, match="unavailable"):
        compute._shutdown_sync(instance_id)
    assert instance_id in compute._sandboxes
    timers[-1].fire()
    assert not compute._sandboxes


def test_status_poll_does_not_reset_idle_timeout(provider):
    compute, _, timers = provider
    instance_id = provision(provider)
    assert compute._get_status_sync(instance_id).status == InstanceStatus.RUNNING
    assert len(compute._list_instances_sync()) == 1
    assert len(timers) == 1
    assert not timers[0].cancelled


@pytest.mark.parametrize(
    "error_name", ["SessionNotFoundError", "SessionTerminatedError"]
)
def test_already_gone_sandbox_does_not_retry_idle_shutdown(provider, error_name):
    compute, sandbox, timers = provider
    provision(provider)
    sandbox.terminate.side_effect = getattr(sys.modules["tenki"], error_name)("gone")
    timers[-1].fire()
    assert not compute._sandboxes
    assert len(timers) == 1
    assert timers[0].cancelled


def test_slow_termination_does_not_block_activity_on_other_sandboxes(provider):
    compute, first_sandbox, timers = provider
    first_id = provision(provider)
    second_sandbox = Mock(id="second-sandbox", state="RUNNING")
    second_sandbox.exec.return_value = SimpleNamespace(
        stdout=b"ok",
        stderr=b"",
        exit_code=0,
        timed_out=False,
    )
    compute._client.create.return_value = second_sandbox
    second_id = provision(provider)
    started = Event()
    release = Event()

    def terminate():
        started.set()
        assert release.wait(5)

    first_sandbox.terminate.side_effect = terminate
    with ThreadPoolExecutor(max_workers=2) as executor:
        shutdown = executor.submit(compute._shutdown_sync, first_id)
        try:
            assert started.wait(5)
            command = executor.submit(compute._execute_sync, second_id, "true", 30)
            assert command.result(timeout=2)["exit_code"] == 0
        finally:
            release.set()
            shutdown.result(timeout=5)
    timers[-1].fire()
    assert not compute._sandboxes


def test_shutdown_during_command_does_not_rearm_timer(provider):
    compute, sandbox, timers = provider
    instance_id = provision(provider)

    def execute(*args, **kwargs):
        compute._shutdown_sync(instance_id)
        return SimpleNamespace(stdout=b"", stderr=b"", exit_code=1, timed_out=False)

    sandbox.exec.side_effect = execute
    assert compute._execute_sync(instance_id, "true", 30)["exit_code"] == 1
    assert len(timers) == 1
    assert timers[-1].cancelled
    timers[-1].fire()
    sandbox.terminate.assert_called_once()
