import time

import pytest

from praisonaiagents.background.job_manager import BackgroundJobManager, JobInfo, JobStatus
from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore


@pytest.fixture
def reopened_store_with_reused_id(tmp_path):
    path = str(tmp_path / 'jobs.db')
    store = SqliteBackgroundJobStore(path)
    manager = BackgroundJobManager(store=store)
    try:
        origin = {'deliver': 'origin', 'chat_id': 'example'}
        manager.start_job(lambda: 'first', job_id='reused', origin=origin)
        assert manager.get_result('reused', timeout=5) == 'first'
        first_created = manager.get_job_info('reused').created_at
        time.sleep(0.02)
        manager.start_job(lambda: 'middle', job_id='middle', origin=origin)
        assert manager.get_result('middle', timeout=5) == 'middle'
        middle_created = manager.get_job_info('middle').created_at
        time.sleep(0.02)
        manager.start_job(lambda: 'second', job_id='reused', origin=origin)
        assert manager.get_result('reused', timeout=5) == 'second'
        second_created = manager.get_job_info('reused').created_at
        assert first_created < middle_created < second_created
    finally:
        manager.shutdown()
        store.close()
    reopened = SqliteBackgroundJobStore(path)
    try:
        yield reopened, second_created
    finally:
        reopened.close()


def test_reused_job_keeps_new_creation_time_after_restart(reopened_store_with_reused_id):
    store, second_created = reopened_store_with_reused_id
    job = store.get('reused')
    assert job.result == 'second'
    assert job.created_at == second_created


def test_reused_job_is_reconciled_in_new_creation_order(reopened_store_with_reused_id):
    store, _ = reopened_store_with_reused_id
    manager = BackgroundJobManager(store=store)
    delivered = []
    try:
        counts = manager.reconcile_on_start(redeliver=lambda job: delivered.append(job.job_id))
        assert counts['redelivered'] == 2
        assert delivered == ['middle', 'reused']
    finally:
        manager.shutdown()


def test_same_job_updates_keep_its_creation_time():
    store = SqliteBackgroundJobStore(':memory:')
    try:
        job = JobInfo(job_id='same', status=JobStatus.PENDING, created_at=50.0)
        store.upsert(job)
        job.status = JobStatus.COMPLETED
        store.upsert(job)
        assert store.get('same').created_at == 50.0
    finally:
        store.close()
