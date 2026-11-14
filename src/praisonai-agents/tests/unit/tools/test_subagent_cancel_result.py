from concurrent.futures import CancelledError
from threading import Event, Thread

import pytest

from praisonaiagents.background import job_manager
from praisonaiagents.background.job_manager import BackgroundJobManager
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
    original_get_result = manager.get_result
    try:
        job_id = tool['function'](task='old', background=True)['job_id']
        assert entered.wait(5)
        assert manager.cancel_job(job_id)

        def reuse_after_cancellation(requested):
            try:
                return original_get_result(requested)
            except CancelledError:
                manager.start_job(lambda: 'replacement', job_id=requested)
                raise

        monkeypatch.setattr(manager, 'get_result', reuse_after_cancellation)
        assert tool['result_tool']['function'](job_id, wait=True) == {
            'success': True, 'job_id': job_id, 'status': 'cancelled'
        }
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
    original_get_result = manager.get_result
    responses = []
    thread = None
    try:
        job_id = tool['function'](task='running', background=True)['job_id']
        assert entered.wait(5)

        def signal_wait(requested):
            waiting.set()
            return original_get_result(requested)

        monkeypatch.setattr(manager, 'get_result', signal_wait)
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
