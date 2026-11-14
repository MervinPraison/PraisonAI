from concurrent.futures import Future, TimeoutError as FuturesTimeoutError
from threading import Event

import pytest

from praisonaiagents.background.job_manager import BackgroundJobManager


@pytest.mark.parametrize('timeout', [None, 5])
def test_task_timeout_error_is_not_rewritten(timeout):
    manager = BackgroundJobManager()
    failure = TimeoutError('provider timed out')

    def fail():
        raise failure

    try:
        job_id = manager.start_job(fail)
        with pytest.raises(TimeoutError) as captured:
            manager.get_result(job_id, timeout=timeout)
        assert captured.value is failure
    finally:
        manager.shutdown()


def test_wait_deadline_is_reported_when_task_is_still_running():
    manager = BackgroundJobManager()
    release = Event()
    try:
        job_id = manager.start_job(lambda: release.wait())
        with pytest.raises(TimeoutError, match='did not complete within'):
            manager.get_result(job_id, timeout=0.01)
    finally:
        release.set()
        manager.shutdown()


def test_deadline_is_not_confused_with_late_task_timeout(monkeypatch):
    manager = BackgroundJobManager()
    future = Future()
    task_error = TimeoutError('provider timed out')
    wait_error = FuturesTimeoutError()

    def wait_then_finish(timeout=None):
        # The deadline was reached, but the job completed before the caller
        # inspected the future. The two exception objects remain distinct.
        future.set_exception(task_error)
        raise wait_error

    monkeypatch.setattr(future, 'result', wait_then_finish)
    manager._futures['race'] = future
    try:
        with pytest.raises(TimeoutError, match='did not complete within') as captured:
            manager.get_result('race', timeout=1)
        assert captured.value.__context__ is wait_error
    finally:
        manager.shutdown()
