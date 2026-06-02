"""Unit tests for SQLite kanban store."""

import pytest
import tempfile
import shutil
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