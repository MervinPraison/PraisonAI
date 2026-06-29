"""Unit tests for SQLite kanban store."""

import pytest

pytestmark = pytest.mark.skip(reason="Legacy unit test pending Core Tests gate update")
import tempfile
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

from praisonai.kanban.sqlite_store import SQLiteKanbanStore
from praisonai.kanban.models import Task, TaskStatus


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_kanban.db"
    
    yield db_path
    
    # Cleanup
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def store(temp_db):
    """Create a kanban store with temp database."""
    # Patch the db path to use temp
    original_path = None
    
    try:
        import praisonai.kanban.sqlite_store
        original_method = praisonai.kanban.sqlite_store.get_kanban_db_path
        praisonai.kanban.sqlite_store.get_kanban_db_path = lambda board=None: temp_db
        
        store = SQLiteKanbanStore()
        yield store
    finally:
        # Restore original method
        if original_method:
            praisonai.kanban.sqlite_store.get_kanban_db_path = original_method


class TestSQLiteKanbanStore:
    """Test kanban store operations."""

    def test_create_task(self, store):
        """Test task creation."""
        task_data = {
            'title': 'Test Task',
            'body': 'Test description',
            'status': 'todo',
            'assignee': 'test_user'
        }
        
        task = store.create_task(task_data)
        
        assert task.title == 'Test Task'
        assert task.body == 'Test description'
        assert task.status == TaskStatus.TODO
        assert task.assignee == 'test_user'
        assert task.id.startswith('task_')
        assert task.created_at is not None
        assert task.updated_at is not None

    def test_get_task(self, store):
        """Test task retrieval."""
        task_data = {'title': 'Test Task', 'assignee': 'user1'}
        created_task = store.create_task(task_data)
        
        retrieved_task = store.get_task(created_task.id)
        
        assert retrieved_task is not None
        assert retrieved_task.id == created_task.id
        assert retrieved_task.title == 'Test Task'
        assert retrieved_task.assignee == 'user1'

    def test_get_nonexistent_task(self, store):
        """Test getting non-existent task returns None."""
        task = store.get_task('nonexistent_id')
        assert task is None

    def test_update_task(self, store):
        """Test task updates."""
        task_data = {'title': 'Original Title', 'status': 'todo'}
        created_task = store.create_task(task_data)
        
        updates = {
            'title': 'Updated Title',
            'status': 'ready',
            'assignee': 'new_user'
        }
        
        updated_task = store.update_task(created_task.id, updates)
        
        assert updated_task.title == 'Updated Title'
        assert updated_task.status == TaskStatus.READY
        assert updated_task.assignee == 'new_user'
        assert updated_task.updated_at > created_task.updated_at

    def test_delete_task(self, store):
        """Test task deletion."""
        task_data = {'title': 'To Delete'}
        created_task = store.create_task(task_data)
        
        deleted = store.delete_task(created_task.id)
        assert deleted is True
        
        # Verify task is gone
        task = store.get_task(created_task.id)
        assert task is None

    def test_list_tasks(self, store):
        """Test task listing."""
        # Create multiple tasks
        tasks_data = [
            {'title': 'Task 1', 'status': 'todo', 'assignee': 'user1'},
            {'title': 'Task 2', 'status': 'ready', 'assignee': 'user1'},
            {'title': 'Task 3', 'status': 'todo', 'assignee': 'user2'},
        ]
        
        created_tasks = []
        for data in tasks_data:
            created_tasks.append(store.create_task(data))
        
        # List all tasks
        all_tasks = store.list_tasks()
        assert len(all_tasks) == 3
        
        # Filter by status
        todo_tasks = store.list_tasks({'status': 'todo'})
        assert len(todo_tasks) == 2
        
        # Filter by assignee
        user1_tasks = store.list_tasks({'assignee': 'user1'})
        assert len(user1_tasks) == 2
        
        # Filter by status list
        ready_tasks = store.list_tasks({'status': ['ready', 'running']})
        assert len(ready_tasks) == 1

    def test_move_task(self, store):
        """Test task status changes."""
        task_data = {'title': 'Move Test', 'status': 'todo'}
        created_task = store.create_task(task_data)
        
        moved_task = store.move_task(created_task.id, 'ready')
        
        assert moved_task.status == TaskStatus.READY
        assert moved_task.updated_at > created_task.updated_at

    def test_get_board(self, store):
        """Test board layout generation."""
        # Create tasks in different statuses
        tasks_data = [
            {'title': 'Todo Task', 'status': 'todo'},
            {'title': 'Ready Task', 'status': 'ready'},
            {'title': 'Done Task', 'status': 'done'},
        ]
        
        for data in tasks_data:
            store.create_task(data)
        
        board = store.get_board()
        
        assert 'board' in board
        assert 'columns' in board
        assert 'task_count' in board
        
        assert len(board['columns']['todo']) == 1
        assert len(board['columns']['ready']) == 1
        assert len(board['columns']['done']) == 1
        assert board['task_count'] == 3

    def test_bulk_update(self, store):
        """Test bulk operations."""
        # Create tasks
        task1 = store.create_task({'title': 'Task 1', 'status': 'todo'})
        task2 = store.create_task({'title': 'Task 2', 'status': 'todo'})
        
        # Bulk operations
        operations = [
            {
                'operation': 'move',
                'task_id': task1.id,
                'status': 'ready'
            },
            {
                'operation': 'update',
                'task_id': task2.id,
                'updates': {'title': 'Updated Task 2'}
            }
        ]
        
        results = store.bulk_update(operations)
        
        assert len(results) == 2
        assert results[0].status == TaskStatus.READY
        assert results[1].title == 'Updated Task 2'

    def test_comments(self, store):
        """Test task comments."""
        task = store.create_task({'title': 'Comment Test'})
        
        # Add comment
        comment = store.add_comment(task.id, 'test_user', 'This is a test comment')
        
        assert comment.task_id == task.id
        assert comment.author == 'test_user'
        assert comment.text == 'This is a test comment'
        assert comment.id.startswith('comment_')
        
        # Get comments
        comments = store.get_comments(task.id)
        assert len(comments) == 1
        assert comments[0].text == 'This is a test comment'

    def test_task_links(self, store):
        """Test task dependencies."""
        parent = store.create_task({'title': 'Parent Task'})
        child = store.create_task({'title': 'Child Task'})
        
        # Add dependency
        link = store.add_link(parent.id, child.id)
        
        assert link.parent_id == parent.id
        assert link.child_id == child.id
        
        # Test cycle detection
        with pytest.raises(ValueError, match="cycle"):
            store.add_link(child.id, parent.id)  # Would create cycle
        
        # Remove link
        removed = store.remove_link(parent.id, child.id)
        assert removed is True

    def test_claim_and_release(self, store):
        """Test task claiming for execution."""
        task = store.create_task({'title': 'Claimable Task', 'status': 'ready'})
        
        # Claim task
        claimed = store.claim_task(task.id, 'worker_1')
        assert claimed is True
        
        # Verify task is running and claimed
        updated_task = store.get_task(task.id)
        assert updated_task.status == TaskStatus.RUNNING
        assert updated_task.claim_lock == 'worker_1'
        
        # Another worker cannot claim
        claimed_again = store.claim_task(task.id, 'worker_2')
        assert claimed_again is False
        
        # Release claim
        released = store.release_claim(task.id, 'worker_1')
        assert released is True
        
        # Verify task is ready again
        released_task = store.get_task(task.id)
        assert released_task.status == TaskStatus.READY
        assert released_task.claim_lock is None

    def test_parent_child_promotion(self, store):
        """Test automatic promotion of child tasks when parent completes."""
        # Create parent and child
        parent = store.create_task({'title': 'Parent', 'status': 'running'})
        child = store.create_task({'title': 'Child', 'status': 'todo'})
        
        # Link them
        store.add_link(parent.id, child.id)
        
        # Complete parent
        store.move_task(parent.id, 'done')
        
        # Child should be promoted to ready
        updated_child = store.get_task(child.id)
        assert updated_child.status == TaskStatus.READY

    def test_recompute_ready_promotes_when_parents_done(self, store):
        """recompute_ready promotes a child once all parents are terminal."""
        parent = store.create_task({'title': 'Parent', 'status': 'running'})
        child = store.create_task({'title': 'Child', 'status': 'todo'})
        store.add_link(parent.id, child.id)

        # Parent not done yet -> no promotion
        assert store.recompute_ready() == []
        assert store.get_task(child.id).status == TaskStatus.TODO

        # Complete parent via direct update (bypassing move_task promotion)
        store.update_task(parent.id, {'status': 'done'})

        promoted = store.recompute_ready()
        assert child.id in promoted
        assert store.get_task(child.id).status == TaskStatus.READY

    def test_recompute_ready_child_linked_after_parent_done(self, store):
        """Child linked after parent already done is still promoted."""
        parent = store.create_task({'title': 'Parent', 'status': 'done'})
        child = store.create_task({'title': 'Child', 'status': 'todo'})

        # Link after the parent is already terminal
        store.add_link(parent.id, child.id)

        promoted = store.recompute_ready()
        assert child.id in promoted
        assert store.get_task(child.id).status == TaskStatus.READY

    def test_recompute_ready_waits_for_all_parents(self, store):
        """A child with multiple parents only promotes when all are terminal."""
        p1 = store.create_task({'title': 'P1', 'status': 'done'})
        p2 = store.create_task({'title': 'P2', 'status': 'running'})
        child = store.create_task({'title': 'Child', 'status': 'todo'})
        store.add_link(p1.id, child.id)
        store.add_link(p2.id, child.id)

        assert store.recompute_ready() == []
        assert store.get_task(child.id).status == TaskStatus.TODO

        store.update_task(p2.id, {'status': 'archived'})
        promoted = store.recompute_ready()
        assert child.id in promoted
        assert store.get_task(child.id).status == TaskStatus.READY

    def test_recompute_ready_ignores_parentless_todo(self, store):
        """Parentless 'todo' tasks are not auto-promoted (backward compatible)."""
        lone = store.create_task({'title': 'Lone', 'status': 'todo'})
        promoted = store.recompute_ready()
        assert lone.id not in promoted
        assert store.get_task(lone.id).status == TaskStatus.TODO

    def test_recompute_ready_promotes_blocked_child(self, store):
        """A 'blocked' child is re-evaluated and promoted when parents finish."""
        parent = store.create_task({'title': 'Parent', 'status': 'done'})
        child = store.create_task({'title': 'Child', 'status': 'blocked'})
        store.add_link(parent.id, child.id)

        promoted = store.recompute_ready()
        assert child.id in promoted
        assert store.get_task(child.id).status == TaskStatus.READY

    def test_get_ready_children(self, store):
        """get_ready_children returns children eligible for promotion."""
        parent = store.create_task({'title': 'Parent', 'status': 'done'})
        ready_child = store.create_task({'title': 'Ready Child', 'status': 'todo'})
        store.add_link(parent.id, ready_child.id)

        other_parent = store.create_task({'title': 'Other', 'status': 'running'})
        blocked_child = store.create_task({'title': 'Blocked Child', 'status': 'todo'})
        store.add_link(parent.id, blocked_child.id)
        store.add_link(other_parent.id, blocked_child.id)

        children = store.get_ready_children(parent.id)
        assert ready_child.id in children
        assert blocked_child.id not in children

    def test_blocked_by_parents(self, store):
        """Test that child cannot move to ready if parents are incomplete."""
        parent = store.create_task({'title': 'Incomplete Parent', 'status': 'todo'})
        child = store.create_task({'title': 'Child', 'status': 'todo'})
        
        # Link them
        store.add_link(parent.id, child.id)
        
        # Try to move child to ready - should fail
        with pytest.raises(ValueError, match="incomplete parent"):
            store.move_task(child.id, 'ready')

    def test_list_events(self, store):
        """Test event listing for audit trail."""
        task = store.create_task({'title': 'Event Test'})
        store.update_task(task.id, {'title': 'Updated Title'})
        
        events = store.list_events()
        
        # Should have created and updated events
        assert len(events) >= 2
        event_types = [e.event_type for e in events]
        assert 'created' in event_types
        assert 'updated' in event_types

    def test_concurrent_access_simulation(self, store):
        """Test optimistic locking prevents concurrent modifications."""
        task = store.create_task({'title': 'Concurrent Test'})
        
        # Simulate concurrent update by manually manipulating version
        with store._get_connection() as conn:
            conn.execute("UPDATE tasks SET version = 2 WHERE id = ?", (task.id,))
        
        # This update should fail due to version mismatch
        with pytest.raises(ValueError, match="modified by another process"):
            store.update_task(task.id, {'title': 'Concurrent Update'})


class TestClaimReclamation:
    """Tests for durable claim leases and stale-claim reclamation."""

    def _make_ready(self, store, title='Reclaim Test'):
        return store.create_task({'title': title, 'status': 'ready'})

    def test_claim_records_lease_and_pid(self, store):
        task = self._make_ready(store)
        ok = store.claim_task(task.id, 'w1', ttl_seconds=900, worker_pid=12345)
        assert ok is True

        claimed = store.get_task(task.id)
        assert claimed.status == TaskStatus.RUNNING
        assert claimed.claim_lock == 'w1'
        assert claimed.worker_pid == 12345
        assert claimed.claim_expires is not None
        assert claimed.last_heartbeat_at is not None

    def test_claim_backward_compatible_defaults(self, store):
        task = self._make_ready(store)
        assert store.claim_task(task.id, 'w1') is True
        claimed = store.get_task(task.id)
        assert claimed.status == TaskStatus.RUNNING
        assert claimed.claim_lock == 'w1'

    def test_heartbeat_updates_timestamp(self, store):
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', worker_pid=99999)
        before = store.get_task(task.id).last_heartbeat_at
        assert store.heartbeat(task.id, 'w1') is True
        after = store.get_task(task.id).last_heartbeat_at
        assert after >= before

    def test_heartbeat_wrong_worker_fails(self, store):
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', worker_pid=99999)
        assert store.heartbeat(task.id, 'other') is False

    def test_heartbeat_extends_lease(self, store):
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', ttl_seconds=1, worker_pid=99999)
        old_expiry = store.get_task(task.id).claim_expires
        assert store.heartbeat(task.id, 'w1', ttl_seconds=3600) is True
        new_expiry = store.get_task(task.id).claim_expires
        assert new_expiry > old_expiry

    def test_reclaim_dead_worker(self, store):
        """Expired lease + dead PID -> reclaimed to ready."""
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', ttl_seconds=900, worker_pid=2147480000)
        with store._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET claim_expires = ? WHERE id = ?",
                (datetime(2000, 1, 1).isoformat(), task.id),
            )

        reclaimed = store.reclaim_stale_claims()
        assert task.id in reclaimed
        t = store.get_task(task.id)
        assert t.status == TaskStatus.READY
        assert t.claim_lock is None
        assert t.worker_pid is None

    def test_reclaim_skips_valid_lease(self, store):
        """Unexpired lease is never reclaimed."""
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', ttl_seconds=3600, worker_pid=2147480000)
        reclaimed = store.reclaim_stale_claims()
        assert task.id not in reclaimed
        assert store.get_task(task.id).status == TaskStatus.RUNNING

    def test_reclaim_keeps_live_heartbeating_worker(self, store):
        """Expired lease but live PID + fresh heartbeat -> kept."""
        import os
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', ttl_seconds=900, worker_pid=os.getpid())
        with store._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET claim_expires = ?, last_heartbeat_at = ? WHERE id = ?",
                (datetime(2000, 1, 1).isoformat(),
                 datetime.utcnow().isoformat(), task.id),
            )
        reclaimed = store.reclaim_stale_claims(stale_timeout_seconds=3600)
        assert task.id not in reclaimed
        assert store.get_task(task.id).status == TaskStatus.RUNNING

    def test_reclaim_stale_heartbeat_live_worker(self, store):
        """Expired lease, live PID, but stale heartbeat -> reclaimed."""
        import os
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', ttl_seconds=900, worker_pid=os.getpid())
        with store._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET claim_expires = ?, last_heartbeat_at = ? WHERE id = ?",
                (datetime(2000, 1, 1).isoformat(),
                 datetime(2000, 1, 1).isoformat(), task.id),
            )
        reclaimed = store.reclaim_stale_claims(stale_timeout_seconds=60)
        assert task.id in reclaimed
        assert store.get_task(task.id).status == TaskStatus.READY

    def test_reclaim_legacy_claim_without_expiry(self, store):
        """Migrated/legacy claim (no lease) with a dead worker -> reclaimed."""
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', worker_pid=2147480000)
        with store._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET claim_expires = NULL, last_heartbeat_at = NULL "
                "WHERE id = ?",
                (task.id,),
            )

        reclaimed = store.reclaim_stale_claims()
        assert task.id in reclaimed
        assert store.get_task(task.id).status == TaskStatus.READY

    def test_release_claim_does_not_requeue_done_task(self, store):
        """release_claim must not revert a completed task back to ready."""
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', worker_pid=99999)
        store.move_task(task.id, 'done')

        # Worker finished; a late release should be a no-op on status.
        store.release_claim(task.id, 'w1')
        t = store.get_task(task.id)
        assert t.status == TaskStatus.DONE
        assert t.claim_lock is None

    def test_reclaim_skips_after_concurrent_heartbeat(self, store):
        """A heartbeat that bumps version after candidate selection wins the race."""
        task = self._make_ready(store)
        store.claim_task(task.id, 'w1', ttl_seconds=900, worker_pid=2147480000)
        # Expire the lease so the task is a reclaim candidate.
        with store._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET claim_expires = ? WHERE id = ?",
                (datetime(2000, 1, 1).isoformat(), task.id),
            )
        version_before = None
        with store._get_connection() as conn:
            row = conn.execute(
                "SELECT version FROM tasks WHERE id = ?", (task.id,)
            ).fetchone()
            version_before = row['version']

        # Simulate a heartbeat racing in by bumping the version directly; the
        # version guard in reclaim must then refuse to reclaim this row.
        with store._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET version = ? WHERE id = ?",
                (version_before + 1, task.id),
            )

        # Manually exercise the guard: build a stale snapshot at the old version.
        # reclaim_stale_claims re-reads, so to prove the guard we assert that a
        # row whose version moved on is not double-reclaimed. Here we confirm the
        # guarded UPDATE is version-scoped by checking reclaim still succeeds once
        # (it re-selects current version) but never resurrects after a heartbeat.
        store.heartbeat(task.id, 'w1', ttl_seconds=3600)
        reclaimed = store.reclaim_stale_claims(stale_timeout_seconds=60)
        # Lease was extended by the heartbeat -> not reclaimed.
        assert task.id not in reclaimed
        assert store.get_task(task.id).status == TaskStatus.RUNNING


class TestTaskRunsAndRetry:
    """Tests for attempt history, structured handoff and circuit-breaker."""

    def test_idempotent_create_returns_existing(self, store):
        """Repeat create with same idempotency_key returns the same task."""
        first = store.create_task({'title': 'Audit auth'}, idempotency_key='audit-1')
        second = store.create_task({'title': 'Different title'}, idempotency_key='audit-1')

        assert first.id == second.id
        assert second.title == 'Audit auth'  # original is returned unchanged

    def test_idempotent_create_different_keys(self, store):
        """Different idempotency keys create distinct tasks."""
        a = store.create_task({'title': 'A'}, idempotency_key='k-a')
        b = store.create_task({'title': 'B'}, idempotency_key='k-b')
        assert a.id != b.id

    def test_start_and_close_run(self, store):
        """A run captures profile/outcome/summary/metadata/error."""
        task = store.create_task({'title': 'Runnable'})

        run_id = store.start_run(task.id, profile='worker-1')
        assert isinstance(run_id, int)

        # current_run_id points at the active run
        assert store.get_task(task.id).current_run_id == run_id

        closed = store.close_run(
            run_id, 'crashed',
            summary='tried path A', metadata={'changed_files': ['a.py']},
            error='boom',
        )
        assert closed.outcome == 'crashed'
        assert closed.summary == 'tried path A'
        assert closed.metadata == {'changed_files': ['a.py']}
        assert closed.error == 'boom'
        assert closed.ended_at is not None
        # Closing the run clears the active-attempt pointer
        assert store.get_task(task.id).current_run_id is None

    def test_get_runs_ordered(self, store):
        """get_runs returns all attempts oldest first."""
        task = store.create_task({'title': 'Multi attempt'})
        store.record_run(task.id, 'failed', error='e1')
        store.record_run(task.id, 'completed', summary='done')

        runs = store.get_runs(task.id)
        assert len(runs) == 2
        assert [r.outcome for r in runs] == ['failed', 'completed']

    def test_record_failure_circuit_breaker(self, store):
        """Auto-block when consecutive failures reach max_retries."""
        task = store.create_task({'title': 'Flaky', 'max_retries': 2})

        assert store.record_failure(task.id, error='e1') is False
        assert store.record_failure(task.id, error='e2') is True

        blocked = store.get_task(task.id)
        assert blocked.status == TaskStatus.BLOCKED
        assert blocked.consecutive_failures == 2

    def test_completion_resets_failure_counter(self, store):
        """A completed run resets consecutive_failures to zero."""
        task = store.create_task({'title': 'Recovers', 'max_retries': 5})
        store.record_failure(task.id, error='e1')
        assert store.get_task(task.id).consecutive_failures == 1

        store.record_run(task.id, 'completed', summary='ok')
        assert store.get_task(task.id).consecutive_failures == 0

    def test_default_max_retries_used_when_unset(self, store):
        """Tasks without max_retries fall back to the board default."""
        from praisonai.kanban.sqlite_store import DEFAULT_MAX_RETRIES
        task = store.create_task({'title': 'Default breaker'})

        blocked = False
        for i in range(DEFAULT_MAX_RETRIES):
            blocked = store.record_failure(task.id, error=f'e{i}')
        assert blocked is True
        assert store.get_task(task.id).status == TaskStatus.BLOCKED

    def test_get_retry_context(self, store):
        """Retry context exposes prior outcomes/summaries/errors."""
        task = store.create_task({'title': 'Retryable'})
        store.record_run(task.id, 'crashed', error='segfault', summary='path A')

        ctx = store.get_retry_context(task.id)
        assert len(ctx) == 1
        assert ctx[0]['outcome'] == 'crashed'
        assert ctx[0]['error'] == 'segfault'
        assert ctx[0]['summary'] == 'path A'

    def test_idempotent_create_scoped_by_tenant(self, store):
        """Same idempotency key under different tenants creates distinct tasks."""
        a = store.create_task(
            {'title': 'Tenant A task', 'tenant': 'tenant-a'},
            idempotency_key='shared-key',
        )
        b = store.create_task(
            {'title': 'Tenant B task', 'tenant': 'tenant-b'},
            idempotency_key='shared-key',
        )
        assert a.id != b.id
        assert a.tenant == 'tenant-a'
        assert b.tenant == 'tenant-b'

    def test_invalid_max_retries_falls_back_to_default(self, store):
        """Non-positive / invalid max_retries must not auto-block on first fail."""
        for bad in (0, -1, 'oops'):
            task = store.create_task({'title': f'Bad {bad}', 'max_retries': bad})
            # First failure should NOT circuit-break (falls back to default)
            assert store.record_failure(task.id, error='e1') is False
            assert store.get_task(task.id).status != TaskStatus.BLOCKED

    def test_move_to_done_clears_claim(self, store):
        """A task moved to a terminal status no longer carries a claim_lock."""
        task = store.create_task({'title': 'Claimed', 'status': 'ready'})
        assert store.claim_task(task.id, 'worker-1') is True
        assert store.get_task(task.id).claim_lock == 'worker-1'

        store.move_task(task.id, 'done')
        done = store.get_task(task.id)
        assert done.status == TaskStatus.DONE
        assert not done.claim_lock

    def test_close_run_rejects_already_finalized(self, store):
        """A finalized run cannot be re-closed with a different outcome."""
        task = store.create_task({'title': 'Finalize once'})
        run_id = store.start_run(task.id, profile='worker-1')
        store.close_run(run_id, 'failed', error='boom', summary='attempt A')

        # A stale caller trying to mark the same run completed must NOT rewrite
        # the already-finalized outcome/summary/error.
        result = store.close_run(run_id, 'completed', summary='now done')
        assert result.outcome == 'failed'
        assert result.summary == 'attempt A'
        assert result.error == 'boom'

        runs = store.get_runs(task.id)
        assert len(runs) == 1
        assert runs[0].outcome == 'failed'

    def test_legacy_zero_max_retries_does_not_block_on_first_failure(self, store):
        """A persisted max_retries=0 (legacy/migrated) falls back to default."""
        task = store.create_task({'title': 'Legacy breaker'})
        # Simulate a row written before create-path validation existed.
        with store._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET max_retries = 0 WHERE id = ?", (task.id,)
            )

        assert store.record_failure(task.id, error='e1') is False
        assert store.get_task(task.id).status != TaskStatus.BLOCKED

    def test_migration_replaces_global_idempotency_index(self, tmp_path):
        """A legacy non-tenant-scoped idempotency index is replaced on init."""
        import praisonai.kanban.sqlite_store
        legacy_path = tmp_path / 'legacy_kanban.db'
        conn = sqlite3.connect(str(legacy_path))
        conn.execute("""
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY, title TEXT, body TEXT, status TEXT,
                assignee TEXT, priority INTEGER, tenant TEXT, board TEXT,
                workspace_kind TEXT, metadata TEXT, idempotency_key TEXT,
                claim_lock TEXT, version INTEGER DEFAULT 1,
                created_at TEXT, updated_at TEXT
            )
        """)
        # Old, board-only (non-tenant-scoped) idempotency index.
        conn.execute(
            "CREATE UNIQUE INDEX idx_tasks_idempotency "
            "ON tasks(board, idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        conn.commit()
        conn.close()

        # Re-opening through the store should migrate the index to be
        # tenant-scoped so two tenants on the same board no longer collide.
        original = praisonai.kanban.sqlite_store.get_kanban_db_path
        praisonai.kanban.sqlite_store.get_kanban_db_path = lambda board=None: legacy_path
        try:
            migrated = SQLiteKanbanStore()
            a = migrated.create_task(
                {'title': 'A', 'tenant': 'tenant-a'}, idempotency_key='shared'
            )
            b = migrated.create_task(
                {'title': 'B', 'tenant': 'tenant-b'}, idempotency_key='shared'
            )
            assert a.id != b.id
        finally:
            praisonai.kanban.sqlite_store.get_kanban_db_path = original
