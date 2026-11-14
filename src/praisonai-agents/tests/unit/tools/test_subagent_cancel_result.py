from concurrent.futures import CancelledError
from threading import Event, Thread

import pytest

from praisonaiagents.background import job_manager
from praisonaiagents.background.job_manager import BackgroundJobManager, JobInfo, JobStatus
from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore
from praisonaiagents.tools.subagent_tool import create_subagent_tool


@pytest.mark.parametrize('cancel_pending', [False, True])
def test_spawned_cancelled_job_has_same_wait_and_poll_result(monkeypatch, cancel_pending):
    manager = BackgroundJobManager(max_workers=1)
    monkeypatch.setattr(job_manager, 'get_job_manager', lambda: manager)
    entered, release = Event(), Event()

    class Agent:
        def chat(self, prompt):
            entered.set()
            assert release.wait(5)
            return 'done'

    tool = create_subagent_tool(agent_factory=lambda **kwargs: Agent())
    spawn = tool['function']
    result = tool['result_tool']['function']
    try:
        first = spawn(task='running', background=True)['job_id']
        assert entered.wait(5)
        job_id = spawn(task='queued', background=True)['job_id'] if cancel_pending else first
        assert manager.cancel_job(job_id)
        expected = {'success': True, 'job_id': job_id, 'status': 'cancelled'}
        assert result(job_id, wait=False) == expected
        assert result(job_id, wait=True) == expected
    finally:
        release.set()
        manager.shutdown()


@pytest.mark.parametrize('error', [ValueError('bad task'), CancelledError('task error'), KeyError('task key')])
def test_failed_job_remains_failed_for_wait_and_poll(monkeypatch, error):
    manager = BackgroundJobManager()
    monkeypatch.setattr(job_manager, 'get_job_manager', lambda: manager)
    result = create_subagent_tool()['result_tool']['function']

    def fail():
        raise error

    try:
        job_id = manager.start_job(fail)
        waited = result(job_id, wait=True)
        polled = result(job_id, wait=False)
        assert waited == polled
        assert waited['success'] is False
        assert waited['status'] == 'failed'
        assert waited['error'] == str(error)
    finally:
        manager.shutdown()


def test_unknown_job_has_same_wait_and_poll_result(monkeypatch):
    manager = BackgroundJobManager()
    monkeypatch.setattr(job_manager, 'get_job_manager', lambda: manager)
    result = create_subagent_tool()['result_tool']['function']
    try:
        assert result('missing', wait=True) == result('missing', wait=False)
        assert result('missing', wait=True)['success'] is False
    finally:
        manager.shutdown()


@pytest.mark.parametrize('status', [JobStatus.COMPLETED, JobStatus.FAILED,
                                    JobStatus.CANCELLED, JobStatus.LOST])
def test_wait_and_poll_use_same_persisted_terminal_status(monkeypatch, status):
    store = SqliteBackgroundJobStore(':memory:')
    store.upsert(JobInfo(job_id='saved', status=status, result='result', error='failure'))
    manager = BackgroundJobManager(store=store)
    monkeypatch.setattr(job_manager, 'get_job_manager', lambda: manager)
    result = create_subagent_tool()['result_tool']['function']
    try:
        assert result('saved', wait=True) == result('saved', wait=False)
        assert result('saved', wait=True)['status'] == status.value
    finally:
        manager.shutdown()
        store.close()


def test_cancelled_wait_reports_original_job_if_id_is_reused(monkeypatch):
    manager = BackgroundJobManager(max_workers=1)
    monkeypatch.setattr(job_manager, 'get_job_manager', lambda: manager)
    entered, release = Event(), Event()

    class Agent:
        def chat(self, prompt):
            entered.set()
            assert release.wait(5)
            return 'done'

    tool = create_subagent_tool(agent_factory=lambda **kwargs: Agent())
    original_snapshot = manager._get_job_snapshot
    try:
        job_id = tool['function'](task='old', background=True)['job_id']
        assert entered.wait(5)
        assert manager.cancel_job(job_id)

        def reuse_after_snapshot(requested):
            snapshot = original_snapshot(requested)
            manager.start_job(lambda: 'replacement', job_id=requested)
            return snapshot

        monkeypatch.setattr(manager, '_get_job_snapshot', reuse_after_snapshot)
        assert tool['result_tool']['function'](job_id, wait=True) == {
            'success': True, 'job_id': job_id, 'status': 'cancelled'
        }
        assert manager.get_job_info(job_id).status.value == 'pending'
    finally:
        release.set()
        manager.shutdown()


def test_waiter_reports_cancellation_while_it_is_waiting(monkeypatch):
    manager = BackgroundJobManager(max_workers=1)
    monkeypatch.setattr(job_manager, 'get_job_manager', lambda: manager)
    entered, release, waiting = Event(), Event(), Event()

    class Agent:
        def chat(self, prompt):
            entered.set()
            assert release.wait(5)
            return 'done'

    tool = create_subagent_tool(agent_factory=lambda **kwargs: Agent())
    responses = []
    thread = None
    try:
        job_id = tool['function'](task='running', background=True)['job_id']
        assert entered.wait(5)

        future = manager._futures[job_id]
        original_result = future.result

        def signal_wait(timeout=None):
            waiting.set()
            return original_result(timeout=timeout)

        monkeypatch.setattr(future, 'result', signal_wait)
        thread = Thread(target=lambda: responses.append(tool['result_tool']['function'](job_id, wait=True)))
        thread.start()
        assert waiting.wait(5)
        assert manager.cancel_job(job_id)
        thread.join(5)
        assert not thread.is_alive()
        assert responses == [{'success': True, 'job_id': job_id, 'status': 'cancelled'}]
    finally:
        release.set()
        if thread is not None:
            thread.join(5)
        manager.shutdown()


@pytest.mark.parametrize('error', [CancelledError('replacement error'), KeyError('replacement key')])
def test_reuse_between_status_and_future_lookup_keeps_generation_consistent(monkeypatch, error):
    manager = BackgroundJobManager(max_workers=2)
    monkeypatch.setattr(job_manager, 'get_job_manager', lambda: manager)
    entered, release = Event(), Event()
    replacement_entered, replacement_release = Event(), Event()
    responses = []
    waiter = None
    tool = create_subagent_tool()
    original_lock = manager._lock

    def old_work():
        entered.set()
        assert release.wait(5)

    def fail():
        replacement_entered.set()
        assert replacement_release.wait(5)
        raise error

    try:
        job_id = manager.start_job(old_work, job_id='reused')
        assert entered.wait(5)
        assert manager.cancel_job(job_id)

        class ReplaceAfterFirstLookup:
            armed = True

            def __enter__(self):
                original_lock.acquire()
                return self

            def __exit__(self, *args):
                original_lock.release()
                if self.armed:
                    self.armed = False
                    manager.start_job(fail, job_id=job_id)
                    assert replacement_entered.wait(5)

        monkeypatch.setattr(manager, '_lock', ReplaceAfterFirstLookup())
        result = tool['result_tool']['function']
        # The wait captured the old cancelled job. After that atomic snapshot,
        # the replacement may fail without changing the old result's meaning.
        waiter = Thread(target=lambda: responses.append(result(job_id, wait=True)))
        waiter.start()
        waiter.join(1)
        assert not waiter.is_alive(), 'waiter followed the replacement future'
        assert responses == [{
            'success': True, 'job_id': job_id, 'status': 'cancelled'
        }]
        replacement_release.set()
        with pytest.raises(type(error)):
            manager.get_result(job_id, timeout=5)
        replacement = result(job_id, wait=False)
        assert replacement['status'] == 'failed'
        assert replacement['error'] == str(error)
    finally:
        release.set()
        replacement_release.set()
        if waiter is not None:
            waiter.join(5)
        manager.shutdown()
