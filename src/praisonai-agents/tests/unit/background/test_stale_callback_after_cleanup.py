import gc
import time
import weakref
from threading import Event, Thread

import pytest

from praisonaiagents.background.job_manager import BackgroundJobManager, JobInfo, JobStatus
from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore


def test_old_callback_cannot_overwrite_reused_id_after_both_jobs_are_evicted():
    store = SqliteBackgroundJobStore(':memory:')
    manager = BackgroundJobManager(store=store)
    entered, release = Event(), Event()
    sent = []

    def old_callback(job):
        entered.set()
        assert release.wait(5)
        sent.append(job.result)

    try:
        manager.start_job(lambda: 'old', job_id='same', on_complete=old_callback,
                          origin={'deliver': 'origin', 'chat_id': 'old'})
        assert entered.wait(5)
        assert manager.cleanup_completed(max_age=-1) == 1
        manager.start_job(lambda: 'new', job_id='same',
                          origin={'deliver': 'origin', 'chat_id': 'new'})
        assert manager.get_result('same', timeout=5) == 'new'
        assert manager.cleanup_completed(max_age=-1) == 1
        release.set()
        manager.shutdown()
        saved = store.get('same')
        assert sent == ['old']
        assert saved.result == 'new'
        assert saved.origin['chat_id'] == 'new'
        assert saved.delivered is False
    finally:
        release.set()
        manager.shutdown()
        store.close()


@pytest.mark.parametrize('succeeds', [True, False])
def test_evicted_current_job_retains_delivery_outcome(succeeds):
    store = SqliteBackgroundJobStore(':memory:')
    manager = BackgroundJobManager(store=store)
    entered, release = Event(), Event()

    def callback(job):
        entered.set()
        assert release.wait(5)
        if not succeeds:
            raise RuntimeError('delivery failed')

    try:
        manager.start_job(lambda: 'result', job_id='one', on_complete=callback,
                          origin={'deliver': 'origin', 'chat_id': 'one'})
        assert entered.wait(5)
        assert manager.cleanup_completed(max_age=-1) == 1
        release.set()
        manager.shutdown()
        saved = store.get('one')
        assert saved.result == 'result'
        assert saved.delivered is succeeds
        assert bool(store.list_unreconciled()) is (not succeeds)
    finally:
        release.set()
        manager.shutdown()
        store.close()


def test_reconciliation_callback_cannot_overwrite_reused_evicted_job():
    store = SqliteBackgroundJobStore(':memory:')
    store.upsert(JobInfo(job_id='same', status=JobStatus.COMPLETED,
                         completed_at=time.time(), result='old',
                         origin={'deliver': 'origin', 'chat_id': 'old'}))
    manager = BackgroundJobManager(store=store)
    entered, release = Event(), Event()

    def redeliver(job):
        entered.set()
        assert release.wait(5)

    thread = Thread(target=lambda: manager.reconcile_on_start(redeliver=redeliver))
    try:
        thread.start()
        assert entered.wait(5)
        assert manager.cleanup_completed(max_age=-1) == 1
        manager.start_job(lambda: 'new', job_id='same',
                          origin={'deliver': 'origin', 'chat_id': 'new'})
        assert manager.get_result('same', timeout=5) == 'new'
        assert manager.cleanup_completed(max_age=-1) == 1
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        saved = store.get('same')
        assert saved.result == 'new'
        assert saved.origin['chat_id'] == 'new'
        assert saved.delivered is False
    finally:
        release.set()
        thread.join(5)
        manager.shutdown()
        store.close()


@pytest.mark.parametrize('succeeds', [True, False])
def test_evicted_reconciled_job_retains_delivery_outcome(succeeds):
    store = SqliteBackgroundJobStore(':memory:')
    store.upsert(JobInfo(job_id='same', status=JobStatus.COMPLETED,
                         completed_at=time.time(), result='result',
                         origin={'deliver': 'origin', 'chat_id': 'one'}))
    manager = BackgroundJobManager(store=store)
    entered, release = Event(), Event()

    def redeliver(job):
        entered.set()
        assert release.wait(5)
        if not succeeds:
            raise RuntimeError('delivery failed')

    thread = Thread(target=lambda: manager.reconcile_on_start(redeliver=redeliver))
    try:
        thread.start()
        assert entered.wait(5)
        assert manager.cleanup_completed(max_age=-1) == 1
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        saved = store.get('same')
        assert saved.result == 'result'
        assert saved.delivered is succeeds
        assert bool(store.list_unreconciled()) is (not succeeds)
    finally:
        release.set()
        thread.join(5)
        manager.shutdown()
        store.close()


def test_completed_job_is_not_kept_alive_after_cleanup():
    manager = BackgroundJobManager()
    try:
        job_id = manager.start_job(lambda: 'done')
        assert manager.get_result(job_id, timeout=5) == 'done'
        manager.shutdown()
        job = manager.get_job_info(job_id)
        ref = weakref.ref(job)
        assert manager.cleanup_completed(max_age=-1) == 1
        del job
        gc.collect()
        assert ref() is None
    finally:
        manager.shutdown()
